"""Run the rules-index cases as fresh sessions and grade each one.

::

    python3 run.py --variant baseline --cases w02,b02,s01,s02
    python3 run.py --variant index --cases w02,b02,s01,s02

Variant ``baseline`` installs the always-loaded rules and guides from the
commit before the index. Variant ``index`` installs them from ``HEAD``. Each
session loads project and local settings only, so the home config's rules,
hooks and skills stay out of both arms. Rows land in
``<variant>/results.jsonl`` as each case finishes, and a rerun skips every
(case, rep) already there.
"""

import argparse
import json
import logging
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

flow_directory = Path(__file__).resolve().parent
for each_import_root in (flow_directory, flow_directory.parent / "features-start-with-an-eval", flow_directory.parents[2] / "packages" / "claude-dev-env" / "scripts"):
    if str(each_import_root) not in sys.path:
        sys.path.insert(0, str(each_import_root))

from contrast_framing import find_contrast_framing
from rules_eval_support.config.constants import (
    ALL_SCORABLE_SUBTYPES,
    BROKER_WAIT_EXIT_CODE,
    CASES_FILE,
    CHECK_CONTRAST,
    CHECK_JUDGE,
    DEFAULT_EFFORT,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    DEFAULT_PARALLEL,
    DEFAULT_REPS,
    DEFAULT_TIMEOUT_SECONDS,
    ERRORS_FILE_NAME,
    FAILURE_BROKER_WAIT,
    FAILURE_JUDGE,
    FAILURE_MODEL_MISMATCH,
    FAILURE_NO_RESULT,
    FAILURE_TIMEOUT,
    FLOW_ROOT,
    JSON_INDENT,
    JUDGE_MODEL,
    LATENCY_DECIMALS,
    NEWLINE,
    RESULTS_FILE_NAME,
    STATE_FILE,
    STATUS_OK,
    TRACE_FILE_TEMPLATE,
    TRACES_DIRECTORY_NAME,
)
from rules_eval_support.grading import TOOL_CHECK_BY_NAME, opened_a_guide
from rules_eval_support.install import prepare_workspace, variant_files
from rules_eval_support.judge import judge_prompt, run_judge
from session_eval_support.grading import tool_calls, wilson_interval
from session_eval_support.session import (
    SessionRun,
    SessionSettings,
    final_event,
    run_session,
    served_models,
    trace_turns,
)

logger = logging.getLogger(__name__)
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
    return [json.loads(each_line) for each_line in path.read_text(encoding="utf-8").splitlines() if each_line]


def _append_line(path: Path, row_by_field: dict[str, object]) -> None:
    with write_lock, path.open("a", encoding="utf-8") as jsonl_file:
        jsonl_file.write(json.dumps(row_by_field) + NEWLINE)


def _unscorable(session: SessionRun, settings: SessionSettings) -> tuple[str, object] | None:
    if session.exit_code == BROKER_WAIT_EXIT_CODE:
        return FAILURE_BROKER_WAIT, session.broker_report.get("final_decision")
    if session.exit_code is None:
        return FAILURE_TIMEOUT, settings.timeout_seconds
    final = final_event(session.all_events)
    if final is None or final.get("subtype") not in ALL_SCORABLE_SUBTYPES:
        return FAILURE_NO_RESULT, None if final is None else final.get("subtype")
    if not any(each_model.startswith(settings.model) for each_model in served_models(final)):
        return FAILURE_MODEL_MISMATCH, served_models(final)
    return None


def _grade(case_by_field: dict[str, str], session: SessionRun) -> tuple[bool | None, dict[str, object]]:
    all_calls = tool_calls(session.all_events)
    check = case_by_field["check"]
    if check in TOOL_CHECK_BY_NAME:
        return TOOL_CHECK_BY_NAME[check](all_calls), {}
    final_text = str((final_event(session.all_events) or {}).get("result", ""))
    if check == CHECK_CONTRAST:
        all_hits = find_contrast_framing(final_text)
        return not all_hits, {"contrast_hits": all_hits}
    if check == CHECK_JUDGE:
        verdict, judge_event = run_judge(
            judge_prompt(case_by_field["prompt"], case_by_field["rubric"], trace_turns(case_by_field["prompt"], session.all_events))
        )
        judge_record = {"judge_model": JUDGE_MODEL, "judge_usage": judge_event.get("usage"), "judge_verdict": verdict}
        return (None if verdict is None else bool(verdict["pass"])), judge_record
    raise KeyError(check)


def _run_one(case_by_field: dict[str, str], rep: int, variant_directory: Path, files_by_target: dict[str, str], settings: SessionSettings) -> None:
    workspace = prepare_workspace(files_by_target)
    session = run_session(workspace, case_by_field["prompt"], settings)
    failure = _unscorable(session, settings)
    if failure is not None:
        _append_line(variant_directory / ERRORS_FILE_NAME, {"prompt_id": case_by_field["id"], "rep": rep, "failure_class": failure[0], "detail": failure[1]})
        return
    (variant_directory / TRACES_DIRECTORY_NAME / TRACE_FILE_TEMPLATE.format(case_id=case_by_field["id"], rep=rep)).write_text(
        json.dumps(trace_turns(case_by_field["prompt"], session.all_events), indent=JSON_INDENT), encoding="utf-8"
    )
    followed, grade_record = _grade(case_by_field, session)
    if followed is None:
        _append_line(variant_directory / ERRORS_FILE_NAME, {"prompt_id": case_by_field["id"], "rep": rep, "failure_class": FAILURE_JUDGE, "detail": grade_record})
        return
    final_by_field = final_event(session.all_events) or {}
    all_calls = tool_calls(session.all_events)
    _append_line(
        variant_directory / RESULTS_FILE_NAME,
        {
            "prompt_id": case_by_field["id"],
            "rep": rep,
            "prompt": case_by_field["prompt"],
            "tags": [case_by_field["group"], case_by_field["rule"]],
            "stop_reason": final_by_field.get("subtype"),
            "status": STATUS_OK,
            "grade": {"followed": int(followed), "opened_guide": int(opened_a_guide(all_calls))},
            "model": settings.model,
            "served_models": served_models(final_by_field),
            "usage": final_by_field.get("usage"),
            "latency_s": round(session.latency_seconds, LATENCY_DECIMALS),
            "tool_calls": len(all_calls),
            "meta": {"first_tools": [each_call.name for each_call in all_calls[:8]], "num_turns": final_by_field.get("num_turns"), **grade_record},
        },
    )


def _summary(all_rows: list[dict[str, object]], error_count: int) -> str:
    passes_by_group: dict[str, list[int]] = defaultdict(list)
    for each_row in all_rows:
        passes_by_group[each_row["tags"][0]].append(each_row["grade"]["followed"])
    total_passes = sum(sum(each) for each in passes_by_group.values())
    low, high = wilson_interval(total_passes, len(all_rows))
    group_text = ", ".join(f"{each_group} {sum(each)}/{len(each)}" for each_group, each in sorted(passes_by_group.items()))
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
    files_by_target = variant_files(state["variants"][arguments.variant]["ref"])
    all_wanted_ids = {each_id for each_id in arguments.cases.split(",") if each_id}
    all_cases = [each_case for each_case in json.loads(CASES_FILE.read_text(encoding="utf-8")) if not all_wanted_ids or each_case["id"] in all_wanted_ids]
    variant_directory = FLOW_ROOT / arguments.variant
    (variant_directory / TRACES_DIRECTORY_NAME).mkdir(parents=True, exist_ok=True)
    settings = SessionSettings(arguments.model, arguments.effort, arguments.max_turns, arguments.timeout_s)
    all_done = {(each_row["prompt_id"], each_row["rep"]) for each_row in _read_rows(variant_directory / RESULTS_FILE_NAME)}
    all_pending = [(each_case, each_rep) for each_case in all_cases for each_rep in range(arguments.reps) if (each_case["id"], each_rep) not in all_done]
    with ThreadPoolExecutor(max_workers=arguments.parallel) as executor:
        for each_future in [executor.submit(_run_one, each_case, each_rep, variant_directory, files_by_target, settings) for each_case, each_rep in all_pending]:
            each_future.result()
    all_rows = [each_row for each_row in _read_rows(variant_directory / RESULTS_FILE_NAME) if each_row["prompt_id"] in {each_case["id"] for each_case in all_cases}]
    logger.info("%s: %s", arguments.variant, _summary(all_rows, len(_read_rows(variant_directory / ERRORS_FILE_NAME))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
