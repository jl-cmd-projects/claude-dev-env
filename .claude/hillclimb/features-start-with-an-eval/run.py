"""Run the features-start-with-an-eval cases as fresh sessions and grade each one.

::

    python3 run.py --variant baseline --cases f01,n01,n02
    python3 run.py --variant v1 --cases f01,n01,n02

Each case runs once per rep in a new git workspace copied from ``fixture/``.
Variant ``baseline`` adds nothing. Variant ``v1`` installs the rule and its
guide into the workspace's ``.claude/`` folder. Rows land in
``<variant>/results.jsonl`` as each case finishes, and a rerun skips every
(case, rep) already there.
"""

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from session_eval_support.config.constants import (
    ALL_SCORABLE_SUBTYPES,
    BROKER_WAIT_EXIT_CODE,
    CASES_FILE,
    DEFAULT_EFFORT,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    DEFAULT_PARALLEL,
    DEFAULT_REPS,
    DEFAULT_TIMEOUT_SECONDS,
    ERRORS_FILE_NAME,
    EXPECTED_BUILD_EVAL,
    FAILURE_BROKER_WAIT,
    FAILURE_MODEL_MISMATCH,
    FAILURE_NO_RESULT,
    FAILURE_TIMEOUT,
    FLOW_ROOT,
    JSON_INDENT,
    LATENCY_DECIMALS,
    MILLISECONDS_PER_SECOND,
    RESULTS_FILE_NAME,
    STATE_FILE,
    STATUS_OK,
    TRACE_FILE_TEMPLATE,
    TRACES_DIRECTORY_NAME,
)
from session_eval_support.grading import grade_case, tool_calls, wilson_interval
from session_eval_support.session import (
    SessionSettings,
    installed_files_digest,
    prepare_workspace,
    result_event,
    run_session,
    served_models,
    trace_turns,
)

write_lock = threading.Lock()


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


def _read_rows(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    return [
        json.loads(each_line)
        for each_line in path.read_text(encoding="utf-8").splitlines()
        if each_line
    ]


def _append_line(path: Path, record: dict[str, object]) -> None:
    with write_lock, path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record) + "\n")


def _failure(
    case: dict[str, str], rep: int, failure_class: str, detail: object
) -> dict[str, object]:
    return {
        "prompt_id": case["id"],
        "rep": rep,
        "failure_class": failure_class,
        "detail": detail,
    }


def _run_one(
    case: dict[str, str],
    rep: int,
    variant_directory: Path,
    all_installs: list[tuple[str, str]],
    settings: SessionSettings,
) -> None:
    workspace = prepare_workspace(all_installs)
    session = run_session(workspace, case["prompt"], settings)
    errors_path = variant_directory / ERRORS_FILE_NAME
    decision = session.broker_report.get("final_decision")
    if session.exit_code == BROKER_WAIT_EXIT_CODE:
        _append_line(errors_path, _failure(case, rep, FAILURE_BROKER_WAIT, decision))
        return
    if session.exit_code is None:
        _append_line(
            errors_path, _failure(case, rep, FAILURE_TIMEOUT, settings.timeout_seconds)
        )
        return
    result = result_event(session.all_events)
    if result is None or result.get("subtype") not in ALL_SCORABLE_SUBTYPES:
        _append_line(
            errors_path,
            _failure(
                case,
                rep,
                FAILURE_NO_RESULT,
                None if result is None else result.get("subtype"),
            ),
        )
        return
    all_served = served_models(result)
    if not any(each_model.startswith(settings.model) for each_model in all_served):
        _append_line(
            errors_path, _failure(case, rep, FAILURE_MODEL_MISMATCH, all_served)
        )
        return
    all_calls = tool_calls(session.all_events)
    trace_path = (
        variant_directory
        / TRACES_DIRECTORY_NAME
        / TRACE_FILE_TEMPLATE.format(case_id=case["id"], rep=rep)
    )
    trace_path.write_text(
        json.dumps(trace_turns(case["prompt"], session.all_events), indent=JSON_INDENT),
        encoding="utf-8",
    )
    permission_denials = result.get("permission_denials")
    row = {
        "prompt_id": case["id"],
        "rep": rep,
        "prompt": case["prompt"],
        "tags": [case["group"], case["expected"]],
        "stop_reason": result.get("subtype"),
        "status": STATUS_OK,
        "grade": grade_case(case["expected"], all_calls),
        "model": settings.model,
        "served_models": all_served,
        "usage": result.get("usage"),
        "latency_s": round(session.latency_seconds, LATENCY_DECIMALS),
        "tool_calls": len(all_calls),
        "meta": {
            "first_tools": [
                each_call.name for each_call in all_calls[: settings.max_turns * 2]
            ],
            "permission_denials": len(permission_denials)
            if isinstance(permission_denials, list)
            else 0,
            "num_turns": result.get("num_turns"),
            "duration_s": round(
                float(result.get("duration_ms") or 0) / MILLISECONDS_PER_SECOND,
                LATENCY_DECIMALS,
            ),
            "effort": settings.effort,
            "installed_digest": installed_files_digest(all_installs),
            "broker_account": decision.get("account")
            if isinstance(decision, dict)
            else None,
        },
    }
    _append_line(variant_directory / RESULTS_FILE_NAME, row)


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


def main() -> int:
    """Run every pending (case, rep) for one variant and print the headline."""
    arguments = _parse_arguments()
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    all_installs = [
        tuple(each_pair)
        for each_pair in state["variants"][arguments.variant]["install"]
    ]
    all_wanted_ids = {each_id for each_id in arguments.cases.split(",") if each_id}
    all_cases = [
        each_case
        for each_case in json.loads(CASES_FILE.read_text(encoding="utf-8"))
        if not all_wanted_ids or each_case["id"] in all_wanted_ids
    ]
    variant_directory = FLOW_ROOT / arguments.variant
    (variant_directory / TRACES_DIRECTORY_NAME).mkdir(parents=True, exist_ok=True)
    all_done = {
        (each_row["prompt_id"], each_row["rep"])
        for each_row in _read_rows(variant_directory / RESULTS_FILE_NAME)
    }
    all_pending = [
        (each_case, each_rep)
        for each_case in all_cases
        for each_rep in range(arguments.reps)
        if (each_case["id"], each_rep) not in all_done
    ]
    settings = SessionSettings(
        arguments.model, arguments.effort, arguments.max_turns, arguments.timeout_s
    )
    with ThreadPoolExecutor(max_workers=arguments.parallel) as executor:
        for each_future in [
            executor.submit(
                _run_one, each_case, each_rep, variant_directory, all_installs, settings
            )
            for each_case, each_rep in all_pending
        ]:
            each_future.result()
    all_wanted = {each_case["id"] for each_case in all_cases}
    all_rows = [
        each_row
        for each_row in _read_rows(variant_directory / RESULTS_FILE_NAME)
        if each_row["prompt_id"] in all_wanted
    ]
    error_count = len(_read_rows(variant_directory / ERRORS_FILE_NAME))
    print(f"{arguments.variant}: {_summary_line(all_rows, error_count)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
