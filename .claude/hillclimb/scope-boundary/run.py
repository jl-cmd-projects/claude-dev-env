"""Run the scope-boundary cases as fresh sessions and grade each one.

::

    python3 run.py --variant baseline --direct
    python3 run.py --variant shipped --direct --cases d01,c02

Each case runs once per rep in a new git workspace copied from ``fixture/``.
Variant ``baseline`` installs nothing. Variant ``shipped`` installs the rules
index and the verified-work guide, which carry the scope rule; variant ``v2``
installs the candidate text under ``candidates/v2/``. Each session
loads project and local settings only, edits files without a prompt, and has
one extra tool, ``request_decision``, a stub that stands in for a decision
card. A judge model reads each transcript against the case's scope labels.
Rows land in ``<variant>/results.jsonl`` as each case finishes, tagged with a
run digest over the fixture, the installed files, the settings, each
case's id, prompt and setup turn, and the harness source, so a rerun skips every (case, rep) already scored.
"""

import argparse
import json
import logging
import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

flow_directory = Path(__file__).resolve().parent
all_import_roots = [
    str(each_root)
    for each_root in (
        flow_directory,
        flow_directory.parent / "features-start-with-an-eval",
        flow_directory.parent / "rules-index",
    )
]
sys.path[:0] = [
    each_root for each_root in all_import_roots if each_root not in sys.path
]

from rules_eval_support import judge as rules_judge
from rules_eval_support.config.constants import JUDGE_MODEL
from rules_eval_support.judge import run_judge
from rules_eval_support.launch import launch_words
from scope_eval_support import grading
from scope_eval_support.config.constants import (
    CASES_DIGEST_FIELD,
    CASES_FILE,
    DEFAULT_EFFORT,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    DEFAULT_PARALLEL,
    DEFAULT_REPS,
    DEFAULT_TIMEOUT_SECONDS,
    ERRORS_FILE_NAME,
    FAILURE_JUDGE,
    FLOW_ROOT,
    PRIOR_REPLY_FIELD,
    RESULTS_FILE_NAME,
    ALL_SESSION_ENVIRONMENT,
    SESSION_ID_FIELD,
    STATE_FILE,
    TRACES_DIRECTORY_NAME,
    USAGE_ERROR_EXIT_CODE,
    WORKSPACE_DIFF_FIELD,
)
from scope_eval_support.grading import (
    decision_questions,
    edited_paths,
    diff_checked_verdict,
    grade_session,
    judge_text,
)
from scope_eval_support.scoring import scored_row
from scope_eval_support.summary import summary
from scope_eval_support.workspace import (
    cases_digest,
    decision_stub_failure,
    fixture_bytes,
    prepare_workspace,
    scope_words,
    starting_commit,
    workspace_diff,
    write_mcp_config,
)
from session_eval_support import session
from session_eval_support.config.constants import RUN_DIGEST_FIELD
from session_eval_support.grading import ToolCall, tool_calls
from session_eval_support.rows import (
    append_row,
    failure_row,
    open_errors,
    rows_for_install,
    select_cases,
    select_variant,
)
from session_eval_support.session import (
    SessionRun,
    SessionSettings,
    final_event,
    harness_sources,
    installed_files,
    remove_workspace,
    run_digest,
    trace_turns,
    unscorable,
    write_trace,
)

logger = logging.getLogger(__name__)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--cases", default="")
    parser.add_argument("--reps", type=int, default=DEFAULT_REPS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default=DEFAULT_EFFORT)
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--timeout-s", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL)
    parser.add_argument(
        "--direct",
        action="store_true",
        help="run every session and judge on this session's account, skipping the broker",
    )
    return parser.parse_args()


@dataclass(frozen=True)
class RunPlan:
    """What every session in one variant run shares."""

    variant_directory: Path
    bytes_by_target: dict[str, bytes]
    digest: str
    settings: SessionSettings
    is_direct: bool
    mcp_config_path: Path


def _harness_paths() -> list[Path]:
    return harness_sources(
        Path(grading.__file__).parent,
        Path(session.__file__).parent,
        Path(rules_judge.__file__).parent,
        Path(__file__),
    )


def _plan(
    arguments: argparse.Namespace,
    variant_by_field: dict[str, object],
    all_file_cases: list[dict[str, str]],
) -> RunPlan:
    bytes_by_target = installed_files(
        [tuple(each_pair) for each_pair in variant_by_field["install"]]
    )
    settings = SessionSettings(
        arguments.model, arguments.effort, arguments.max_turns, arguments.timeout_s
    )
    digest = run_digest(
        {**bytes_by_target, **fixture_bytes()},
        {
            **asdict(settings),
            "direct": arguments.direct,
            CASES_DIGEST_FIELD: cases_digest(all_file_cases),
        },
        _harness_paths(),
    )
    variant_directory = FLOW_ROOT / arguments.variant
    (variant_directory / TRACES_DIRECTORY_NAME).mkdir(parents=True, exist_ok=True)
    return RunPlan(
        variant_directory,
        bytes_by_target,
        digest,
        settings,
        arguments.direct,
        write_mcp_config(variant_directory),
    )


def _run_session(
    workspace: Path, prompt: str, plan: RunPlan, resume_session_id: str = ""
) -> SessionRun:
    return session.run_session(
        workspace,
        prompt,
        plan.settings,
        lambda report_path, all_claude_words: launch_words(
            report_path,
            scope_words(all_claude_words, plan.mcp_config_path, resume_session_id),
            plan.is_direct,
        ),
    )


def _run_turns(
    workspace: Path, case_by_field: dict[str, str], plan: RunPlan
) -> tuple[SessionRun, str]:
    """Run the case's setup turn when it has one, then the graded turn.

    A two-turn case first sends ``setup``. The graded turn then continues
    that conversation by its session id in the same workspace, and the setup turn's final
    reply goes to the judge as the earlier turn the ask answers.
    """
    setup_prompt = case_by_field.get("setup")
    if not setup_prompt:
        return _run_session(workspace, case_by_field["prompt"], plan), ""
    setup_run = _run_session(workspace, setup_prompt, plan)
    if unscorable(setup_run, plan.settings) is not None:
        return setup_run, ""
    setup_final = final_event(setup_run.all_events) or {}
    return (
        _run_session(
            workspace,
            case_by_field["prompt"],
            plan,
            resume_session_id=str(setup_final.get(SESSION_ID_FIELD, "")),
        ),
        str(setup_final.get("result", "")),
    )


def _judge(
    case_by_field: dict[str, str], session_run: SessionRun, is_direct: bool
) -> tuple[dict[str, object] | None, dict[str, object]]:
    all_turns = trace_turns(case_by_field["prompt"], session_run.all_events)
    transcript = rules_judge._transcript_within_limit(all_turns)
    verdict, judge_event = run_judge(judge_text(case_by_field, transcript), is_direct)
    return verdict, {
        "judge_model": JUDGE_MODEL,
        "judge_usage": judge_event.get("usage"),
        "judge_verdict": verdict,
        PRIOR_REPLY_FIELD: case_by_field[PRIOR_REPLY_FIELD],
        WORKSPACE_DIFF_FIELD: case_by_field[WORKSPACE_DIFF_FIELD],
    }


def _record_failure(plan: RunPlan, failure_by_field: dict[str, object]) -> None:
    append_row(plan.variant_directory / ERRORS_FILE_NAME, failure_by_field)


def _grade(
    case_by_field: dict[str, str],
    verdict_by_flag: dict[str, object],
    all_calls: list[ToolCall],
    meta_by_field: dict[str, object],
) -> dict[str, int]:
    return grade_session(
        decision_questions(all_calls),
        diff_checked_verdict(verdict_by_flag, case_by_field, meta_by_field),
    )


def _judge_and_record(
    case_by_field: dict[str, str],
    rep: int,
    session_run: SessionRun,
    plan: RunPlan,
    workspace: Path,
) -> None:
    verdict, judge_record = _judge(case_by_field, session_run, plan.is_direct)
    if verdict is None:
        _record_failure(
            plan,
            failure_row(case_by_field, rep, plan.digest, FAILURE_JUDGE, judge_record),
        )
        return
    write_trace(case_by_field, rep, plan.variant_directory, session_run)
    all_calls = tool_calls(session_run.all_events)
    meta_by_field = {**judge_record, RUN_DIGEST_FIELD: plan.digest}
    meta_by_field["edited_paths"] = edited_paths(all_calls, workspace)
    grade_by_metric = _grade(case_by_field, verdict, all_calls, meta_by_field)
    append_row(
        plan.variant_directory / RESULTS_FILE_NAME,
        scored_row(
            case_by_field,
            rep,
            session_run,
            plan.settings,
            grade_by_metric,
            meta_by_field,
        ),
    )


def _run_one(case_by_field: dict[str, str], rep: int, plan: RunPlan) -> None:
    workspace = prepare_workspace(plan.bytes_by_target)
    try:
        from_commit = starting_commit(workspace)
        session_run, prior_reply = _run_turns(workspace, case_by_field, plan)
        final_diff = workspace_diff(workspace, from_commit)
    finally:
        remove_workspace(workspace)
    failure = unscorable(session_run, plan.settings) or decision_stub_failure(
        session_run.all_events
    )
    if failure is not None:
        _record_failure(plan, failure_row(case_by_field, rep, plan.digest, *failure))
        return
    judged_case = {
        **case_by_field,
        PRIOR_REPLY_FIELD: prior_reply,
        WORKSPACE_DIFF_FIELD: final_diff,
    }
    _judge_and_record(judged_case, rep, session_run, plan, workspace)


def _wait_for_all(all_futures: list[Future[None]]) -> None:
    try:
        for each_future in all_futures:
            each_future.result()
    finally:
        for each_future in all_futures:
            each_future.cancel()


def _run_pending(
    all_pending: list[tuple[dict[str, str], int]], plan: RunPlan, parallel: int
) -> None:
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        _wait_for_all(
            [
                executor.submit(_run_one, each_case, each_rep, plan)
                for each_case, each_rep in all_pending
            ]
        )


def _pending_pairs(
    all_cases: list[dict[str, str]], reps: int, plan: RunPlan, all_case_ids: set[str]
) -> list[tuple[dict[str, str], int]]:
    all_done = {
        (each_row["prompt_id"], each_row["rep"])
        for each_row in rows_for_install(
            plan.variant_directory / RESULTS_FILE_NAME, plan.digest, all_case_ids
        )
    }
    return [
        (each_case, each_rep)
        for each_case in all_cases
        for each_rep in range(reps)
        if (each_case["id"], each_rep) not in all_done
    ]


def _report(variant_name: str, plan: RunPlan, all_case_ids: set[str]) -> None:
    all_rows = rows_for_install(
        plan.variant_directory / RESULTS_FILE_NAME, plan.digest, all_case_ids
    )
    all_errors = rows_for_install(
        plan.variant_directory / ERRORS_FILE_NAME, plan.digest, all_case_ids
    )
    logger.info(
        "%s: %s",
        variant_name,
        summary(all_rows, len(open_errors(all_errors, all_rows))),
    )


def main() -> int:
    """Run every pending (case, rep) for one variant and print the headline.

    Returns:
        Process exit status, zero once every pending run has finished.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    arguments = _parse_arguments()
    os.environ.update(ALL_SESSION_ENVIRONMENT)
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    try:
        variant_by_field = select_variant(state["variants"], arguments.variant)
        all_cases = select_cases(
            json.loads(CASES_FILE.read_text(encoding="utf-8")), arguments.cases
        )
    except ValueError as error:
        logger.error("%s", error)
        return USAGE_ERROR_EXIT_CODE
    plan = _plan(
        arguments,
        variant_by_field,
        json.loads(CASES_FILE.read_text(encoding="utf-8")),
    )
    all_case_ids = {each_case["id"] for each_case in all_cases}
    all_pending = _pending_pairs(all_cases, arguments.reps, plan, all_case_ids)
    _run_pending(all_pending, plan, arguments.parallel)
    _report(arguments.variant, plan, all_case_ids)
    return 0


if __name__ == "__main__":
    sys.exit(main())
