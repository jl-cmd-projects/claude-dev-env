"""Deny writes to eval files until the session has invoked /claude-api build-eval."""

from __future__ import annotations

import posixpath
import re
import sys
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.codex_apply_patch import payload_patch_target_paths
from blocking.pr_lifecycle_skill_gate import deny_decision, eval_skill_call_status
from hooks_constants.build_eval_before_eval_write_gate_constants import (
    ALL_EVAL_DIRECTORY_NAMES,
    ALL_FILE_PATH_FIELDS,
    ALL_FILE_WRITE_TOOL_NAMES,
    ALL_SHELL_TOOL_NAMES,
    APPLY_PATCH_TOOL_NAME,
    COMMAND_FIELD,
    EVAL_FILE_NAME_WORD_PATTERN,
    MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON,
    UNREADABLE_TRANSCRIPT_BEFORE_EVAL_WRITE_REASON,
)
from hooks_constants.pr_lifecycle_skill_gate_constants import PATH_SEPARATOR_PATTERN
from hooks_constants.shell_command_mutation import is_mutating_shell_command
from hooks_constants.shell_command_pipeline import all_operator_aware_tokenizations
from hooks_constants.pre_tool_use_stdin import print_decision_from_stdin


def is_eval_path(path: str) -> bool:
    """Return whether a path belongs to an eval.

    ::

        evals/cases.json                     -> True
        .claude/hillclimb/feature/run.py     -> True
        tools/eval_runner.py                 -> True
        tests/test_search.eval.json          -> True
        evals/../src/app.py                  -> False
        docs/features-start-with-an-eval.md  -> False
        build_eval_before_eval_write_gate.py -> False
        src/evaluate_score.py                -> False

    Args:
        path: The file path the tool writes.
    """
    slash_path = re.sub(PATH_SEPARATOR_PATTERN, "/", path.lower())
    all_segments = [each for each in posixpath.normpath(slash_path).split("/") if each]
    if not all_segments or not path:
        return False
    if any(each in ALL_EVAL_DIRECTORY_NAMES for each in all_segments[:-1]):
        return True
    return re.search(EVAL_FILE_NAME_WORD_PATTERN, all_segments[-1]) is not None


def shell_command_paths(command: str) -> list[str]:
    """Return the single words of a file-writing shell command, or nothing for a read.

    ::

        echo [] > evals/cases.json        -> ["echo", "[]", ">", "evals/cases.json"]
        cd evals && echo [] > cases.json  -> ["cd", "evals", "&&", ...]
        cat evals/cases.json              -> []

    The words come from the shared quote-aware tokenizer, and the write test is
    the shared mutating-command check. A quoted phrase with spaces, such as a
    commit message, is left out.

    Args:
        command: The shell command a Bash or PowerShell tool call runs.
    """
    if not is_mutating_shell_command(command):
        return []
    return [
        each_word
        for each_tokenization in all_operator_aware_tokenizations(command)
        for each_word in each_tokenization
        if not any(each_character.isspace() for each_character in each_word)
    ]


def _written_paths(all_payload_fields: dict[str, object]) -> list[str]:
    tool_name = all_payload_fields.get("tool_name")
    tool_input = all_payload_fields.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    if tool_name in ALL_SHELL_TOOL_NAMES:
        command = tool_input.get(COMMAND_FIELD)
        return shell_command_paths(command) if isinstance(command, str) else []
    if tool_name == APPLY_PATCH_TOOL_NAME:
        return list(payload_patch_target_paths(all_payload_fields, tool_input))
    if tool_name not in ALL_FILE_WRITE_TOOL_NAMES:
        return []
    return [
        path
        for path in (tool_input.get(each_field) for each_field in ALL_FILE_PATH_FIELDS)
        if isinstance(path, str) and path
    ]


def decision_for(all_payload_fields: dict[str, object]) -> dict[str, object] | None:
    """Return a deny for an eval file write with no build-eval call, else None.

    ::

        Write evals/cases.json, no build-eval in transcript   -> deny
        Bash echo [] > evals/cases.json, no build-eval        -> deny
        Write evals/cases.json, no readable transcript        -> deny
        Write evals/cases.json, build-eval in transcript      -> None
        Write src/app.py, no build-eval in transcript         -> None

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    if not any(is_eval_path(each_path) for each_path in _written_paths(all_payload_fields)):
        return None
    status = eval_skill_call_status(all_payload_fields)
    if status is None:
        return deny_decision(UNREADABLE_TRANSCRIPT_BEFORE_EVAL_WRITE_REASON)
    return None if status else deny_decision(MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON)


def main() -> int:
    """Read one payload, print a deny when needed, and exit zero."""
    return print_decision_from_stdin(decision_for)


if __name__ == "__main__":
    sys.exit(main())
