"""Deny a new pull request whose body lacks a 'Proof in practice' or an 'Existing work' section, or a feature pull request whose body lacks an 'Eval' section."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterator, Mapping
from typing import NamedTuple
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.followup_pr_dedupe import body_from_arguments, create_tool_fields, title_from_arguments
from hooks_constants.pr_lifecycle_skill_gate_constants import SHELL_TOOL_NAMES, UPDATE_PULL_REQUEST_TOOL_SUFFIX
from hooks_constants.pull_request_proof_constants import (
    ALL_GH_CREATE_WORDS,
    ALL_GH_EDIT_WORDS,
    ALL_PYTHON_PROGRAM_NAMES,
    ALL_VISIBLE_FILE_SUFFIXES,
    CHANGED_FILES_SEPARATOR,
    COMMAND_MARKER,
    DEFERRED_PROOF_REASON,
    MERGE_WORD_PATTERN,
    ALL_BASE_FLAGS,
    ALL_DEFAULT_BRANCH_REFERENCES,
    ALL_HEAD_FLAGS,
    ALL_REPOSITORY_FLAGS,
    BASE_FLAG_ASSIGNMENT_PREFIX,
    COMPARE_ENDPOINT_TEMPLATE,
    COMPARE_FILE_LIST_LIMIT,
    COMPARE_FILE_NAMES_QUERY,
    DEFAULT_BRANCH_QUERY,
    GH_TIMEOUT_SECONDS,
    HEAD_FLAG_ASSIGNMENT_PREFIX,
    REMOTE_BRANCH_PREFIX,
    REPOSITORY_ENDPOINT_TEMPLATE,
    REPOSITORY_FLAG_ASSIGNMENT_PREFIX,
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
    PULL_REQUEST_SCRIPT_EDIT_WORD,
    PULL_REQUEST_SCRIPT_NAME,
    ALL_TEST_RUNNER_COMMAND_PREFIXES,
    CODE_FENCE_MARKER,
    FENCED_COMMAND_PROMPT,
    INLINE_COMMAND_PATTERN,
    TEST_ONLY_PROOF_REASON,
    ALL_CODE_FENCE_MARKERS,
    BLOCKQUOTE_MARKERS,
    INLINE_CODE_SPAN_PATTERN,
    UNITTEST_MODULE_NAME,
    UNPROVEN_ADMISSION_PATTERN,
    UNPROVEN_PROOF_REASON,
    ALL_PASSTHROUGH_PROGRAM_NAMES,
    PATH_WITH_LINE_PATTERN,
    SINGLE_FILE_NAME_PATTERN,
)
from hooks_constants.piped_pytest_blocker_constants import (
    MODULE_RUN_FLAG,
    PYTHON_INTERPRETER_BASENAME_PATTERN,
)
from hooks_constants.pytest_invocation import (
    _all_tokens_from_the_interpreter_module_flag,
    segment_runs_pytest,
    unquoted_token,
)
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


def _script_word_arguments(program: str, all_arguments: list[str], word: str) -> list[str] | None:
    all_script_arguments = _script_arguments(program, all_arguments)
    if all_script_arguments is None or all_script_arguments[:1] != [word]:
        return None
    return all_script_arguments[1:]


def _command_arguments(
    all_segment_tokens: list[str], all_gh_words: list[str], script_word: str
) -> list[str] | None:
    program, all_arguments = segment_program_and_arguments(all_segment_tokens)
    if program == "gh" and all_arguments[: len(all_gh_words)] == all_gh_words:
        return all_arguments[len(all_gh_words) :]
    return _script_word_arguments(program, all_arguments, script_word)


def _shell_command(all_payload_fields: Mapping[str, object]) -> str | None:
    tool_input = all_payload_fields.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if all_payload_fields.get("tool_name") not in SHELL_TOOL_NAMES or not isinstance(command, str):
        return None
    return command


def _all_argument_lists(command: str, all_gh_words: list[str], script_word: str) -> Iterator[list[str]]:
    return (
        all_arguments
        for each_text in all_wrapped_command_texts(command)
        for each_segment, _each_following_operator in pipeline_segments_for_command(each_text)
        if (all_arguments := _command_arguments(each_segment, all_gh_words, script_word)) is not None
    )


def _all_create_argument_lists(command: str) -> Iterator[list[str]]:
    return _all_argument_lists(command, ALL_GH_CREATE_WORDS, PULL_REQUEST_SCRIPT_CREATE_WORD)


def _all_edit_argument_lists(command: str) -> Iterator[list[str]]:
    return _all_argument_lists(command, ALL_GH_EDIT_WORDS, PULL_REQUEST_SCRIPT_EDIT_WORD)


def _shell_create_calls(command: str, working_directory: str) -> list[CreateCall]:
    return [
        CreateCall(
            title_from_arguments(all_create_arguments),
            body_from_arguments(all_create_arguments, working_directory),
        )
        for all_create_arguments in _all_create_argument_lists(command)
    ]


def _flag_value(all_create_arguments: list[str], all_flags: frozenset[str], assignment_prefix: str) -> str | None:
    for each_position, each_argument in enumerate(all_create_arguments):
        if each_argument in all_flags and each_position + 1 < len(all_create_arguments):
            return unquoted_token(all_create_arguments[each_position + 1])
        if each_argument.startswith(assignment_prefix):
            return unquoted_token(each_argument[len(assignment_prefix) :])
    return None


def _shell_flag_value(
    all_payload_fields: Mapping[str, object], all_flags: frozenset[str], assignment_prefix: str
) -> str | None:
    command = _shell_command(all_payload_fields)
    if command is None:
        return None
    all_flag_values = [
        _flag_value(all_create_arguments, all_flags, assignment_prefix)
        for all_create_arguments in _all_create_argument_lists(command)
    ]
    return next((each_value for each_value in all_flag_values if each_value), None)


def _named_create_field(
    all_payload_fields: Mapping[str, object], field_name: str, all_flags: frozenset[str], assignment_prefix: str
) -> str | None:
    create_fields = create_tool_fields(all_payload_fields)
    field_value = None if create_fields is None else create_fields.get(field_name)
    if isinstance(field_value, str) and field_value:
        return field_value
    return _shell_flag_value(all_payload_fields, all_flags, assignment_prefix)


def _named_head_branch(all_payload_fields: Mapping[str, object]) -> str | None:
    return _named_create_field(all_payload_fields, "head", ALL_HEAD_FLAGS, HEAD_FLAG_ASSIGNMENT_PREFIX)


def _named_base_branch(all_payload_fields: Mapping[str, object]) -> str | None:
    return _named_create_field(all_payload_fields, "base", ALL_BASE_FLAGS, BASE_FLAG_ASSIGNMENT_PREFIX)


def _named_repository(all_payload_fields: Mapping[str, object]) -> str | None:
    create_fields = create_tool_fields(all_payload_fields)
    if create_fields is not None:
        owner = create_fields.get("owner")
        repository_name = create_fields.get("repo")
        if isinstance(owner, str) and owner and isinstance(repository_name, str) and repository_name:
            return f"{owner}/{repository_name}"
        return None
    return _shell_flag_value(all_payload_fields, ALL_REPOSITORY_FLAGS, REPOSITORY_FLAG_ASSIGNMENT_PREFIX)


def _create_calls(all_payload_fields: Mapping[str, object]) -> list[CreateCall]:
    create_fields = create_tool_fields(all_payload_fields)
    if create_fields is not None:
        title = create_fields.get("title")
        body = create_fields.get("body")
        return [
            CreateCall(
                title if isinstance(title, str) else None,
                body if isinstance(body, str) else "",
            )
        ]
    command = _shell_command(all_payload_fields)
    if command is None:
        return []
    working_directory = all_payload_fields.get("cwd")
    return _shell_create_calls(
        command, working_directory if isinstance(working_directory, str) else ""
    )


def is_create_call(all_payload_fields: Mapping[str, object]) -> bool:
    """Return whether a tool call opens a pull request.

    ::

        gh pr create --title t --body-file b.md         -> True
        mcp__github__create_pull_request                -> True
        gh pr edit 7, git push, Read                    -> False

    Args:
        all_payload_fields: A tool name and input, shaped like a PreToolUse payload.
    """
    command = _shell_command(all_payload_fields)
    return create_tool_fields(all_payload_fields) is not None or (
        command is not None and next(_all_create_argument_lists(command), None) is not None
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


def _line_commands(line: str, is_inside_fence: bool) -> list[str]:
    if not is_inside_fence:
        return re.findall(INLINE_COMMAND_PATTERN, line)
    stripped_line = line.strip()
    if stripped_line.startswith(FENCED_COMMAND_PROMPT):
        return [stripped_line[len(FENCED_COMMAND_PROMPT) :]]
    return []


def _fence_marker(line: str) -> str | None:
    fence_text = line.strip().lstrip(BLOCKQUOTE_MARKERS).strip()
    for each_marker in ALL_CODE_FENCE_MARKERS:
        if fence_text.startswith(each_marker) and each_marker not in fence_text[len(each_marker) :]:
            return each_marker
    return None


def _lines_with_fence_state(section: str) -> Iterator[tuple[str, bool]]:
    open_marker: str | None = None
    for each_line in section.splitlines():
        line_marker = _fence_marker(each_line)
        if line_marker is not None and open_marker is None:
            open_marker = line_marker
            continue
        if line_marker is not None and line_marker == open_marker:
            open_marker = None
            continue
        yield each_line, open_marker is not None


def _proof_commands(section: str) -> list[str]:
    all_commands: list[str] = []
    for each_line, each_is_inside_fence in _lines_with_fence_state(section):
        all_commands.extend(_line_commands(each_line, each_is_inside_fence))
    return [each_command for each_command in all_commands if _reads_as_command(each_command)]


def _reads_as_command(span: str) -> bool:
    all_words = span.split()
    if not all_words or re.match(PATH_WITH_LINE_PATTERN, all_words[0]):
        return False
    if len(all_words) > 1 or re.match(SINGLE_FILE_NAME_PATTERN, all_words[0]) is None:
        return True
    return _command_runs_tests(span)


def _unquoted_arguments(all_arguments: list[str]) -> list[str]:
    return [unquoted_token(each_argument) for each_argument in all_arguments]


def _arguments_name_unittest(all_arguments: list[str]) -> bool:
    all_module_tokens = _all_tokens_from_the_interpreter_module_flag(
        _unquoted_arguments(all_arguments)
    )
    if not all_module_tokens:
        return False
    module_flag = unquoted_token(all_module_tokens[0])
    if module_flag == MODULE_RUN_FLAG + UNITTEST_MODULE_NAME:
        return True
    return (
        module_flag == MODULE_RUN_FLAG
        and len(all_module_tokens) > 1
        and unquoted_token(all_module_tokens[1]) == UNITTEST_MODULE_NAME
    )


def _segment_runs_tests(all_segment_tokens: list[str]) -> bool:
    if segment_runs_pytest(all_segment_tokens):
        return True
    program, all_arguments = segment_program_and_arguments(all_segment_tokens)
    if PYTHON_INTERPRETER_BASENAME_PATTERN.fullmatch(program):
        return _arguments_name_unittest(all_arguments)
    command_words = (program, *_unquoted_arguments(all_arguments))
    return any(
        command_words[: len(each_prefix)] == each_prefix
        for each_prefix in ALL_TEST_RUNNER_COMMAND_PREFIXES
    )


def _command_runs_tests(command: str) -> bool:
    all_working_segments = [
        each_segment
        for each_segment, _each_following_operator in pipeline_segments_for_command(command)
        if segment_program_and_arguments(each_segment)[0] not in ALL_PASSTHROUGH_PROGRAM_NAMES
    ]
    return bool(all_working_segments) and all(
        _segment_runs_tests(each_segment) for each_segment in all_working_segments
    )


def _proof_runs_only_tests(section: str) -> bool:
    all_commands = _proof_commands(section)
    return bool(all_commands) and all(_command_runs_tests(each_command) for each_command in all_commands)


def _prose_lines(section: str) -> Iterator[tuple[str, str]]:
    for each_line, each_is_inside_fence in _lines_with_fence_state(section):
        if not each_is_inside_fence:
            yield each_line, re.sub(INLINE_CODE_SPAN_PATTERN, "", each_line.replace(CODE_FENCE_MARKER, "`"))


def unproven_admission(section: str) -> str | None:
    """Return the first prose line of a proof section that says something is not proven, or None.

    ::

        "Not proven here: a fresh Convert run."   -> "Not proven here: a fresh Convert run."
        "The live run is untested."               -> "The live run is untested."
        "It has not been tested on the target."   -> "It has not been tested on the target."
        "`not proven` printed by the probe"       -> None
        "> Not proven here: the live run."        -> "> Not proven here: the live run."
        "Ran `python run.py`, quoted below."      -> None

    The markers are not proven, not tested and not verified, each with any
    run of yet, been or fully after the not, plus unproven, untested and
    unverified. A line or list item that opens with "not run", "not ran",
    "not exercised" or "not executed", each with any run of yet or been after
    the not, is one too, and so is "has not been run", "have not been exercised"
    or "hasn't been executed", with "yet" allowed before "been". Case is
    ignored.
    Inline code spans and fenced blocks are skipped, so output quoted there
    never counts.
    """
    return _first_prose_match(section, UNPROVEN_ADMISSION_PATTERN)


def _first_prose_match(section: str, pattern: str) -> str | None:
    for each_line, each_prose in _prose_lines(section):
        if re.search(pattern, each_prose, re.IGNORECASE):
            return each_line.strip()
    return None


def merge_word_line(section: str) -> str | None:
    """Return the first prose line of a proof section that holds a merge word, or None.

    ::

        "I check the publish after the merge."   -> that line
        "A session verifies it after merging."   -> that line
        "Post-merge, a session confirms it."     -> that line
        "Ran `git merge origin/main`, then `python run.py`." -> None
        "Verified on the branch."                -> None

    The words are merge, merged, merges and merging, matched without regard to
    case, so post-merge counts. Inline code spans and fenced blocks are skipped,
    so a command or file name that holds the word passes when it sits in
    backticks.

    Args:
        section: The text under the 'Proof in practice' heading.
    """
    return _first_prose_match(section, MERGE_WORD_PATTERN)


def missing_proof_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a deny reason when a new pull request's body has no proof, else None.

    ::

        gh pr create --body-file body.md, body has the section -> None
        mcp__github__create_pull_request, body without it      -> MISSING_PROOF_REASON
        proof whose only commands run tests, like `pytest`      -> TEST_ONLY_PROOF_REASON
        proof whose only command is `py.test`                   -> TEST_ONLY_PROOF_REASON
        proof whose only command is `python -q -m unittest`     -> TEST_ONLY_PROOF_REASON
        proof with `pytest` and `python run.py`                 -> None
        proof whose prose says "Not proven here: the run"      -> UNPROVEN_PROOF_REASON
        proof whose prose says "Not run: the live publish"     -> UNPROVEN_PROOF_REASON
        proof prose that says "I verify it after the merge"    -> DEFERRED_PROOF_REASON
        gh pr create --fill                                     -> MISSING_BODY_REASON
        gh pr edit, git push, any other tool                    -> None

    The proof section is a 'Proof in practice' heading whose text names at
    least one command in backticks. A command is an inline backticked span, or
    a line that starts with '$ ' inside a fenced block. A span that starts
    with a path:line is not a command. A span that is one path or file name is
    not a command unless that span runs a test runner, such as py.test or
    pytest.exe. When every command runs a test runner, such as pytest,
    python -m unittest, npm test, npx vitest, jest, go test or cargo test,
    the section is denied. Quotes around a runner word still count. Interpreter
    flags before -m unittest still count. coverage run -m unittest counts.
    A pipe into tee, tail, head, grep or cat keeps a test run a test run.
    A section whose prose says part of the change is not proven, untested or
    unverified is denied, with the line quoted; unproven_admission lists the
    markers. A prose line with a merge word is denied in the proof section;
    merge_word_line lists the words.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    for each_body in _create_bodies(all_payload_fields):
        if each_body is None:
            return MISSING_BODY_REASON
        section = proof_section(each_body)
        if not section:
            return MISSING_PROOF_REASON
        section_reason = _proof_section_reason(section)
        if section_reason is not None:
            return section_reason
    return None


def _proof_section_reason(section: str) -> str | None:
    if COMMAND_MARKER not in section:
        return MISSING_PROOF_REASON
    if _proof_runs_only_tests(section):
        return TEST_ONLY_PROOF_REASON
    admission = unproven_admission(section)
    if admission is not None:
        return UNPROVEN_PROOF_REASON.format(admission=admission)
    deferral = merge_word_line(section)
    return None if deferral is None else DEFERRED_PROOF_REASON.format(deferral=deferral)


def edit_proof_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a deny reason when a pull request body edit weakens its proof section, else None.

    ::

        update_pull_request, proof section says "Not run: x"       -> UNPROVEN_PROOF_REASON
        gh pr edit --body-file, proof prose says "after the merge" -> DEFERRED_PROOF_REASON
        update_pull_request, proof whose only command is `pytest`  -> TEST_ONLY_PROOF_REASON
        update_pull_request, body with no proof section            -> None
        update_pull_request with no body, create calls, any tool   -> None

    An edit with no proof section passes. A proof section that is there meets
    the rules a new pull request meets: a command in backticks, more than test
    runs, no unrun line and no merge word. The edit comes through the
    update_pull_request tool, gh pr edit, or the pull_request.py edit script.
    A body this gate cannot read passes unread: an inline multi-line --body,
    --body-file - from standard input, a $(...) body, a --body-file path that
    an earlier cd changes, a gh global option before pr edit, or a gh api call.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    for each_body in _edit_bodies(all_payload_fields):
        section = proof_section(each_body)
        edit_reason = _proof_section_reason(section) if section else None
        if edit_reason is not None:
            return edit_reason
    return None


def _edit_bodies(all_payload_fields: Mapping[str, object]) -> list[str]:
    tool_name = all_payload_fields.get("tool_name")
    tool_input = all_payload_fields.get("tool_input")
    if isinstance(tool_name, str) and tool_name.endswith(UPDATE_PULL_REQUEST_TOOL_SUFFIX):
        body = tool_input.get("body") if isinstance(tool_input, dict) else None
        return [body] if isinstance(body, str) else []
    command = _shell_command(all_payload_fields)
    if command is None:
        return []
    working_directory = all_payload_fields.get("cwd")
    all_bodies = [
        body_from_arguments(each_arguments, working_directory if isinstance(working_directory, str) else "")
        for each_arguments in _all_edit_argument_lists(command)
    ]
    return [each_body for each_body in all_bodies if each_body is not None]


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
    return _visible_paths(all_changed_paths)


def _visible_paths(all_changed_paths: list[str]) -> list[str]:
    return [each_path for each_path in all_changed_paths if each_path.lower().endswith(ALL_VISIBLE_FILE_SUFFIXES)]


def _gh_api_lines(endpoint: str, query: str) -> list[str] | None:
    try:
        completed = subprocess.run(
            ["gh", "api", endpoint, "--jq", query],
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.splitlines() if completed.returncode == 0 else None


def _compare_base_branch(repository: str, base_branch: str | None) -> str | None:
    if base_branch:
        return base_branch
    all_default_branch_lines = _gh_api_lines(
        REPOSITORY_ENDPOINT_TEMPLATE.format(repository=repository), DEFAULT_BRANCH_QUERY
    )
    if not all_default_branch_lines:
        return None
    return all_default_branch_lines[0]


def _visible_compare_paths(repository: str, base_branch: str, head_branch: str) -> list[str] | None:
    all_changed_paths = _gh_api_lines(
        COMPARE_ENDPOINT_TEMPLATE.format(
            repository=repository, base_branch=base_branch, head_branch=head_branch
        ),
        COMPARE_FILE_NAMES_QUERY,
    )
    if all_changed_paths is None:
        return None
    all_visible_paths = _visible_paths(all_changed_paths)
    if all_visible_paths or len(all_changed_paths) < COMPARE_FILE_LIST_LIMIT:
        return all_visible_paths
    return None


def remote_visible_changed_files(
    repository: str | None, base_branch: str | None, head_branch: str | None
) -> list[str] | None:
    """Return the changed files people see, read from the GitHub compare API, or None when it cannot tell.

    ::

        compare lists tool.py                          -> []
        compare lists web/page.html                    -> ["web/page.html"]
        compare returns 300 paths and none are visible -> None
        repository or head missing                     -> None

    The base is the named base branch, else the repository's default branch.
    A page of 300 paths is the compare API's file cap. A visible file on that
    page is returned. A full page with none is None, because a later file can
    still be one people see.

    Args:
        repository: The owner/name the create call names, or None.
        base_branch: The base branch the create call names, or None.
        head_branch: The head branch the create call names, or None.
    """
    if not repository or not head_branch:
        return None
    resolved_base_branch = _compare_base_branch(repository, base_branch)
    if resolved_base_branch is None:
        return None
    return _visible_compare_paths(repository, resolved_base_branch, head_branch)


def missing_look_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a deny reason when a pull request changing visible files shows no picture, else None.

    ::

        branch changes page.html, proof has ![after](https://x/after.png) -> None
        branch changes page.html, proof quotes only command output        -> MISSING_LOOK_REASON
        branch changes only .py files                                     -> None
        git cannot read the branch, compare API lists only .py files      -> None
        git cannot read the branch, compare API returns 300 .py files     -> UNREADABLE_CHANGES_REASON
        neither git nor the compare API can read it, no picture           -> UNREADABLE_CHANGES_REASON

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    all_bodies = [each_body for each_body in _create_bodies(all_payload_fields) if each_body is not None]
    if not all_bodies:
        return None
    working_directory = all_payload_fields.get("cwd")
    head_branch = _named_head_branch(all_payload_fields)
    all_visible_files = visible_changed_files(str(working_directory or ""), head_branch)
    if all_visible_files is None:
        all_visible_files = remote_visible_changed_files(
            _named_repository(all_payload_fields), _named_base_branch(all_payload_fields), head_branch
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
