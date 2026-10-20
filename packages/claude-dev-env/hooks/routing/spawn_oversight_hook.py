#!/usr/bin/env python3
"""PreToolUse hook: refuse a spawn brief without the user's outcome and a blocker clause.

Registered on every tool that starts another agent: ``Agent``, ``Task``,
``Workflow``, ``multi_agent_v1__spawn_agent``,
``mcp__hearthbot__start_thread_session``, ``mcp__hearthbot__start_rc_session``,
and ``mcp__hearthbot__start_remote_control``, plus a workflow dispatch whose
inputs carry a ``prompt`` for an agent. The brief needs an ``Outcome:`` line
and an ``On a blocker:`` clause, each with text after it, so the worker owns
the outcome and any route named is a default.

::

    Agent {"prompt": "Run X via RC."}            -> deny: no outcome, no blocker clause
    Agent {"prompt": "Outcome: ... On a blocker: ..."}
                                                 -> additionalContext: the directive
    Workflow {"name": "saved-review"}            -> additionalContext: the directive
    actions trigger {"method": "cancel_workflow_run"}
                                                 -> no output
    Bash {"command": "ls"}                       -> no output
    Agent "not an object"                        -> no output

A passing spawn gets the oversight directive, so the spawner owns the work it
delegates. Subagent and read-only helper spawns are checked the same way. A
``Workflow`` call with no script text, such as a saved or resumed run, passes
with the directive.
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
routing_directory = str(Path(__file__).resolve().parent)
if routing_directory not in sys.path:
    sys.path.insert(0, routing_directory)

from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
)
from hooks_constants.pre_tool_use_context_runner import run_context_hook
from hooks_constants.spawn_oversight_hook_constants import (
    ADDITIONAL_CONTEXT_KEY,
    ALL_BLOCKER_CLAUSE_MARKERS,
    ALL_OUTCOME_MARKERS,
    DENY_DECISION,
    MARKER_DECORATION_CHARACTERS,
    MISSING_BLOCKER_CLAUSE_REASON,
    MISSING_OUTCOME_REASON,
    PERMISSION_DECISION_REASON_KEY,
    PRE_TOOL_USE_EVENT_NAME,
    REASON_SEPARATOR,
    REFUSAL_PREFIX,
    REFUSAL_SUFFIX,
    SPAWN_OVERSIGHT_DIRECTIVE,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    WORKFLOW_TOOL_NAME,
)
from spawn_brief_text import spawn_brief_text


def has_marked_clause(brief: str, all_markers: tuple[str, ...]) -> bool:
    """Return True when a marker appears in the brief with text after it on its line.

    ::

        "Outcome: the test passes." , ("outcome:",)  -> True
        "- **Outcome:** the test passes."            -> True
        "Do X.\\nOutcome:\\nOn a blocker:"            -> False

    Args:
        brief: The text the spawn hands its agents.
        all_markers: Lowercase marker strings such as ``"outcome:"``.
    """
    return any(
        _has_text_after_marker(each_line, each_marker)
        for each_line in brief.lower().splitlines()
        for each_marker in all_markers
    )


def _has_text_after_marker(line: str, marker: str) -> bool:
    all_segments_after_marker = line.split(marker)[1:]
    return any(
        each_segment.strip(MARKER_DECORATION_CHARACTERS)
        for each_segment in all_segments_after_marker
    )


def brief_gaps(brief: str) -> list[str]:
    """Return the refusal reason for each required clause the brief lacks.

    ::

        "Run X on the PC via RC."                    -> [no outcome, no blocker clause]
        "Outcome: X is done. On a blocker: try ..."  -> []

    Args:
        brief: The text the spawn hands its agents.
    """
    all_gaps = []
    if not has_marked_clause(brief, ALL_OUTCOME_MARKERS):
        all_gaps.append(MISSING_OUTCOME_REASON)
    if not has_marked_clause(brief, ALL_BLOCKER_CLAUSE_MARKERS):
        all_gaps.append(MISSING_BLOCKER_CLAUSE_REASON)
    return all_gaps


def _directive_output() -> dict[str, object]:
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: PRE_TOOL_USE_EVENT_NAME,
            ADDITIONAL_CONTEXT_KEY: SPAWN_OVERSIGHT_DIRECTIVE,
        }
    }


def _deny_output(all_gaps: list[str]) -> dict[str, object]:
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: PRE_TOOL_USE_EVENT_NAME,
            PERMISSION_DECISION_KEY: DENY_DECISION,
            PERMISSION_DECISION_REASON_KEY: REASON_SEPARATOR.join(
                [REFUSAL_PREFIX, *all_gaps, REFUSAL_SUFFIX]
            ),
        }
    }


def decide_hook_output(all_hook_fields: dict[str, object]) -> dict[str, object] | None:
    """Return a deny for a brief that lacks a clause, the directive for one that passes.

    Args:
        all_hook_fields: The parsed PreToolUse payload.

    Returns:
        None for a call that spawns no agent, else the deny or the directive.
    """
    all_tool_input_fields = all_hook_fields.get(TOOL_INPUT_KEY)
    if not isinstance(all_tool_input_fields, dict):
        return None
    tool_name = all_hook_fields.get(TOOL_NAME_KEY)
    brief = spawn_brief_text(tool_name, all_tool_input_fields)
    if brief is None:
        return None
    if tool_name == WORKFLOW_TOOL_NAME and not brief:
        return _directive_output()
    all_gaps = brief_gaps(brief)
    if all_gaps:
        return _deny_output(all_gaps)
    return _directive_output()


def main() -> int:
    """Run the hook on the stdin payload; always 0."""
    return run_context_hook(decide_hook_output)


if __name__ == "__main__":
    sys.exit(main())
