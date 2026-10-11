"""Deny writes to eval files until the session has invoked /claude-api build-eval."""

from __future__ import annotations

import re
import sys
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.pr_lifecycle_skill_gate import is_build_eval_missing
from hooks_constants.build_eval_before_eval_write_gate_constants import (
    ALL_EVAL_DIRECTORY_NAMES,
    ALL_FILE_PATH_FIELDS,
    ALL_FILE_WRITE_TOOL_NAMES,
    EVAL_FILE_NAME_WORD_PATTERN,
    MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON,
)
from hooks_constants.hook_specific_output_keys import (
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
)
from hooks_constants.pr_lifecycle_skill_gate_constants import (
    DENY_DECISION,
    HOOK_EVENT_NAME,
    PATH_SEPARATOR_PATTERN,
    PERMISSION_DECISION_REASON_KEY,
)
from hooks_constants.pre_tool_use_stdin import print_decision_from_stdin


def is_eval_path(path: str) -> bool:
    """Return whether a path belongs to an eval.

    ::

        evals/cases.json                     -> True
        .claude/hillclimb/feature/run.py     -> True
        tools/eval_runner.py                 -> True
        tests/test_search.eval.json          -> True
        tools/search-evals.md                -> True
        build_eval_before_eval_write_gate.py -> False
        src/evaluate_score.py                -> False
        src/retrieval.py                     -> False

    Args:
        path: The file path the tool writes.
    """
    all_segments = [each for each in re.split(PATH_SEPARATOR_PATTERN, path.lower()) if each]
    if not all_segments:
        return False
    if any(each in ALL_EVAL_DIRECTORY_NAMES for each in all_segments[:-1]):
        return True
    return re.search(EVAL_FILE_NAME_WORD_PATTERN, all_segments[-1]) is not None


def _written_path(all_payload_fields: dict[str, object]) -> str | None:
    if all_payload_fields.get("tool_name") not in ALL_FILE_WRITE_TOOL_NAMES:
        return None
    tool_input = all_payload_fields.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    for each_field in ALL_FILE_PATH_FIELDS:
        path = tool_input.get(each_field)
        if isinstance(path, str) and path:
            return path
    return None


def decision_for(all_payload_fields: dict[str, object]) -> dict[str, object] | None:
    """Return a deny for an eval file write with no build-eval call, else None.

    ::

        Write evals/cases.json, no build-eval in transcript   -> deny
        Write evals/cases.json, build-eval in transcript      -> None
        Write src/app.py, no build-eval in transcript         -> None
        Write evals/cases.json, no readable transcript        -> None

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    path = _written_path(all_payload_fields)
    if path is None or not is_eval_path(path):
        return None
    if not is_build_eval_missing(all_payload_fields):
        return None
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            "hookEventName": HOOK_EVENT_NAME,
            PERMISSION_DECISION_KEY: DENY_DECISION,
            PERMISSION_DECISION_REASON_KEY: MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON,
        }
    }


def main() -> int:
    """Read one payload, print a deny when needed, and exit zero."""
    return print_decision_from_stdin(decision_for)


if __name__ == "__main__":
    sys.exit(main())
