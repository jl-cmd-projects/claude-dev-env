"""Deny a new pull request whose body carries no 'Proof in practice' section."""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.followup_pr_dedupe import body_from_arguments
from hooks_constants.pr_lifecycle_skill_gate_constants import SHELL_TOOL_NAMES
from hooks_constants.pull_request_proof_constants import (
    ALL_GH_CREATE_WORDS,
    ALL_PYTHON_PROGRAM_NAMES,
    COMMAND_MARKER,
    CREATE_PULL_REQUEST_TOOL_SUFFIX,
    LINE_SEPARATOR,
    MISSING_BODY_REASON,
    MISSING_PROOF_REASON,
    NEXT_HEADING_PATTERN,
    PROOF_HEADING_PATTERN,
    PULL_REQUEST_SCRIPT_CREATE_WORD,
    PULL_REQUEST_SCRIPT_NAME,
)
from hooks_constants.pytest_invocation import unquoted_token
from hooks_constants.shell_command_pipeline import pipeline_segments_for_command
from hooks_constants.shell_command_segments import token_basename
from hooks_constants.shell_command_wrappers import (
    all_wrapped_command_texts,
    segment_program_and_arguments,
)


def _heading_level(line: str, heading_pattern: str) -> int | None:
    heading = re.match(heading_pattern, line.strip(), re.IGNORECASE)
    return None if heading is None else len(heading.group(1))


def _lines_until_heading(all_lines: list[str], heading_level: int) -> list[str]:
    for each_index, each_line in enumerate(all_lines):
        next_level = _heading_level(each_line, NEXT_HEADING_PATTERN)
        if next_level is not None and next_level <= heading_level:
            return all_lines[:each_index]
    return all_lines


def proof_section(body: str) -> str | None:
    """Return the text under the body's 'Proof in practice' heading, or None.

    ::

        "## Proof in practice\\nran `x`\\n## Notes" -> "ran `x`"
        "## Summary\\nno proof heading"             -> None

    The section runs to the next heading of the same or a higher level.
    """
    all_lines = body.splitlines()
    for each_index, each_line in enumerate(all_lines):
        heading_level = _heading_level(each_line, PROOF_HEADING_PATTERN)
        if heading_level is not None:
            all_section_lines = _lines_until_heading(all_lines[each_index + 1 :], heading_level)
            return LINE_SEPARATOR.join(all_section_lines).strip()
    return None


def _script_arguments(program: str, all_arguments: list[str]) -> list[str] | None:
    if program == PULL_REQUEST_SCRIPT_NAME:
        return all_arguments
    if program not in ALL_PYTHON_PROGRAM_NAMES or not all_arguments:
        return None
    script_name = token_basename(unquoted_token(all_arguments[0]))
    return all_arguments[1:] if script_name == PULL_REQUEST_SCRIPT_NAME else None


def _script_create_arguments(program: str, all_arguments: list[str]) -> list[str] | None:
    all_script_arguments = _script_arguments(program, all_arguments)
    if all_script_arguments is None or all_script_arguments[:1] != [PULL_REQUEST_SCRIPT_CREATE_WORD]:
        return None
    return all_script_arguments[1:]


def _create_arguments(all_segment_tokens: list[str]) -> list[str] | None:
    program, all_arguments = segment_program_and_arguments(all_segment_tokens)
    if program == "gh" and all_arguments[: len(ALL_GH_CREATE_WORDS)] == ALL_GH_CREATE_WORDS:
        return all_arguments[len(ALL_GH_CREATE_WORDS) :]
    return _script_create_arguments(program, all_arguments)


def _shell_create_bodies(command: str, working_directory: str) -> list[str | None]:
    return [
        body_from_arguments(all_create_arguments, working_directory)
        for each_text in all_wrapped_command_texts(command)
        for each_segment, _each_following_operator in pipeline_segments_for_command(each_text)
        if (all_create_arguments := _create_arguments(each_segment)) is not None
    ]


def _create_bodies(all_payload_fields: Mapping[str, object]) -> list[str | None]:
    tool_name = all_payload_fields.get("tool_name")
    tool_input = all_payload_fields.get("tool_input")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return []
    if tool_name.endswith(CREATE_PULL_REQUEST_TOOL_SUFFIX):
        body = tool_input.get("body")
        return [body if isinstance(body, str) else ""]
    command = tool_input.get("command")
    if tool_name not in SHELL_TOOL_NAMES or not isinstance(command, str):
        return []
    working_directory = all_payload_fields.get("cwd")
    return _shell_create_bodies(
        command, working_directory if isinstance(working_directory, str) else ""
    )


def missing_proof_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a deny reason when a new pull request's body has no proof, else None.

    ::

        gh pr create --body-file body.md, body has the section -> None
        mcp__github__create_pull_request, body without it      -> MISSING_PROOF_REASON
        gh pr create --fill                                     -> MISSING_BODY_REASON
        gh pr edit, git push, any other tool                    -> None

    The proof section is a 'Proof in practice' heading whose text names at
    least one command in backticks.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    for each_body in _create_bodies(all_payload_fields):
        if each_body is None:
            return MISSING_BODY_REASON
        section = proof_section(each_body)
        if not section or COMMAND_MARKER not in section:
            return MISSING_PROOF_REASON
    return None
