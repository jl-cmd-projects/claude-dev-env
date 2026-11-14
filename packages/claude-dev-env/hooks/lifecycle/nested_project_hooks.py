#!/usr/bin/env python3
"""SessionStart, UserPromptSubmit, and PreToolUse hook: run nested checkout hooks.

Claude Code reads project hooks from ``<project>/.claude/settings.json`` of the
directory a session starts in. A cloud session that holds several repository
checkouts starts in their parent directory, which has no settings of its own,
and ``--add-dir`` loads no hooks from the checkouts. Their start hooks, prompt
hooks, and tool guards then never run. This hook runs them::

    session directory (no .git, no .claude/settings.json)
    |-- checkout-a/.claude/settings.json   hooks run with CLAUDE_PROJECT_DIR=checkout-a
    `-- checkout-b/.claude/settings.json   hooks run with CLAUDE_PROJECT_DIR=checkout-b

Each child hook receives the same stdin payload, runs inside its checkout, and
keeps its own matcher and timeout. A child ``exit 2`` blocks the tool call and a
child ``deny``, else a child ``ask``, passes through, a ``deny`` carrying every
refusing child's reason; a child ``allow`` is dropped,
so no child widens permissions for the session. The ``additionalContext`` of
every child, at SessionStart, UserPromptSubmit, and PreToolUse, joins into one
``additionalContext``.

All children of one event share a run budget 2 seconds under that event's
registration: 118 seconds at PreToolUse and UserPromptSubmit, 1798 at
SessionStart. A child gets the smaller of its own timeout and the time left,
and a child with no time left does not start. Each child that does not start
or is stopped writes one line to stderr and adds nothing, so a spent budget
never denies a call by itself.

When the session directory is itself a checkout or holds its own settings,
Claude Code already runs those hooks, and this hook exits at once.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

_hooks_dir = str(Path(__file__).resolve().parent.parent)
if _hooks_dir not in sys.path:
    sys.path.insert(0, _hooks_dir)

from hooks_constants.nested_project_hooks_constants import (
    ADDITIONAL_CONTEXT_KEY,
    ALL_FORWARDED_PERMISSION_DECISIONS,
    BLOCKING_EXIT_CODE,
    CONTEXT_SECTION_SEPARATOR,
    DENY_PERMISSION_DECISION,
    HOOK_EVENT_NAME_KEY,
    ALL_MATCH_TARGET_KEYS_BY_EVENT,
    PRE_TOOL_USE_EVENT,
    PROJECT_DIRECTORY_ENVIRONMENT_VARIABLE,
    ALL_RUN_BUDGET_SECONDS_BY_EVENT,
    CUT_OFF_CHILD_LINE_TEMPLATE,
    NOT_STARTED_OUTCOME,
    STOPPED_OUTCOME_TEMPLATE,
    SESSION_START_EVENT,
    SHELL_COMMAND_FLAG,
    ALL_SHELL_PROGRAM_NAMES,
)
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY as HOOK_EVENT_NAME_OUTPUT_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
    PERMISSION_DECISION_REASON_KEY,
)
from hooks_constants.hook_time_budget import call_timeout, time_budget
from hooks_constants.subprocess_window import hidden_window_creation_flags
from lifecycle.nested_project_hooks_discovery import NestedHook, collect_nested_hooks


@dataclass(frozen=True)
class HookVerdict:
    """What this hook hands back to Claude Code."""

    exit_code: int
    stdout_text: str
    stderr_text: str


def _shell_program() -> str | None:
    for each_name in ALL_SHELL_PROGRAM_NAMES:
        found_path = shutil.which(each_name)
        if found_path:
            return found_path
    return None


def _hook_environment(project_directory: Path) -> dict[str, str]:
    return {**os.environ, PROJECT_DIRECTORY_ENVIRONMENT_VARIABLE: str(project_directory)}


def run_nested_hook(
    nested_hook: NestedHook, payload_text: str
) -> subprocess.CompletedProcess[str] | None:
    """Run one nested hook the way Claude Code would run it in its own checkout.

    Args:
        nested_hook: The hook to run.
        payload_text: The stdin payload Claude Code handed this hook.

    Returns:
        The completed process, or None when no shell exists, the command
        cannot start, it outlives its timeout, or the run budget is spent.
    """
    shell_program = _shell_program()
    if shell_program is None:
        return None
    timeout_seconds = call_timeout(nested_hook.timeout_seconds)
    if timeout_seconds is None:
        _write_cut_off_line(nested_hook, NOT_STARTED_OUTCOME)
        return None
    try:
        return subprocess.run(
            [shell_program, SHELL_COMMAND_FLAG, nested_hook.command],
            input=payload_text,
            capture_output=True,
            text=True,
            cwd=nested_hook.project_directory,
            env=_hook_environment(nested_hook.project_directory),
            timeout=timeout_seconds,
            check=False,
            creationflags=hidden_window_creation_flags(),
        )
    except subprocess.TimeoutExpired:
        _write_cut_off_line(nested_hook, STOPPED_OUTCOME_TEMPLATE.format(seconds=timeout_seconds))
        return None
    except OSError:
        return None


def _write_cut_off_line(nested_hook: NestedHook, outcome: str) -> None:
    sys.stderr.write(
        CUT_OFF_CHILD_LINE_TEMPLATE.format(
            checkout=nested_hook.project_directory.name,
            command=nested_hook.command,
            outcome=outcome,
        )
    )


def _parsed_hook_output(stdout_text: str) -> dict[str, object] | None:
    try:
        parsed_output = json.loads(stdout_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed_output, dict):
        return None
    return parsed_output


def _permission_decision(all_output_fields: dict[str, object]) -> object:
    specific_output = all_output_fields.get(HOOK_SPECIFIC_OUTPUT_KEY)
    if not isinstance(specific_output, dict):
        return None
    return specific_output.get(PERMISSION_DECISION_KEY)


def _deny_reason(all_output_fields: dict[str, object]) -> str:
    if _permission_decision(all_output_fields) != DENY_PERMISSION_DECISION:
        return ""
    specific_output = all_output_fields.get(HOOK_SPECIFIC_OUTPUT_KEY)
    reason = (
        specific_output.get(PERMISSION_DECISION_REASON_KEY)
        if isinstance(specific_output, dict)
        else None
    )
    return reason.strip() if isinstance(reason, str) else ""


def _joined_reasons(all_reasons: Iterable[str]) -> str:
    return CONTEXT_SECTION_SEPARATOR.join(dict.fromkeys(_non_empty_sections(all_reasons)))


def pre_tool_use_verdict(
    all_results: list[subprocess.CompletedProcess[str]],
) -> HookVerdict:
    """Fold nested PreToolUse results into the one verdict Claude Code reads.

    Claude Code shows one reason per refused call, so every refusing child's
    reason travels in that one reason::

        alpha exits 2 "no tests", beta denies "no link"  -> exit 2, both reasons
        alpha denies "no link", beta denies "too long"   -> deny, both reasons
        alpha asks, beta denies "no link"                -> deny, "no link"

    Args:
        all_results: The completed nested hooks, in run order.

    Returns:
        A blocking exit when any child exits 2, its stderr holding every
        exit-2 child's stderr and every child ``deny`` reason; else the first
        child ``deny`` output, its reason holding every child ``deny``
        reason, or with no ``deny`` the first child ``ask`` output, either
        carrying one copy of each distinct child ``additionalContext``; else
        a pass carrying that context, else an empty pass.
    """
    all_parsed_outputs = [
        _parsed_hook_output(each_result.stdout)
        for each_result in all_results
        if each_result.returncode == 0
    ]
    all_parsed_outputs = [each_output for each_output in all_parsed_outputs if each_output is not None]
    all_deny_reasons = [_deny_reason(each_output) for each_output in all_parsed_outputs]
    all_blocking_stderr = [
        each_result.stderr.strip()
        for each_result in all_results
        if each_result.returncode == BLOCKING_EXIT_CODE
    ]
    if all_blocking_stderr:
        return HookVerdict(
            BLOCKING_EXIT_CODE, "", _joined_reasons([*all_blocking_stderr, *all_deny_reasons])
        )
    all_context_sections = _non_empty_sections(
        _json_additional_context(each_parsed_output) for each_parsed_output in all_parsed_outputs
    )
    all_distinct_context_sections = list(dict.fromkeys(all_context_sections))
    joined_context = CONTEXT_SECTION_SEPARATOR.join(all_distinct_context_sections)
    for each_decision in ALL_FORWARDED_PERMISSION_DECISIONS:
        for each_parsed_output in all_parsed_outputs:
            if _permission_decision(each_parsed_output) != each_decision:
                continue
            decision_output = dict(each_parsed_output)
            decision_specific_output = dict(decision_output[HOOK_SPECIFIC_OUTPUT_KEY])
            if joined_context:
                decision_specific_output[ADDITIONAL_CONTEXT_KEY] = joined_context
            joined_deny_reasons = _joined_reasons(all_deny_reasons)
            if each_decision == DENY_PERMISSION_DECISION and joined_deny_reasons:
                decision_specific_output[PERMISSION_DECISION_REASON_KEY] = joined_deny_reasons
            decision_output[HOOK_SPECIFIC_OUTPUT_KEY] = decision_specific_output
            return HookVerdict(0, json.dumps(decision_output), "")
    if not joined_context:
        return HookVerdict(0, "", "")
    hook_output = {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_OUTPUT_KEY: PRE_TOOL_USE_EVENT,
            ADDITIONAL_CONTEXT_KEY: joined_context,
        }
    }
    return HookVerdict(0, json.dumps(hook_output), "")


def _json_additional_context(all_output_fields: dict[str, object]) -> str:
    specific_output = all_output_fields.get(HOOK_SPECIFIC_OUTPUT_KEY)
    if not isinstance(specific_output, dict):
        return ""
    context_text = specific_output.get(ADDITIONAL_CONTEXT_KEY)
    return context_text.strip() if isinstance(context_text, str) else ""


def _session_start_context(stdout_text: str) -> str:
    parsed_output = _parsed_hook_output(stdout_text)
    if parsed_output is None:
        return stdout_text.strip()
    return _json_additional_context(parsed_output)


def _non_empty_sections(all_sections: Iterable[str]) -> list[str]:
    return [each_section for each_section in all_sections if each_section]


def additional_context_verdict(
    all_results: list[subprocess.CompletedProcess[str]],
    event_name: str,
) -> HookVerdict:
    """Join nested hook output into one additional-context block.

    Args:
        all_results: The completed nested hooks, in run order.
        event_name: The envelope event name Claude Code expects.

    Returns:
        A pass whose stdout carries every child's context, or an empty pass
        when no child printed any.
    """
    all_context_sections = _non_empty_sections(
        _session_start_context(each_result.stdout) for each_result in all_results
    )
    stderr_text = CONTEXT_SECTION_SEPARATOR.join(
        _non_empty_sections(each_result.stderr.strip() for each_result in all_results)
    )
    if not all_context_sections:
        return HookVerdict(0, "", stderr_text)
    hook_output = {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_OUTPUT_KEY: event_name,
            ADDITIONAL_CONTEXT_KEY: CONTEXT_SECTION_SEPARATOR.join(all_context_sections),
        }
    }
    return HookVerdict(0, json.dumps(hook_output), stderr_text)


def session_start_verdict(
    all_results: list[subprocess.CompletedProcess[str]],
) -> HookVerdict:
    """Join nested SessionStart output into one additional-context block."""
    return additional_context_verdict(all_results, SESSION_START_EVENT)


def _completed_results(
    all_nested_hooks: list[NestedHook], payload_text: str
) -> list[subprocess.CompletedProcess[str]]:
    all_outcomes = (run_nested_hook(each_hook, payload_text) for each_hook in all_nested_hooks)
    return [each_outcome for each_outcome in all_outcomes if each_outcome is not None]


def forward_nested_hooks(session_directory: Path, payload_text: str) -> HookVerdict:
    """Run the nested checkouts' hooks for one payload and fold their results.

    Args:
        session_directory: The directory the session started in.
        payload_text: The stdin payload Claude Code handed this hook.

    Returns:
        The verdict for Claude Code. An empty pass for an unreadable payload
        or an event this hook does not forward.
    """
    payload = _parsed_hook_output(payload_text)
    if payload is None:
        return HookVerdict(0, "", "")
    event_name = payload.get(HOOK_EVENT_NAME_KEY)
    if not isinstance(event_name, str) or event_name not in ALL_MATCH_TARGET_KEYS_BY_EVENT:
        return HookVerdict(0, "", "")
    match_target = payload.get(ALL_MATCH_TARGET_KEYS_BY_EVENT[event_name])
    all_nested_hooks = collect_nested_hooks(
        session_directory, event_name, match_target if isinstance(match_target, str) else ""
    )
    with time_budget(ALL_RUN_BUDGET_SECONDS_BY_EVENT[event_name]):
        all_results = _completed_results(all_nested_hooks, payload_text)
    if event_name == PRE_TOOL_USE_EVENT:
        return pre_tool_use_verdict(all_results)
    return additional_context_verdict(all_results, event_name)


def main() -> None:
    """Entry point: read the payload, forward it, and exit with the verdict."""
    session_directory_text = os.environ.get(PROJECT_DIRECTORY_ENVIRONMENT_VARIABLE)
    if not session_directory_text:
        sys.exit(0)
    payload_text = sys.stdin.read()
    verdict = forward_nested_hooks(Path(session_directory_text), payload_text)
    if verdict.stdout_text:
        sys.stdout.write(verdict.stdout_text)
    if verdict.stderr_text:
        sys.stderr.write(verdict.stderr_text)
    sys.exit(verdict.exit_code)


if __name__ == "__main__":
    main()
