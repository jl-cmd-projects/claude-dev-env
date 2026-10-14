"""Run the rules-index cases as fresh sessions and grade each one.

::

    python3 run.py --variant baseline --cases w02,b02,s01,s02
    python3 run.py --variant index --cases w02,b02,s01,s02

Variant ``baseline`` installs the always-loaded rules and guides from the
commit before the index. Variant ``index`` installs them from ``HEAD``. Each
session loads project and local settings only, so the home config's rules,
hooks and skills stay out of both arms. Rows land in
``<variant>/results.jsonl`` as each case finishes, each tagged with a digest
of the installed rules. A rerun skips every (case, rep) already there under
the same digest, and the headline counts only those rows and errors.
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

flow_directory = Path(__file__).resolve().parent
all_import_roots = [str(each_root) for each_root in (flow_directory, flow_directory.parent / "features-start-with-an-eval", flow_directory.parents[2] / "packages" / "claude-dev-env" / "scripts")]
sys.path[:0] = [each_root for each_root in all_import_roots if each_root not in sys.path]

from contrast_framing import find_contrast_framing
from rules_eval_support.config.constants import (
    CASES_FILE,
    CHECK_CONTRAST,
    CHECK_JUDGE,
    DEFAULT_EFFORT,
    DEFAULT_MAX_TURNS,
    FAILURE_JUDGE,
    FIRST_TOOLS_SHOWN,
    FLOW_ROOT,
    GROUP_SEPARATOR,
    JUDGE_MODEL,
    STATE_FILE,
)
from rules_eval_support.grading import opened_a_guide, tool_check
from rules_eval_support.install import installed_digest, prepare_workspace, variant_files
from rules_eval_support.judge import judge_prompt, run_judge
from rules_eval_support.launch import run_session
from session_eval_support.config.constants import (
    DEFAULT_MODEL,
    DEFAULT_PARALLEL,
    DEFAULT_REPS,
    DEFAULT_TIMEOUT_SECONDS,
    ERRORS_FILE_NAME,
    INSTALLED_DIGEST_FIELD,
    JSON_INDENT,
    LATENCY_DECIMALS,
    META_FIELD,
    RESULTS_FILE_NAME,
    STATUS_OK,
    TRACE_FILE_TEMPLATE,
    TRACES_DIRECTORY_NAME,
    USAGE_ERROR_EXIT_CODE,
)
from session_eval_support.grading import tool_calls, wilson_interval
from session_eval_support.rows import append_row, rows_for_install, select_cases, select_variant
from session_eval_support.session import (
    SessionRun,
    SessionSettings,
    final_event,
    remove_workspace,
    served_models,
    trace_turns,
    unscorable,
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
    parser.add_argument("--label", default="", help="results folder name; defaults to the variant name")
    parser.add_argument("--direct", action="store_true", help="run every session and judge on this session's account, skipping the broker")
    return parser.parse_args()


def _grade(case_by_field: dict[str, str], session: SessionRun, is_direct: bool) -> tuple[bool | None, dict[str, object]]:
    all_calls = tool_calls(session.all_events)
    check = case_by_field["check"]
    grader = tool_check(check)
    if grader is not None:
        return grader(all_calls), {}
    final_text = str((final_event(session.all_events) or {}).get("result", ""))
    if check == CHECK_CONTRAST:
        all_hits = find_contrast_framing(final_text)
        return not all_hits, {"contrast_hits": all_hits}
    if check == CHECK_JUDGE:
        verdict, judge_event = run_judge(
            judge_prompt(case_by_field["prompt"], case_by_field["rubric"], trace_turns(case_by_field["prompt"], session.all_events)),
            is_direct,
        )
        judge_record = {"judge_model": JUDGE_MODEL, "judge_usage": judge_event.get("usage"), "judge_verdict": verdict}
        return (None if verdict is None else bool(verdict["pass"])), judge_record
    raise KeyError(check)


def _failure_row(case_by_field: dict[str, str], rep: int, digest: str, failure_class: str, detail: object) -> dict[str, object]:
    return {"prompt_id": case_by_field["id"], "rep": rep, "failure_class": failure_class, "detail": detail, META_FIELD: {INSTALLED_DIGEST_FIELD: digest}}


def _run_one(case_by_field: dict[str, str], rep: int, variant_directory: Path, files_by_target: dict[str, str], settings: SessionSettings, is_direct: bool) -> None:
    workspace = prepare_workspace(files_by_target)
    try:
        session = run_session(workspace, case_by_field["prompt"], settings, is_direct)
    finally:
        remove_workspace(workspace)
    digest = installed_digest(files_by_target)
    failure = unscorable(session, settings)
    if failure is not None:
        append_row(variant_directory / ERRORS_FILE_NAME, _failure_row(case_by_field, rep, digest, *failure))
        return
    (variant_directory / TRACES_DIRECTORY_NAME / TRACE_FILE_TEMPLATE.format(case_id=case_by_field["id"], rep=rep)).write_text(
        json.dumps(trace_turns(case_by_field["prompt"], session.all_events), indent=JSON_INDENT), encoding="utf-8"
    )
    followed, grade_record = _grade(case_by_field, session, is_direct)
    if followed is None:
        append_row(variant_directory / ERRORS_FILE_NAME, _failure_row(case_by_field, rep, digest, FAILURE_JUDGE, grade_record))
        return
    append_row(variant_directory / RESULTS_FILE_NAME, _scored_row(case_by_field, rep, session, settings, followed, {**grade_record, INSTALLED_DIGEST_FIELD: digest}))


def _scored_row(case_by_field: dict[str, str], rep: int, session: SessionRun, settings: SessionSettings, is_followed: bool, meta_by_field: dict[str, object]) -> dict[str, object]:
    final_by_field = final_event(session.all_events) or {}
    all_calls = tool_calls(session.all_events)
    return {
        "prompt_id": case_by_field["id"],
        "rep": rep,
        "prompt": case_by_field["prompt"],
        "tags": [case_by_field["group"], case_by_field["rule"]],
        "stop_reason": final_by_field.get("subtype"),
        "status": STATUS_OK,
        "grade": {"followed": int(is_followed), "opened_guide": int(opened_a_guide(all_calls))},
        "model": settings.model,
        "served_models": served_models(final_by_field),
        "usage": final_by_field.get("usage"),
        "latency_s": round(session.latency_seconds, LATENCY_DECIMALS),
        "tool_calls": len(all_calls),
        "meta": {"first_tools": [each_call.name for each_call in all_calls[:FIRST_TOOLS_SHOWN]], "num_turns": final_by_field.get("num_turns"), **meta_by_field},
    }


def _summary(all_rows: list[dict[str, object]], error_count: int) -> str:
    passes_by_group: dict[str, list[int]] = defaultdict(list)
    for each_row in all_rows:
        passes_by_group[each_row["tags"][0]].append(each_row["grade"]["followed"])
    total_passes = sum(sum(each) for each in passes_by_group.values())
    low, high = wilson_interval(total_passes, len(all_rows))
    group_text = GROUP_SEPARATOR.join(f"{each_group} {sum(each)}/{len(each)}" for each_group, each in sorted(passes_by_group.items()))
    guide_opens = sum(each_row["grade"]["opened_guide"] for each_row in all_rows)
    return f"followed {total_passes}/{len(all_rows)} (95% CI {low:.2f}-{high:.2f}) | {group_text} | opened a guide {guide_opens}/{len(all_rows)} | errors {error_count}"


def main() -> int:
    """Run every pending (case, rep) for one variant and print the headline.

    Returns:
        Process exit status, zero once every pending run has finished.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    arguments = _parse_arguments()
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    try:
        variant = select_variant(state["variants"], arguments.variant)
        all_cases = select_cases(json.loads(CASES_FILE.read_text(encoding="utf-8")), arguments.cases)
    except ValueError as error:
        logger.error("%s", error)
        return USAGE_ERROR_EXIT_CODE
    files_by_target = variant_files(str(variant["ref"]))
    digest = installed_digest(files_by_target)
    all_case_ids = {each_case["id"] for each_case in all_cases}
    variant_directory = FLOW_ROOT / (arguments.label or arguments.variant)
    (variant_directory / TRACES_DIRECTORY_NAME).mkdir(parents=True, exist_ok=True)
    settings = SessionSettings(arguments.model, arguments.effort, arguments.max_turns, arguments.timeout_s)
    all_done = {(each_row["prompt_id"], each_row["rep"]) for each_row in rows_for_install(variant_directory / RESULTS_FILE_NAME, digest, all_case_ids)}
    all_pending = [(each_case, each_rep) for each_case in all_cases for each_rep in range(arguments.reps) if (each_case["id"], each_rep) not in all_done]
    with ThreadPoolExecutor(max_workers=arguments.parallel) as executor:
        for each_future in [executor.submit(_run_one, each_case, each_rep, variant_directory, files_by_target, settings, arguments.direct) for each_case, each_rep in all_pending]:
            each_future.result()
    all_rows = rows_for_install(variant_directory / RESULTS_FILE_NAME, digest, all_case_ids)
    all_errors = rows_for_install(variant_directory / ERRORS_FILE_NAME, digest, all_case_ids)
    logger.info("%s: %s", arguments.variant, _summary(all_rows, len(all_errors)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
