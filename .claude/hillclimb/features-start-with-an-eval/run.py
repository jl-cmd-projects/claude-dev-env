"""Run the features-start-with-an-eval cases as fresh sessions and grade each one.

::

    python3 run.py --variant baseline --cases f01,n01,n02
    python3 run.py --variant v1 --cases f01,n01,n02

Each case runs once per rep in a new git workspace copied from ``fixture/``.
Variant ``baseline`` adds nothing. Variant ``v1`` installs the rule and its
guide into the workspace's ``.claude/`` folder. Each session loads project and
local settings only, so a rule installed in the home config stays out of both
arms. Rows land in
``<variant>/results.jsonl`` as each case finishes, each tagged with a digest
of the installed files. A rerun skips every (case, rep) already there under
the same digest, and the headline counts only those rows and errors.
"""

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from session_eval_support.config.constants import (
    CASES_FILE,
    DEFAULT_EFFORT,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    DEFAULT_PARALLEL,
    DEFAULT_REPS,
    DEFAULT_TIMEOUT_SECONDS,
    ERRORS_FILE_NAME,
    EXPECTED_BUILD_EVAL,
    FIRST_TOOLS_PER_TURN,
    FLOW_ROOT,
    INSTALLED_DIGEST_FIELD,
    LATENCY_DECIMALS,
    MILLISECONDS_PER_SECOND,
    RESULTS_FILE_NAME,
    SESSION_SETTING_SOURCES,
    STATE_FILE,
    STATUS_OK,
    TRACES_DIRECTORY_NAME,
    USAGE_ERROR_EXIT_CODE,
)
from session_eval_support.grading import (
    ToolCall,
    grade_case,
    tool_calls,
    wilson_interval,
)
from session_eval_support.rows import (
    append_row,
    failure_row,
    rows_for_install,
    select_cases,
    select_variant,
)
from session_eval_support.session import (
    SessionRun,
    SessionSettings,
    final_event,
    files_digest,
    installed_files,
    prepare_workspace,
    remove_workspace,
    run_session,
    served_models,
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
    return parser.parse_args()


def _row_meta(
    session: SessionRun,
    final_by_field: dict[str, object],
    all_calls: list[ToolCall],
    digest: str,
    settings: SessionSettings,
) -> dict[str, object]:
    permission_denials = final_by_field.get("permission_denials")
    decision = session.broker_report.get("final_decision")
    return {
        "first_tools": [
            each_call.name
            for each_call in all_calls[: settings.max_turns * FIRST_TOOLS_PER_TURN]
        ],
        "permission_denials": len(permission_denials)
        if isinstance(permission_denials, list)
        else 0,
        "num_turns": final_by_field.get("num_turns"),
        "duration_s": round(
            float(final_by_field.get("duration_ms") or 0) / MILLISECONDS_PER_SECOND,
            LATENCY_DECIMALS,
        ),
        "effort": settings.effort,
        "setting_sources": SESSION_SETTING_SOURCES,
        INSTALLED_DIGEST_FIELD: digest,
        "broker_account": decision.get("account")
        if isinstance(decision, dict)
        else None,
    }


def _scored_row(
    case_by_field: dict[str, str],
    rep: int,
    session: SessionRun,
    digest: str,
    settings: SessionSettings,
) -> dict[str, object]:
    final_by_field = final_event(session.all_events) or {}
    all_calls = tool_calls(session.all_events)
    return {
        "prompt_id": case_by_field["id"],
        "rep": rep,
        "prompt": case_by_field["prompt"],
        "tags": [case_by_field["group"], case_by_field["expected"]],
        "stop_reason": final_by_field.get("subtype"),
        "status": STATUS_OK,
        "grade": grade_case(case_by_field["expected"], all_calls),
        "model": settings.model,
        "served_models": served_models(final_by_field),
        "usage": final_by_field.get("usage"),
        "latency_s": round(session.latency_seconds, LATENCY_DECIMALS),
        "tool_calls": len(all_calls),
        "meta": _row_meta(session, final_by_field, all_calls, digest, settings),
    }


def _run_one(
    case_by_field: dict[str, str],
    rep: int,
    variant_directory: Path,
    bytes_by_target: dict[str, bytes],
    digest: str,
    settings: SessionSettings,
) -> None:
    workspace = prepare_workspace(bytes_by_target)
    try:
        session = run_session(workspace, case_by_field["prompt"], settings)
    finally:
        remove_workspace(workspace)
    failure = unscorable(session, settings)
    if failure is not None:
        append_row(
            variant_directory / ERRORS_FILE_NAME,
            failure_row(case_by_field, rep, digest, *failure),
        )
        return
    write_trace(case_by_field, rep, variant_directory, session)
    append_row(
        variant_directory / RESULTS_FILE_NAME,
        _scored_row(case_by_field, rep, session, digest, settings),
    )


def _summary_line(all_rows: list[dict[str, object]], error_count: int) -> str:
    all_feature = [
        each_row for each_row in all_rows if each_row["tags"][1] == EXPECTED_BUILD_EVAL
    ]
    all_other = [
        each_row for each_row in all_rows if each_row["tags"][1] != EXPECTED_BUILD_EVAL
    ]
    feature_passes = sum(each_row["grade"]["correct"] for each_row in all_feature)
    other_passes = sum(each_row["grade"]["correct"] for each_row in all_other)
    recall_low, recall_high = wilson_interval(feature_passes, len(all_feature))
    specificity_low, specificity_high = wilson_interval(other_passes, len(all_other))
    return (
        f"recall {feature_passes}/{len(all_feature)} (95% CI {recall_low:.2f}-{recall_high:.2f})"
        f" | specificity {other_passes}/{len(all_other)} (95% CI {specificity_low:.2f}-{specificity_high:.2f})"
        f" | errors {error_count}"
    )


def _pending_runs(
    all_cases: list[dict[str, str]], reps: int, variant_directory: Path, digest: str
) -> list[tuple[dict[str, str], int]]:
    all_case_ids = {each_case["id"] for each_case in all_cases}
    all_done = {
        (each_row["prompt_id"], each_row["rep"])
        for each_row in rows_for_install(
            variant_directory / RESULTS_FILE_NAME, digest, all_case_ids
        )
    }
    return [
        (each_case, each_rep)
        for each_case in all_cases
        for each_rep in range(reps)
        if (each_case["id"], each_rep) not in all_done
    ]


def _variant_summary(
    all_cases: list[dict[str, str]], variant_directory: Path, digest: str
) -> str:
    all_case_ids = {each_case["id"] for each_case in all_cases}
    all_rows = rows_for_install(variant_directory / RESULTS_FILE_NAME, digest, all_case_ids)
    all_errors = rows_for_install(variant_directory / ERRORS_FILE_NAME, digest, all_case_ids)
    return _summary_line(all_rows, len(all_errors))


def _run_pending(
    all_pending: list[tuple[dict[str, str], int]],
    variant_directory: Path,
    bytes_by_target: dict[str, bytes],
    digest: str,
    settings: SessionSettings,
    parallel: int,
) -> None:
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        for each_future in [
            executor.submit(
                _run_one,
                each_case,
                each_rep,
                variant_directory,
                bytes_by_target,
                digest,
                settings,
            )
            for each_case, each_rep in all_pending
        ]:
            each_future.result()


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
        all_cases = select_cases(
            json.loads(CASES_FILE.read_text(encoding="utf-8")), arguments.cases
        )
    except ValueError as error:
        logger.error("%s", error)
        return USAGE_ERROR_EXIT_CODE
    bytes_by_target = installed_files(
        [tuple(each_pair) for each_pair in variant["install"]]
    )
    digest = files_digest(bytes_by_target)
    variant_directory = FLOW_ROOT / arguments.variant
    (variant_directory / TRACES_DIRECTORY_NAME).mkdir(parents=True, exist_ok=True)
    settings = SessionSettings(
        arguments.model, arguments.effort, arguments.max_turns, arguments.timeout_s
    )
    _run_pending(
        _pending_runs(all_cases, arguments.reps, variant_directory, digest),
        variant_directory,
        bytes_by_target,
        digest,
        settings,
        arguments.parallel,
    )
    logger.info(
        "%s: %s",
        arguments.variant,
        _variant_summary(all_cases, variant_directory, digest),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
