"""Run the subagent-effort-routing cases as fresh sessions and grade each one.

::

    python3 run.py --variant baseline
    python3 run.py --variant v1 --cases o01,n01

Each case runs once per rep in a new git workspace copied from the shared
fixture project. The parent session runs on Opus at high, with Agent, Task,
Read, Grep and Glob allowed, and loads project and local settings only.
Variant ``baseline`` adds nothing. Variant ``v1`` installs the rule and its
guide and registers the routing hook in the workspace's
``.claude/settings.json``.

Each spawned child's real model and effort come from its own transcript under
``~/.claude/projects/*/<session id>/subagents/``. Rows land in
``<variant>/results.jsonl`` with a run digest, and a rerun skips every
(case, rep) already stored under the same digest.
"""

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)
shared_flow_directory = str(Path(__file__).resolve().parent.parent / "features-start-with-an-eval")
if shared_flow_directory not in sys.path:
    sys.path.insert(0, shared_flow_directory)

from routing_eval_support import grading as routing_grading
from routing_eval_support.config.constants import (
    ALL_EXTRA_SESSION_WORDS,
    ALL_RATE_METRIC_IDS,
    CASES_FILE,
    CLAUDE_PROJECTS_DIRECTORY,
    COMMAND_HOOK_TYPE,
    DEFAULT_EFFORT,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    DEFAULT_PARALLEL,
    DEFAULT_REPS,
    DEFAULT_TIMEOUT_SECONDS,
    EFFORT_INPUT_KEY,
    FAILURE_NO_CHILD_TRANSCRIPT,
    FLOW_ROOT,
    HOOK_COMMAND_TEMPLATE,
    HOOK_EVENT_NAME,
    ALL_HOOK_SOURCE_PATHS,
    HOOK_TIMEOUT_SECONDS,
    JSON_INDENT,
    MODEL_INPUT_KEY,
    REPOSITORY_ROOT,
    SPAWNED_METRIC_ID,
    STATE_FILE,
    SUMMARY_SEPARATOR,
    WORKSPACE_SETTINGS_TARGET,
)
from routing_eval_support.grading import (
    ChildRun,
    child_runs,
    grade_case,
    routed_count,
    session_id,
    spawn_calls,
)
from session_eval_support.config.constants import (
    ERRORS_FILE_NAME,
    LATENCY_DECIMALS,
    RESULTS_FILE_NAME,
    RUN_DIGEST_FIELD,
    SESSION_SETTING_SOURCES,
    STATUS_OK,
    TRACES_DIRECTORY_NAME,
    USAGE_ERROR_EXIT_CODE,
)
from session_eval_support import grading as session_grading
from session_eval_support.grading import tool_calls, wilson_interval
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
    prepare_workspace,
    remove_workspace,
    run_digest,
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


def unbrokered_words(report_path: Path, all_claude_words: list[str]) -> list[str]:
    """Return the claude command with this eval's tool and hook-event flags.

    Args:
        report_path: Unused; there is no broker here.
        all_claude_words: The claude command and its arguments.
    """
    del report_path
    return [*all_claude_words, *ALL_EXTRA_SESSION_WORDS]


def _command_hook(hook_path: Path) -> dict[str, object]:
    return {
        "type": COMMAND_HOOK_TYPE,
        "command": HOOK_COMMAND_TEMPLATE.format(hook_path=hook_path),
        "timeout": HOOK_TIMEOUT_SECONDS,
    }


def hook_settings_bytes(all_hooks: list[list[str]]) -> dict[str, bytes]:
    """Return the workspace settings file that registers a variant's hooks.

    ::

        [] -> {}
        [["Agent|Task", "packages/.../hook.py"]] -> {".claude/settings.json": b'{"hooks": ...}'}

    Args:
        all_hooks: Pairs of a PreToolUse matcher and a hook script's repository path.

    Returns:
        The settings file keyed by its workspace path, or an empty map.
    """
    if not all_hooks:
        return {}
    all_entries = [
        {"matcher": each_matcher, "hooks": [_command_hook(REPOSITORY_ROOT / each_path)]}
        for each_matcher, each_path in all_hooks
    ]
    settings_text = json.dumps({"hooks": {HOOK_EVENT_NAME: all_entries}}, indent=JSON_INDENT)
    return {WORKSPACE_SETTINGS_TARGET: settings_text.encode("utf-8")}


def _child_summary(child: ChildRun) -> dict[str, object]:
    return {
        "tool_use_id": child.tool_use_id,
        "agent_type": child.agent_type,
        "pairs": sorted({f"{each_model}@{each_effort}" for each_model, each_effort in child.all_pairs}),
        "in_rule": routing_grading.child_in_rule(child),
    }


def _row_meta(session: SessionRun, all_children: list[ChildRun], digest: str) -> dict[str, object]:
    final_by_field = final_event(session.all_events) or {}
    all_spawns = spawn_calls(tool_calls(session.all_events))
    return {
        "spawns": [
            {
                "model": each_call.tool_input.get(MODEL_INPUT_KEY),
                "effort": each_call.tool_input.get(EFFORT_INPUT_KEY),
                "named_in_rule": routing_grading.named_in_rule(each_call),
            }
            for each_call in all_spawns
        ],
        "children": [_child_summary(each_child) for each_child in all_children],
        "routed_spawns": routed_count(session.all_events),
        "cost_usd": final_by_field.get("total_cost_usd"),
        "setting_sources": SESSION_SETTING_SOURCES,
        RUN_DIGEST_FIELD: digest,
    }


def _scored_row(
    case_by_field: dict[str, str],
    rep: int,
    session: SessionRun,
    all_children: list[ChildRun],
    digest: str,
    settings: SessionSettings,
) -> dict[str, object]:
    final_by_field = final_event(session.all_events) or {}
    all_calls = tool_calls(session.all_events)
    return {
        "prompt_id": case_by_field["id"],
        "rep": rep,
        "prompt": case_by_field["prompt"],
        "tags": [case_by_field["group"]],
        "stop_reason": final_by_field.get("subtype"),
        "status": STATUS_OK,
        "grade": grade_case(spawn_calls(all_calls), all_children, routed_count(session.all_events)),
        "model": settings.model,
        "served_models": served_models(final_by_field),
        "usage": final_by_field.get("usage"),
        "latency_s": round(session.latency_seconds, LATENCY_DECIMALS),
        "tool_calls": len(all_calls),
        "meta": _row_meta(session, all_children, digest),
    }


def session_children(session: SessionRun) -> list[ChildRun]:
    """Return the child agents a finished session started.

    Args:
        session: What the session left behind.
    """
    found_id = session_id(session.all_events)
    return [] if found_id is None else child_runs(CLAUDE_PROJECTS_DIRECTORY, found_id)


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
        session = run_session(workspace, case_by_field["prompt"], settings, unbrokered_words)
    finally:
        remove_workspace(workspace)
    all_children = session_children(session)
    failure = unscorable(session, settings)
    if failure is None and spawn_calls(tool_calls(session.all_events)) and not all_children:
        failure = FAILURE_NO_CHILD_TRANSCRIPT, session_id(session.all_events)
    if failure is not None:
        append_row(variant_directory / ERRORS_FILE_NAME, failure_row(case_by_field, rep, digest, *failure))
        return
    write_trace(case_by_field, rep, variant_directory, session)
    append_row(
        variant_directory / RESULTS_FILE_NAME,
        _scored_row(case_by_field, rep, session, all_children, digest, settings),
    )


def _rate_text(all_rows: list[dict[str, object]], metric_id: str) -> str:
    passes = sum(each_row["grade"][metric_id] for each_row in all_rows)
    low, high = wilson_interval(passes, len(all_rows))
    return f"{metric_id} {passes}/{len(all_rows)} (95% CI {low:.2f}-{high:.2f})"


def summary_lines(all_rows: list[dict[str, object]], error_count: int) -> list[str]:
    """Return the headline and one line per case group.

    The spawn rate counts every row. The other rates count only rows that
    spawned, since a session with no spawn has nothing to route.

    Args:
        all_rows: The scored rows of one variant and digest.
        error_count: Errors no retry has scored.

    Returns:
        One line for all rows, one per group, then the error count.
    """
    all_groups = sorted({each_row["tags"][0] for each_row in all_rows})
    all_lines = []
    for each_group in [None, *all_groups]:
        all_group_rows = [each_row for each_row in all_rows if each_group in (None, each_row["tags"][0])]
        all_spawning = [each_row for each_row in all_group_rows if each_row["grade"][SPAWNED_METRIC_ID]]
        all_parts = [_rate_text(all_group_rows, SPAWNED_METRIC_ID)]
        all_parts.extend(_rate_text(all_spawning, each_metric) for each_metric in ALL_RATE_METRIC_IDS)
        all_lines.append(f"{each_group or 'all'}: " + SUMMARY_SEPARATOR.join(all_parts))
    all_lines.append(f"errors {error_count}")
    return all_lines


def _pending_runs(
    all_cases: list[dict[str, str]], reps: int, variant_directory: Path, digest: str
) -> list[tuple[dict[str, str], int]]:
    all_case_ids = {each_case["id"] for each_case in all_cases}
    all_done = {
        (each_row["prompt_id"], each_row["rep"])
        for each_row in rows_for_install(variant_directory / RESULTS_FILE_NAME, digest, all_case_ids)
    }
    return [
        (each_case, each_rep)
        for each_case in all_cases
        for each_rep in range(reps)
        if (each_case["id"], each_rep) not in all_done
    ]


def _variant_summary(all_cases: list[dict[str, str]], variant_directory: Path, digest: str) -> list[str]:
    all_case_ids = {each_case["id"] for each_case in all_cases}
    all_rows = rows_for_install(variant_directory / RESULTS_FILE_NAME, digest, all_case_ids)
    all_errors = rows_for_install(variant_directory / ERRORS_FILE_NAME, digest, all_case_ids)
    return summary_lines(all_rows, len(open_errors(all_errors, all_rows)))


def _run_pending(
    all_pending: list[tuple[dict[str, str], int]],
    variant_directory: Path,
    bytes_by_target: dict[str, bytes],
    digest: str,
    settings: SessionSettings,
    parallel: int,
) -> None:
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        all_futures = [
            executor.submit(_run_one, each_case, each_rep, variant_directory, bytes_by_target, digest, settings)
            for each_case, each_rep in all_pending
        ]
        try:
            for each_future in all_futures:
                each_future.result()
        finally:
            for each_future in all_futures:
                each_future.cancel()


def _variant_inputs(all_variant_lists: dict[str, list], settings: SessionSettings) -> tuple[dict[str, bytes], str]:
    bytes_by_target = {
        **installed_files([tuple(each_pair) for each_pair in all_variant_lists["install"]]),
        **hook_settings_bytes(all_variant_lists["hooks"]),
    }
    all_hook_paths = [REPOSITORY_ROOT / each_hook[1] for each_hook in all_variant_lists["hooks"]]
    if all_hook_paths:
        all_hook_paths.extend(REPOSITORY_ROOT / each_path for each_path in ALL_HOOK_SOURCE_PATHS)
    all_harness = harness_sources(
        Path(routing_grading.__file__).parent,
        Path(session_grading.__file__).parent,
        Path(__file__),
        *all_hook_paths,
    )
    return bytes_by_target, run_digest(bytes_by_target, asdict(settings), all_harness)


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
    settings = SessionSettings(arguments.model, arguments.effort, arguments.max_turns, arguments.timeout_s)
    bytes_by_target, digest = _variant_inputs(variant, settings)
    variant_directory = FLOW_ROOT / arguments.variant
    (variant_directory / TRACES_DIRECTORY_NAME).mkdir(parents=True, exist_ok=True)
    all_pending = _pending_runs(all_cases, arguments.reps, variant_directory, digest)
    _run_pending(all_pending, variant_directory, bytes_by_target, digest, settings, arguments.parallel)
    for each_line in _variant_summary(all_cases, variant_directory, digest):
        logger.info("%s: %s", arguments.variant, each_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
