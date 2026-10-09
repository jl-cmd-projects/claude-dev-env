"""Deny a new pull request whose body lacks a 'Proof in practice' or an 'Existing work' section, or a feature pull request whose body lacks an 'Eval' section."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Mapping
from typing import NamedTuple
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.followup_pr_dedupe import body_from_arguments, title_from_arguments
from hooks_constants.pr_lifecycle_skill_gate_constants import SHELL_TOOL_NAMES
from hooks_constants.pull_request_proof_constants import (
    ALL_GH_CREATE_WORDS,
    ALL_PYTHON_PROGRAM_NAMES,
    ALL_VISIBLE_FILE_SUFFIXES,
    CHANGED_FILES_SEPARATOR,
    COMMAND_MARKER,
    CREATE_PULL_REQUEST_TOOL_SUFFIX,
    ALL_DEFAULT_BRANCH_REFERENCES,
    ALL_HEAD_FLAGS,
    HEAD_FLAG_ASSIGNMENT_PREFIX,
    REMOTE_BRANCH_PREFIX,
    UNREADABLE_CHANGES_REASON,
    EVAL_HEADING_PATTERN,
    EXISTING_WORK_HEADING_PATTERN,
    FEATURE_TITLE_PATTERN,
    GIT_TIMEOUT_SECONDS,
    LINE_SEPARATOR,
    MISSING_BODY_REASON,
    MISSING_EVAL_SECTION_REASON,
    MISSING_EXISTING_WORK_REASON,
    MISSING_LOOK_REASON,
    MISSING_PROOF_REASON,
    NEXT_HEADING_PATTERN,
    PROOF_HEADING_PATTERN,
    PROOF_IMAGE_PATTERN,
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


class CreateCall(NamedTuple):
    """The title and body one pull request create call passes; None marks a value this gate cannot read."""

    title: str | None
    body: str | None


def _heading_level(line: str, heading_pattern: str) -> int | None:
    heading = re.match(heading_pattern, line.strip(), re.IGNORECASE)
    return None if heading is None else len(heading.group(1))


def _lines_until_heading(all_lines: list[str], heading_level: int) -> list[str]:
    for each_index, each_line in enumerate(all_lines):
        next_level = _heading_level(each_line, NEXT_HEADING_PATTERN)
        if next_level is not None and next_level <= heading_level:
            return all_lines[:each_index]
    return all_lines


def _section_text(body: str, heading_pattern: str) -> str | None:
    all_lines = body.splitlines()
    for each_index, each_line in enumerate(all_lines):
        heading_level = _heading_level(each_line, heading_pattern)
        if heading_level is not None:
            all_section_lines = _lines_until_heading(all_lines[each_index + 1 :], heading_level)
            return LINE_SEPARATOR.join(all_section_lines).strip()
    return None


def proof_section(body: str) -> str | None:
    """Return the text under the body's 'Proof in practice' heading, or None.

    ::

        "## Proof in practice\\nran `x`\\n## Notes" -> "ran `x`"
        "## Summary\\nno proof heading"             -> None

    The section runs to the next heading of the same or a higher level.
    """
    return _section_text(body, PROOF_HEADING_PATTERN)


def section_under_existing_work(body: str) -> str | None:
    """Return the text under the body's 'Existing work' heading, or None.

    ::

        "## Existing work\\n`a.py:4` runs it\\n## Notes" -> "`a.py:4` runs it"
        "## Summary\\nno existing work heading"         -> None

    The section runs to the next heading of the same or a higher level.
    """
    return _section_text(body, EXISTING_WORK_HEADING_PATTERN)


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


def _shell_create_calls(command: str, working_directory: str) -> list[CreateCall]:
    return [
        CreateCall(
            title_from_arguments(all_create_arguments),
            body_from_arguments(all_create_arguments, working_directory),
        )
        for each_text in all_wrapped_command_texts(command)
        for each_segment, _each_following_operator in pipeline_segments_for_command(each_text)
        if (all_create_arguments := _create_arguments(each_segment)) is not None
    ]


def _head_flag_value(all_create_arguments: list[str]) -> str | None:
    for each_position, each_argument in enumerate(all_create_arguments):
        if each_argument in ALL_HEAD_FLAGS and each_position + 1 < len(all_create_arguments):
            return all_create_arguments[each_position + 1]
        if each_argument.startswith(HEAD_FLAG_ASSIGNMENT_PREFIX):
            return each_argument[len(HEAD_FLAG_ASSIGNMENT_PREFIX) :]
    return None


def _named_head_branch(all_payload_fields: Mapping[str, object]) -> str | None:
    tool_input = all_payload_fields.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    head_branch = tool_input.get("head")
    if isinstance(head_branch, str):
        return head_branch
    command = tool_input.get("command")
    if all_payload_fields.get("tool_name") not in SHELL_TOOL_NAMES or not isinstance(command, str):
        return None
    all_head_flag_values = [
        _head_flag_value(all_create_arguments)
        for each_text in all_wrapped_command_texts(command)
        for each_segment, _each_following_operator in pipeline_segments_for_command(each_text)
        if (all_create_arguments := _create_arguments(each_segment)) is not None
    ]
    return next((each_value for each_value in all_head_flag_values if each_value), None)


def _create_calls(all_payload_fields: Mapping[str, object]) -> list[CreateCall]:
    tool_name = all_payload_fields.get("tool_name")
    tool_input = all_payload_fields.get("tool_input")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return []
    if tool_name.endswith(CREATE_PULL_REQUEST_TOOL_SUFFIX):
        title = tool_input.get("title")
        body = tool_input.get("body")
        return [
            CreateCall(
                title if isinstance(title, str) else None,
                body if isinstance(body, str) else "",
            )
        ]
    command = tool_input.get("command")
    if tool_name not in SHELL_TOOL_NAMES or not isinstance(command, str):
        return []
    working_directory = all_payload_fields.get("cwd")
    return _shell_create_calls(
        command, working_directory if isinstance(working_directory, str) else ""
    )


def _create_bodies(all_payload_fields: Mapping[str, object]) -> list[str | None]:
    return [each_call.body for each_call in _create_calls(all_payload_fields)]


def _is_feature_title(title: str | None) -> bool:
    return title is not None and re.match(FEATURE_TITLE_PATTERN, title, re.IGNORECASE) is not None


def is_feature_pull_request(all_payload_fields: Mapping[str, object]) -> bool:
    """Return whether any pull request create call in the payload carries a feature title.

    ::

        mcp__github__create_pull_request, title "feat(hooks)!: x" -> True
        gh pr create --title "fix: y" --body-file b.md             -> False
        gh pr create --fill                                        -> False
        gh pr edit, git push, any other tool                       -> False

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    return any(_is_feature_title(each_call.title) for each_call in _create_calls(all_payload_fields))


def missing_eval_section_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a deny reason when a feature pull request's body has no eval section, else None.

    ::

        title "feat: x", body has the section     -> None
        title "feat: x", body without it          -> MISSING_EVAL_SECTION_REASON
        title "fix: y", body without it           -> None
        title "feat: x", gh pr create --fill      -> None

    The section is an 'Eval' heading whose text names at least one command in
    backticks. A create command whose body this gate cannot read passes here,
    because missing_proof_reason denies it first.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    for each_call in _create_calls(all_payload_fields):
        if each_call.body is None or not _is_feature_title(each_call.title):
            continue
        section = _section_text(each_call.body, EVAL_HEADING_PATTERN)
        if not section or COMMAND_MARKER not in section:
            return MISSING_EVAL_SECTION_REASON
    return None


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


def missing_existing_work_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a deny reason when a new pull request's body has no existing-work section, else None.

    ::

        mcp__github__create_pull_request, body has the section -> None
        mcp__github__create_pull_request, body without it      -> MISSING_EXISTING_WORK_REASON
        gh pr create --fill                                     -> None
        gh pr edit, git push, any other tool                    -> None

    The section is an 'Existing work' heading with text under it. A create
    command whose body this gate cannot read passes here, because
    missing_proof_reason denies it first.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    for each_body in _create_bodies(all_payload_fields):
        if each_body is not None and not section_under_existing_work(each_body):
            return MISSING_EXISTING_WORK_REASON
    return None


def _git_lines(working_directory: str, *all_git_arguments: str) -> list[str] | None:
    try:
        completed = subprocess.run(
            ["git", "-C", working_directory, *all_git_arguments],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.splitlines() if completed.returncode == 0 else None


def _first_merge_base(working_directory: str, head_reference: str) -> str | None:
    for each_base_reference in ALL_DEFAULT_BRANCH_REFERENCES:
        all_merge_base_lines = _git_lines(working_directory, "merge-base", head_reference, each_base_reference)
        if all_merge_base_lines:
            return all_merge_base_lines[0]
    return None


def _head_reference(working_directory: str, head_branch: object) -> str | None:
    if not isinstance(head_branch, str) or not head_branch:
        return "HEAD"
    if _git_lines(working_directory, "branch", "--show-current") == [head_branch]:
        return "HEAD"
    for each_candidate in (head_branch, REMOTE_BRANCH_PREFIX + head_branch):
        if _git_lines(working_directory, "rev-parse", "--verify", "--quiet", each_candidate + "^{commit}"):
            return each_candidate
    return None


def visible_changed_files(working_directory: str, head_branch: object) -> list[str] | None:
    """Return the changed files people see on the head branch, or None when git cannot tell.

    The head is the checked-out branch, or the named branch or its origin copy
    when the checkout holds another branch. The base is the first of
    origin/HEAD, origin/main and main that git can reach::

        checkout on feature, page.html changed -> ["page.html"]
        named head exists nowhere in the clone  -> None
        no base reference reachable             -> None

    Args:
        working_directory: The session directory the hook payload names.
        head_branch: The head branch a create call names, or None.
    """
    if not working_directory:
        return None
    head_reference = _head_reference(working_directory, head_branch)
    if head_reference is None:
        return None
    merge_base = _first_merge_base(working_directory, head_reference)
    if merge_base is None:
        return None
    all_changed_paths = _git_lines(working_directory, "diff", "--name-only", merge_base, head_reference)
    if all_changed_paths is None:
        return None
    return [each_path for each_path in all_changed_paths if each_path.lower().endswith(ALL_VISIBLE_FILE_SUFFIXES)]


def missing_look_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a deny reason when a pull request changing visible files shows no picture, else None.

    ::

        branch changes page.html, proof has ![after](https://x/after.png) -> None
        branch changes page.html, proof quotes only command output        -> MISSING_LOOK_REASON
        branch changes only .py files                                     -> None
        git cannot read the branch, proof shows no picture                -> UNREADABLE_CHANGES_REASON

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    all_bodies = [each_body for each_body in _create_bodies(all_payload_fields) if each_body is not None]
    if not all_bodies:
        return None
    working_directory = all_payload_fields.get("cwd")
    all_visible_files = visible_changed_files(
        str(working_directory or ""), _named_head_branch(all_payload_fields)
    )
    if all_visible_files == []:
        return None
    for each_body in all_bodies:
        if re.search(PROOF_IMAGE_PATTERN, proof_section(each_body) or "", re.IGNORECASE):
            continue
        if all_visible_files is None:
            return UNREADABLE_CHANGES_REASON
        return MISSING_LOOK_REASON.format(changed_files=CHANGED_FILES_SEPARATOR.join(all_visible_files))
    return None
