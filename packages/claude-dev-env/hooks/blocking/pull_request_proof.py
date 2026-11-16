"""Deny a new pull request whose body lacks a 'Proof in practice' or an 'Existing work' section, or a feature pull request whose body lacks an 'Eval' section."""

from __future__ import annotations

import argparse
import base64
import binascii
import functools
import json
import re
import sys
from collections.abc import Callable, Iterator, Mapping
from typing import NamedTuple
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.body_flowchart import fenced_line_flags, section_has_flowchart
from blocking.evidence_tier import (
    EvidenceTier,
    TierCause,
    TierChoice,
    choose_tier,
    declared_live_surface_globs,
    first_agent_surface_path,
)
from blocking.followup_pr_dedupe import (
    all_create_argument_lists,
    all_pull_request_argument_lists,
    body_from_arguments,
    create_tool_fields,
    shell_command,
    title_from_arguments,
)
from blocking.gate_run_reads import ReadSlice, answer_once, child_stdout, gate_run
from hooks_constants.evidence_tier_constants import LIVE_SURFACES_FILE_PATH
from hooks_constants.pr_lifecycle_skill_gate_constants import UPDATE_PULL_REQUEST_TOOL_SUFFIX
from hooks_constants.pull_request_proof_constants import (
    ADDED_FILE_NAMES_QUERY,
    AGENT_SURFACE_EVAL_SENTENCE,
    ALL_EDIT_NUMBER_FLAGS,
    ALL_GH_EDIT_BOOLEAN_FLAGS,
    CODE_WITHOUT_LIVE_SURFACE_TIER_SENTENCE,
    CONTENTS_ENDPOINT_TEMPLATE,
    CONTENTS_QUERY,
    FLAG_ASSIGNMENT_MARKER,
    FLAG_PREFIX,
    LIVE_SURFACE_TIER_SENTENCE,
    DECLARED_SURFACES_FILE_ENCODING,
    MISSING_CHECKED_PROOF_REASON,
    NEEDS_EVAL_SECTION_KEY,
    NEEDS_PROOF_SECTION_KEY,
    NO_DECLARED_SURFACES_TIER_SENTENCE,
    ONLY_DOCS_AND_TESTS_TIER_SENTENCE,
    UNREAD_FILE_LIST_EVAL_SENTENCE,
    UNREAD_FILE_LIST_TIER_SENTENCE,
    GIT_URL_SUFFIX,
    REMOTE_LINE_FIELD_COUNT,
    RUN_WORD_PATTERN,
    WORKFLOW_NAME_MATCH_TEMPLATE,
    WORKFLOW_SUBJECT_PATTERN,
    AFTER_MERGE_HEADING_PATTERN,
    AFTER_MERGE_NO_RECORDER_PATTERN,
    AFTER_MERGE_RECORDER_PATTERN,
    AFTER_MERGE_SENTENCE_SEPARATOR_PATTERN,
    ALL_GH_EDIT_WORDS,
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
    COMPARE_FILE_STATUS_QUERY,
    DEFAULT_BRANCH_QUERY,
    GH_TIMEOUT_SECONDS,
    HEAD_FLAG_ASSIGNMENT_PREFIX,
    REMOTE_BRANCH_PREFIX,
    REPOSITORY_ENDPOINT_TEMPLATE,
    REPOSITORY_FLAG_ASSIGNMENT_PREFIX,
    UNREADABLE_CHANGES_REASON,
    WHAT_THIS_DOES_HEADING_PATTERN,
    EVAL_HEADING_PATTERN,
    EXISTING_WORK_HEADING_PATTERN,
    FEATURE_TITLE_PATTERN,
    GIT_TIMEOUT_SECONDS,
    LINE_SEPARATOR,
    MISSING_BODY_REASON,
    MISSING_EVAL_SECTION_REASON,
    MISSING_EXISTING_WORK_REASON,
    MISSING_FLOWCHART_REASON,
    MISSING_LOOK_REASON,
    MISSING_PROOF_REASON,
    NEW_WORKFLOW_PATH_PATTERN,
    NEXT_HEADING_PATTERN,
    PROOF_HEADING_PATTERN,
    PURE_RENAME_STATUS,
    RAW_HEADER_FIELD_COUNT,
    RAW_RECORD_PREFIX,
    RAW_RENAME_PATH_COUNT,
    RAW_RENAME_STATUS_LETTER,
    ALL_RAW_TWO_PATH_STATUS_LETTERS,
    PROOF_IMAGE_PATTERN,
    PULL_REQUEST_SCRIPT_EDIT_WORD,
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
from hooks_constants.shell_command_wrappers import segment_program_and_arguments


class CreateCall(NamedTuple):
    """The title, body, head, base and repository one pull request create call passes.

    None in title or body marks a value this gate cannot read. None in head,
    base or repository marks a value the create does not name.
    """

    title: str | None
    body: str | None
    head: str | None
    base: str | None
    repository: str | None


def _heading_level(line: str, heading_pattern: str) -> int | None:
    heading = re.match(heading_pattern, line.strip(), re.IGNORECASE)
    return None if heading is None else len(heading.group(1))


def _lines_until_heading(all_lines: list[str], heading_level: int) -> list[str]:
    all_fenced_flags = fenced_line_flags(all_lines)
    for each_index, each_line in enumerate(all_lines):
        next_level = None if all_fenced_flags[each_index] else _heading_level(each_line, NEXT_HEADING_PATTERN)
        if next_level is not None and next_level <= heading_level:
            return all_lines[:each_index]
    return all_lines


def _section_text(body: str, heading_pattern: str) -> str | None:
    all_lines = body.splitlines()
    all_fenced_flags = fenced_line_flags(all_lines)
    for each_index, each_line in enumerate(all_lines):
        heading_level = None if all_fenced_flags[each_index] else _heading_level(each_line, heading_pattern)
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


def what_this_does_section(body: str) -> str | None:
    """Return the text under the body's 'What this does' heading, or None.

    ::

        "## What this does\\nBefore, after.\\n## Risk" -> "Before, after."
        "## Summary\\nno what-this-does heading"      -> None

    The section runs to the next heading of the same or a higher level. A line
    that starts with a hash inside a fenced block is code, not a heading. When any fence
    in the body never closes, every fence reads as plain text.
    """
    return _section_text(body, WHAT_THIS_DOES_HEADING_PATTERN)


def section_under_existing_work(body: str) -> str | None:
    """Return the text under the body's 'Existing work' heading, or None.

    ::

        "## Existing work\\n`a.py:4` runs it\\n## Notes" -> "`a.py:4` runs it"
        "## Summary\\nno existing work heading"         -> None

    The section runs to the next heading of the same or a higher level.
    """
    return _section_text(body, EXISTING_WORK_HEADING_PATTERN)


def _all_edit_argument_lists(command: str) -> Iterator[list[str]]:
    return all_pull_request_argument_lists(command, ALL_GH_EDIT_WORDS, PULL_REQUEST_SCRIPT_EDIT_WORD)


def _shell_create_calls(command: str, working_directory: str) -> list[CreateCall]:
    return [
        CreateCall(
            title_from_arguments(all_create_arguments),
            body_from_arguments(all_create_arguments, working_directory),
            _flag_value(all_create_arguments, ALL_HEAD_FLAGS, HEAD_FLAG_ASSIGNMENT_PREFIX) or None,
            _flag_value(all_create_arguments, ALL_BASE_FLAGS, BASE_FLAG_ASSIGNMENT_PREFIX) or None,
            _flag_value(all_create_arguments, ALL_REPOSITORY_FLAGS, REPOSITORY_FLAG_ASSIGNMENT_PREFIX) or None,
        )
        for all_create_arguments in all_create_argument_lists(command)
    ]


def _flag_value(all_create_arguments: list[str], all_flags: frozenset[str], assignment_prefix: str) -> str | None:
    for each_position, each_argument in enumerate(all_create_arguments):
        if each_argument in all_flags and each_position + 1 < len(all_create_arguments):
            return unquoted_token(all_create_arguments[each_position + 1])
        if each_argument.startswith(assignment_prefix):
            return unquoted_token(each_argument[len(assignment_prefix) :])
    return None


def _named_text(all_create_fields: Mapping[str, object], field_name: str) -> str | None:
    field_value = all_create_fields.get(field_name)
    return field_value if isinstance(field_value, str) and field_value else None


def _mcp_create_call(all_create_fields: Mapping[str, object]) -> CreateCall:
    title = all_create_fields.get("title")
    body = all_create_fields.get("body")
    owner = _named_text(all_create_fields, "owner")
    repository_name = _named_text(all_create_fields, "repo")
    return CreateCall(
        title if isinstance(title, str) else None,
        body if isinstance(body, str) else "",
        _named_text(all_create_fields, "head"),
        _named_text(all_create_fields, "base"),
        f"{owner}/{repository_name}" if owner and repository_name else None,
    )


def _create_calls(all_payload_fields: Mapping[str, object]) -> list[CreateCall]:
    create_fields = create_tool_fields(all_payload_fields)
    if create_fields is not None:
        return [_mcp_create_call(create_fields)]
    command = shell_command(all_payload_fields)
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
    command = shell_command(all_payload_fields)
    return create_tool_fields(all_payload_fields) is not None or (
        command is not None and next(all_create_argument_lists(command), None) is not None
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


def agent_surface_sentence(agent_surface_path: str | None) -> str:
    """Return the sentence that says why a feature owes an eval.

    ::

        "skills/ship/SKILL.md" -> AGENT_SURFACE_EVAL_SENTENCE naming that path
        None                   -> UNREAD_FILE_LIST_EVAL_SENTENCE

    Args:
        agent_surface_path: The first changed path agents read or load, or None
            when the changed file list could not be read.
    """
    if agent_surface_path is None:
        return UNREAD_FILE_LIST_EVAL_SENTENCE
    return AGENT_SURFACE_EVAL_SENTENCE.format(path=agent_surface_path)


def _eval_need_sentence(path_read: ChangedPathRead | None) -> str | None:
    if path_read is None or not path_read.all_paths:
        return agent_surface_sentence(None)
    agent_surface_path = first_agent_surface_path(path_read.all_paths)
    return None if agent_surface_path is None else agent_surface_sentence(agent_surface_path)


def eval_need_sentence(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return why a feature create in the payload owes an eval, or None when none owes one.

    ::

        title "feat: x", branch changes skills/a/SKILL.md -> agent_surface_sentence("skills/a/SKILL.md")
        title "feat: x", branch changes only src/a.py     -> None
        title "feat: x", changed file list unread         -> agent_surface_sentence(None)
        title "fix: y", any branch                        -> None

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    working_directory = str(all_payload_fields.get("cwd") or "")
    for each_call in _create_calls(all_payload_fields):
        if not _is_feature_title(each_call.title):
            continue
        need_sentence = _eval_need_sentence(_changed_path_read_for_create(each_call, working_directory))
        if need_sentence is not None:
            return need_sentence
    return None


def missing_eval_section_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a deny reason when a feature pull request that changes an agent surface has no eval section, else None.

    ::

        title "feat: x", body has the section                    -> None
        title "feat: x", changes skills/a/SKILL.md, no section   -> MISSING_EVAL_SECTION_REASON + why
        title "feat: x", changed file list unread, no section    -> MISSING_EVAL_SECTION_REASON + why
        title "feat: x", changes only src/a.py, no section       -> None
        title "fix: y", body without it                          -> None
        title "feat: x", gh pr create --fill                     -> None

    The section is an 'Eval' heading whose text names at least one command in
    backticks. A feature owes it when a changed path is an agent surface, as
    first_agent_surface_path names one, or when the changed file list cannot be
    read. A body with the section reads no file list. A create command whose
    body this gate cannot read passes here, because missing_proof_reason denies
    it first.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    working_directory = str(all_payload_fields.get("cwd") or "")
    for each_call in _create_calls(all_payload_fields):
        if each_call.body is None or not _is_feature_title(each_call.title):
            continue
        section = _section_text(each_call.body, EVAL_HEADING_PATTERN)
        if section and COMMAND_MARKER in section:
            continue
        need_sentence = _eval_need_sentence(_changed_path_read_for_create(each_call, working_directory))
        if need_sentence is not None:
            return MISSING_EVAL_SECTION_REASON + need_sentence
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


def unproven_admissions(section: str) -> list[str]:
    """Return every prose line of a proof section that says something is not proven.

    ::

        "Not proven here: a fresh Convert run."   -> ["Not proven here: a fresh Convert run."]
        "The live run is untested."               -> ["The live run is untested."]
        "It has not been tested on the target."   -> ["It has not been tested on the target."]
        "`not proven` printed by the probe"       -> []
        "> Not proven here: the live run."        -> ["> Not proven here: the live run."]
        "Ran `python run.py`, quoted below."      -> []

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
    return [
        each_line.strip()
        for each_line, each_prose in _prose_lines(section)
        if re.search(UNPROVEN_ADMISSION_PATTERN, each_prose, re.IGNORECASE)
    ]



def merge_word_line(section: str, all_covered_names: list[str] | None = None) -> str | None:
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

    A line that is about the first run of a covered new workflow is skipped.

    Args:
        section: The text under the 'Proof in practice' heading.
        all_covered_names: The added workflow files the After merge section covers.
    """
    for each_line, each_prose in _prose_lines(section):
        if re.search(MERGE_WORD_PATTERN, each_prose, re.IGNORECASE) and not _admission_is_about_a_first_run(
            each_line, all_covered_names or []
        ):
            return each_line.strip()
    return None


def tier_sentence(tier_choice: TierChoice) -> str:
    """Return the sentence a proof deny ends with: the tier and the path or cause that set it.

    ::

        LIVE_SURFACE, "skills/a/SKILL.md"      -> LIVE_SURFACE_TIER_SENTENCE naming the path
        NO_DECLARED_SURFACES, "src/a.py"       -> NO_DECLARED_SURFACES_TIER_SENTENCE naming the path
        UNREAD_FILE_LIST, None                 -> UNREAD_FILE_LIST_TIER_SENTENCE
        CODE_WITHOUT_LIVE_SURFACE, "src/a.py"  -> CODE_WITHOUT_LIVE_SURFACE_TIER_SENTENCE naming the path
        ONLY_DOCS_AND_TESTS, None              -> ONLY_DOCS_AND_TESTS_TIER_SENTENCE

    Args:
        tier_choice: The tier the pull request's changed paths gave it.
    """
    all_sentences_by_cause = {
        TierCause.LIVE_SURFACE: LIVE_SURFACE_TIER_SENTENCE,
        TierCause.NO_DECLARED_SURFACES: NO_DECLARED_SURFACES_TIER_SENTENCE,
        TierCause.UNREAD_FILE_LIST: UNREAD_FILE_LIST_TIER_SENTENCE,
        TierCause.CODE_WITHOUT_LIVE_SURFACE: CODE_WITHOUT_LIVE_SURFACE_TIER_SENTENCE,
        TierCause.ONLY_DOCS_AND_TESTS: ONLY_DOCS_AND_TESTS_TIER_SENTENCE,
    }
    return all_sentences_by_cause[tier_choice.cause].format(path=tier_choice.deciding_path)


def _missing_proof_reason_for(tier_choice: TierChoice) -> str:
    base_reason = MISSING_PROOF_REASON if tier_choice.tier is EvidenceTier.LIVE else MISSING_CHECKED_PROOF_REASON
    return base_reason + tier_sentence(tier_choice)


def missing_proof_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a deny reason when a new pull request's body has no proof its evidence tier accepts, else None.

    ::

        gh pr create --body-file body.md, body has the section -> None
        live tier, body without the section                     -> MISSING_PROOF_REASON + tier
        checked tier, body without the section                  -> MISSING_CHECKED_PROOF_REASON + tier
        none tier, body without the section                     -> None
        none or checked tier, section with no command           -> MISSING_CHECKED_PROOF_REASON + tier
        live tier, proof whose only commands run tests          -> TEST_ONLY_PROOF_REASON + tier
        checked or none tier, proof whose only command is `pytest` -> None
        live tier, proof whose only command is `py.test`        -> TEST_ONLY_PROOF_REASON + tier
        live tier, only command `python -q -m unittest`         -> TEST_ONLY_PROOF_REASON + tier
        proof with `pytest` and `python run.py`                 -> None
        proof whose prose says "Not proven here: the run"      -> UNPROVEN_PROOF_REASON
        proof whose prose says "Not run: the live publish"     -> UNPROVEN_PROOF_REASON
        proof prose that says "I verify it after the merge"    -> DEFERRED_PROOF_REASON
        gh pr create --fill                                     -> MISSING_BODY_REASON
        gh pr edit, git push, any other tool                    -> None

    The tier comes from the paths the create changes; see tier_choice_for_create.
    A none tier passes without the section. A section that is there, in any
    tier, is a 'Proof in practice' heading whose text names at least one
    command in backticks. A command is an inline backticked span, or
    a line that starts with '$ ' inside a fenced block. A span that starts
    with a path:line is not a command. A span that is one path or file name is
    not a command unless that span runs a test runner, such as py.test or
    pytest.exe. In the live tier, when every command runs a test runner, such
    as pytest, python -m unittest, npm test, npx vitest, jest, go test or cargo
    test, the section is denied. Quotes around a runner word still count.
    Interpreter flags before -m unittest still count. coverage run -m unittest
    counts. A pipe into tee, tail, head, grep or cat keeps a test run a test run.
    A section whose prose says part of the change is not proven, untested or
    unverified is denied in every tier, with the line quoted;
    unproven_admissions lists the markers. A prose line with a merge word is
    denied in the proof section in every tier; merge_word_line lists the
    words. The unproven line passes when the pull
    request adds a workflow file the default branch lacks and the body has an
    'After merge' section that names that file in backticks and says who records
    the run, and the line uses the word run outside code spans and says workflow
    or GitHub Actions or names a covered workflow file; see
    _first_unwaived_admission. The same covered line is exempt from the merge word.
    The waiver reads the head branch of the create whose body holds the admission.
    A body whose section passes the live rules reads no file list.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    working_directory = str(all_payload_fields.get("cwd") or "")
    for each_call in _create_calls(all_payload_fields):
        if each_call.body is None:
            return MISSING_BODY_REASON
        read_tier = functools.partial(tier_choice_for_create, each_call, working_directory)
        section = proof_section(each_call.body)
        if section is None:
            tier_choice = read_tier()
            if tier_choice.tier is EvidenceTier.NONE:
                continue
            return _missing_proof_reason_for(tier_choice)
        section_reason = _proof_section_reason(section, read_tier, each_call, working_directory)
        if section_reason is not None:
            return section_reason
    return None


def _proof_section_reason(
    section: str,
    read_tier: Callable[[], TierChoice],
    create_call: CreateCall | None = None,
    working_directory: str = "",
) -> str | None:
    if COMMAND_MARKER not in section:
        return _missing_proof_reason_for(read_tier())
    if _proof_runs_only_tests(section):
        tier_choice = read_tier()
        if tier_choice.tier is EvidenceTier.LIVE:
            return TEST_ONLY_PROOF_REASON + tier_sentence(tier_choice)
    all_admissions = unproven_admissions(section)
    if create_call is None or create_call.body is None:
        unwaived_admission = all_admissions[0] if all_admissions else None
        all_covered_names: list[str] = []
    else:
        needs_waiver = bool(all_admissions) or merge_word_line(section) is not None
        all_covered_names = _covered_workflow_names(create_call, working_directory) if needs_waiver else []
        unwaived_admission = _first_unwaived_admission(all_admissions, all_covered_names)
    if unwaived_admission is not None:
        return UNPROVEN_PROOF_REASON.format(admission=unwaived_admission)
    deferral = merge_word_line(section, all_covered_names)
    return None if deferral is None else DEFERRED_PROOF_REASON.format(deferral=deferral)


class EditCall(NamedTuple):
    """One pull request body edit, with what tells whose pull request it edits.

    ``names_pull_request`` is True when the edit names a pull request by number,
    URL or branch, or comes from the update tool, so the checkout cannot be
    taken as that pull request's head.
    """

    body: str
    working_directory: str
    repository: str | None
    names_pull_request: bool


def edit_proof_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a deny reason when a pull request body edit holds a proof its tier would deny, else None.

    ::

        update_pull_request, proof section says "Not run: x"           -> UNPROVEN_PROOF_REASON
        gh pr edit --body-file, proof prose says "after the merge"     -> DEFERRED_PROOF_REASON
        update_pull_request, proof whose only command is `pytest`      -> TEST_ONLY_PROOF_REASON + tier
        gh pr edit --body-file from a docs-only head checkout, `pytest` -> None
        gh pr edit 7 --body-file, proof whose only command is `pytest` -> TEST_ONLY_PROOF_REASON + tier
        update_pull_request, body with no proof section                -> None
        update_pull_request with no body, create calls, any tool       -> None

    An edit with no proof heading passes. A proof heading that is there meets
    the rules a new pull request of the same tier meets. The tier comes from
    the checkout only for a gh pr edit that names no pull request, so it edits
    the pull request of the checked-out branch, run from a checkout of the
    repository it names, with a readable file list. Every other edit gets the
    live tier. The edit comes through the
    update_pull_request tool, gh pr edit, or the pull_request.py edit script.
    A body this gate cannot read passes unread: an inline multi-line --body,
    --body-file - from standard input, a $(...) body, a --body-file path that
    an earlier cd changes, a gh global option before pr edit, or a gh api call.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    for each_call in _edit_calls(all_payload_fields):
        section = proof_section(each_call.body)
        if section is None:
            continue
        edit_reason = _proof_section_reason(section, functools.partial(_edit_tier_choice, each_call))
        if edit_reason is not None:
            return edit_reason
    return None


def _edit_tier_choice(edit_call: EditCall) -> TierChoice:
    if edit_call.names_pull_request or not edit_call.working_directory:
        return choose_tier(None, None)
    return _tier_choice(edit_call.working_directory, edit_call.repository, None, None)


def _edit_names_a_pull_request(all_edit_arguments: list[str]) -> bool:
    is_flag_value = False
    for each_argument in all_edit_arguments:
        word = unquoted_token(each_argument)
        if is_flag_value:
            is_flag_value = False
            continue
        if word.partition(FLAG_ASSIGNMENT_MARKER)[0] in ALL_EDIT_NUMBER_FLAGS or not word.startswith(FLAG_PREFIX):
            return True
        is_flag_value = FLAG_ASSIGNMENT_MARKER not in word and word not in ALL_GH_EDIT_BOOLEAN_FLAGS
    return False


def _edit_calls(all_payload_fields: Mapping[str, object]) -> list[EditCall]:
    tool_name = all_payload_fields.get("tool_name")
    tool_input = all_payload_fields.get("tool_input")
    if isinstance(tool_name, str) and tool_name.endswith(UPDATE_PULL_REQUEST_TOOL_SUFFIX):
        body = tool_input.get("body") if isinstance(tool_input, dict) else None
        return [EditCall(body, "", None, True)] if isinstance(body, str) else []
    command = shell_command(all_payload_fields)
    if command is None:
        return []
    raw_working_directory = all_payload_fields.get("cwd")
    working_directory = raw_working_directory if isinstance(raw_working_directory, str) else ""
    all_edit_calls = []
    for each_arguments in _all_edit_argument_lists(command):
        body = body_from_arguments(each_arguments, working_directory)
        if body is None:
            continue
        repository = _flag_value(each_arguments, ALL_REPOSITORY_FLAGS, REPOSITORY_FLAG_ASSIGNMENT_PREFIX) or None
        all_edit_calls.append(EditCall(body, working_directory, repository, _edit_names_a_pull_request(each_arguments)))
    return all_edit_calls


def _edit_bodies(all_payload_fields: Mapping[str, object]) -> list[str]:
    return [each_call.body for each_call in _edit_calls(all_payload_fields)]


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


def has_flowchart_under_what_this_does(body: str) -> bool:
    """Return whether the body's 'What this does' section holds a mermaid flowchart.

    ::

        "## What this does\\n```mermaid\\nflowchart LR\\n a --> b\\n```" -> True
        "## What this does\\nwords only"                                  -> False
        "## Summary\\nno what-this-does heading"                          -> False

    Args:
        body: The pull request body.
    """
    section = what_this_does_section(body)
    return section is not None and section_has_flowchart(section)


def missing_flowchart_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a deny reason when a pull request body has no flowchart under 'What this does', else None.

    ::

        MCP create, flowchart under the heading        -> None
        MCP create, text only under the heading        -> MISSING_FLOWCHART_REASON
        MCP create, no 'What this does' heading        -> MISSING_FLOWCHART_REASON
        update_pull_request, heading and no flowchart  -> MISSING_FLOWCHART_REASON
        update_pull_request, no 'What this does' heading -> None
        a create with --fill, any other tool           -> None

    A new pull request needs the flowchart. A body edit needs it only when the
    body carries the heading, so an edit to an older body passes. A create
    command whose body this gate cannot read passes here, because
    missing_proof_reason denies it first.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    for each_body in _create_bodies(all_payload_fields):
        if each_body is not None and not has_flowchart_under_what_this_does(each_body):
            return MISSING_FLOWCHART_REASON
    for each_body in _edit_bodies(all_payload_fields):
        if what_this_does_section(each_body) is not None and not has_flowchart_under_what_this_does(each_body):
            return MISSING_FLOWCHART_REASON
    return None


class ChangedFile(NamedTuple):
    path: str
    old_path: str
    is_pure_rename: bool


def _git_output(working_directory: str, *all_git_arguments: str) -> str | None:
    return child_stdout(
        ["git", "-C", working_directory, *all_git_arguments], GIT_TIMEOUT_SECONDS, ReadSlice.PROOF_AND_LOOK
    )


def _git_lines(working_directory: str, *all_git_arguments: str) -> list[str] | None:
    output = _git_output(working_directory, *all_git_arguments)
    return output.splitlines() if output is not None else None


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
        page.html renamed with no edit          -> []
        page.html renamed and edited            -> ["page.html"]
        named head exists nowhere in the clone  -> None
        no base reference reachable             -> None

    A rename whose old and new blob ids match and whose old and new names end the
    same way, such as a.html to b/a.html, changes nothing people see. One that
    changes the ending, such as notes.txt or Widget.tsx to page.html, still makes a
    page. A copy or a rename with an edit keeps its path.

    Args:
        working_directory: The session directory the hook payload names.
        head_branch: The head branch a create call names, or None.
    """
    all_changes = _local_changes(working_directory, head_branch)
    return None if all_changes is None else _visible_paths(all_changes)


def _local_changes(working_directory: str, head_branch: object) -> list[ChangedFile] | None:
    named_head = head_branch if isinstance(head_branch, str) else None
    return answer_once(
        ("local changes", working_directory, named_head),
        lambda: _read_local_changes(working_directory, named_head),
    )


def _read_local_changes(working_directory: str, head_branch: str | None) -> list[ChangedFile] | None:
    merge_base_and_head = _merge_base_and_head(working_directory, head_branch)
    if merge_base_and_head is None:
        return None
    raw_output = _git_output(working_directory, "diff", "--raw", "--no-abbrev", "-M", "-z", *merge_base_and_head)
    return None if raw_output is None else _git_changes(raw_output.split("\0"))


def _merge_base_and_head(working_directory: str, head_branch: object) -> tuple[str, str] | None:
    named_head = head_branch if isinstance(head_branch, str) else None
    return answer_once(
        ("merge base and head", working_directory, named_head),
        lambda: _read_merge_base_and_head(working_directory, named_head),
    )


def _read_merge_base_and_head(working_directory: str, head_branch: str | None) -> tuple[str, str] | None:
    if not working_directory:
        return None
    head_reference = _head_reference(working_directory, head_branch)
    if head_reference is None:
        return None
    merge_base = _first_merge_base(working_directory, head_reference)
    return None if merge_base is None else (merge_base, head_reference)


def _git_changes(all_raw_fields: list[str]) -> list[ChangedFile] | None:
    all_changes = []
    field_index = 0
    while field_index < len(all_raw_fields) and all_raw_fields[field_index].startswith(RAW_RECORD_PREFIX):
        all_header_fields = all_raw_fields[field_index][1:].split(" ")
        if len(all_header_fields) != RAW_HEADER_FIELD_COUNT:
            return None
        old_mode, new_mode, old_blob, new_blob, status = all_header_fields
        path_count = RAW_RENAME_PATH_COUNT if status[:1] in ALL_RAW_TWO_PATH_STATUS_LETTERS else 1
        all_paths = all_raw_fields[field_index + 1 : field_index + 1 + path_count]
        if len(all_paths) != path_count:
            return None
        is_pure_rename = status.startswith(RAW_RENAME_STATUS_LETTER) and old_mode == new_mode and old_blob == new_blob
        all_changes.append(ChangedFile(path=all_paths[-1], old_path=all_paths[0], is_pure_rename=is_pure_rename))
        field_index += 1 + path_count
    if any(all_raw_fields[field_index:]):
        return None
    return all_changes


def _compare_changes(all_json_lines: list[str]) -> list[ChangedFile] | None:
    all_changes = []
    for each_line in all_json_lines:
        try:
            status, old_path, path = json.loads(each_line)
        except (ValueError, TypeError):
            return None
        all_changes.append(ChangedFile(path=path, old_path=old_path, is_pure_rename=status == PURE_RENAME_STATUS))
    return all_changes


def _visible_suffix(path: str) -> str | None:
    lowered_path = path.lower()
    for each_suffix in ALL_VISIBLE_FILE_SUFFIXES:
        if lowered_path.endswith(each_suffix):
            return each_suffix
    return None


def _is_unchanged_move(change: ChangedFile) -> bool:
    return change.is_pure_rename and _visible_suffix(change.old_path) == _visible_suffix(change.path)


def _visible_paths(all_changes: list[ChangedFile]) -> list[str]:
    return [
        each_change.path
        for each_change in all_changes
        if _visible_suffix(each_change.path) is not None and not _is_unchanged_move(each_change)
    ]


def _workflow_paths(all_added_paths: list[str]) -> list[str]:
    return [each_path for each_path in all_added_paths if re.match(NEW_WORKFLOW_PATH_PATTERN, each_path)]


def added_workflow_files(working_directory: str, head_branch: object) -> list[str] | None:
    """Return the workflow files the head branch adds, or None when git cannot tell.

    The head and base are chosen as in visible_changed_files. Only a file git
    reports as added counts, and a rename counts as an add, so a workflow the
    branch edits is left out::

        branch adds .github/workflows/release.yml   -> [".github/workflows/release.yml"]
        branch edits an existing workflow           -> []
        named head exists nowhere in the clone      -> None

    Args:
        working_directory: The session directory the hook payload names.
        head_branch: The head branch a create call names, or None.
    """
    merge_base_and_head = _merge_base_and_head(working_directory, head_branch)
    if merge_base_and_head is None:
        return None
    all_added_paths = _git_lines(
        working_directory, "diff", "--name-only", "--no-renames", "--diff-filter=A", *merge_base_and_head
    )
    return None if all_added_paths is None else _workflow_paths(all_added_paths)


def _gh_api_lines(endpoint: str, query: str) -> list[str] | None:
    printed_text = child_stdout(["gh", "api", endpoint, "--jq", query], GH_TIMEOUT_SECONDS, ReadSlice.PROOF_AND_LOOK)
    return None if printed_text is None else printed_text.splitlines()


def _compare_base_branch(repository: str, base_branch: str | None) -> str | None:
    if base_branch:
        return base_branch
    return answer_once(("default branch", repository), lambda: _read_default_branch(repository))


def _read_default_branch(repository: str) -> str | None:
    all_default_branch_lines = _gh_api_lines(
        REPOSITORY_ENDPOINT_TEMPLATE.format(repository=repository), DEFAULT_BRANCH_QUERY
    )
    if not all_default_branch_lines:
        return None
    return all_default_branch_lines[0]


def _compare_lines(
    repository: str | None, base_branch: str | None, head_branch: str | None, query: str
) -> list[str] | None:
    if not repository or not head_branch:
        return None
    resolved_base_branch = _compare_base_branch(repository, base_branch)
    if resolved_base_branch is None:
        return None
    return _gh_api_lines(
        COMPARE_ENDPOINT_TEMPLATE.format(
            repository=repository, base_branch=resolved_base_branch, head_branch=head_branch
        ),
        query,
    )


def remote_visible_changed_files(
    repository: str | None, base_branch: str | None, head_branch: str | None
) -> list[str] | None:
    """Return the changed files people see, read from the GitHub compare API, or None when it cannot tell.

    ::

        compare lists tool.py                          -> []
        compare lists web/page.html                    -> ["web/page.html"]
        compare lists web/page.html renamed, no edit   -> []
        compare returns 300 paths and none are visible -> None
        repository or head missing                     -> None

    The base is the named base branch, else the repository's default branch.
    A page of 300 paths is the compare API's file cap. A visible file on that
    page is returned. A full page with none is None, because a later file can
    still be one people see. A pure rename counts toward the 300. It is not
    visible when the file it moved from ended the same way.

    Args:
        repository: The owner/name the create call names, or None.
        base_branch: The base branch the create call names, or None.
        head_branch: The head branch the create call names, or None.
    """
    all_status_lines = _compare_status_lines(repository, base_branch, head_branch)
    if all_status_lines is None:
        return None
    all_changes = _compare_changes(all_status_lines)
    if all_changes is None:
        return None
    all_visible_paths = _visible_paths(all_changes)
    if all_visible_paths or len(all_status_lines) < COMPARE_FILE_LIST_LIMIT:
        return all_visible_paths
    return None


def remote_added_workflow_files(
    repository: str | None, base_branch: str | None, head_branch: str | None
) -> list[str] | None:
    """Return the workflow files the head branch adds, read from the GitHub compare API, or None.

    ::

        compare adds .github/workflows/release.yml     -> [".github/workflows/release.yml"]
        compare adds only tool.py                      -> []
        compare returns 300 files and adds no workflow -> None
        repository or head missing                     -> None

    A full page of 300 files is the compare API's cap, so a workflow could sit
    on a later page and the answer is None.

    Args:
        repository: The owner/name the create call names, or None.
        base_branch: The base branch the create call names, or None.
        head_branch: The head branch the create call names, or None.
    """
    all_lines = _compare_lines(repository, base_branch, head_branch, ADDED_FILE_NAMES_QUERY)
    if not all_lines or not all_lines[0].isdigit():
        return None
    all_workflow_paths = _workflow_paths(all_lines[1:])
    if all_workflow_paths or int(all_lines[0]) < COMPARE_FILE_LIST_LIMIT:
        return all_workflow_paths
    return None


def _added_workflow_files_for_create(create_call: CreateCall, working_directory: str) -> list[str]:
    repository, base_branch, head_branch = create_call.repository, create_call.base, create_call.head
    return answer_once(
        ("added workflow files", working_directory, repository, base_branch, head_branch),
        lambda: _read_added_workflow_files(working_directory, repository, base_branch, head_branch),
    )


def _read_added_workflow_files(
    working_directory: str, repository: str | None, base_branch: str | None, head_branch: str | None
) -> list[str]:
    all_workflow_paths = None
    if _local_checkout_may_answer(working_directory, repository, head_branch):
        all_workflow_paths = added_workflow_files(working_directory, head_branch)
    if all_workflow_paths is None:
        all_workflow_paths = remote_added_workflow_files(repository, base_branch, head_branch)
    return all_workflow_paths or []


def _local_checkout_may_answer(
    working_directory: str, repository: str | None, head_branch: str | None
) -> bool:
    return not head_branch or checkout_is_for(working_directory, repository)


def checkout_is_for(working_directory: str, repository: str | None) -> bool:
    if repository is None:
        return True
    all_remote_lines = _git_lines(working_directory, "remote", "-v") if working_directory else None
    all_repository_endings = ("/" + repository.lower(), ":" + repository.lower())
    for each_line in all_remote_lines or []:
        all_fields = each_line.split()
        if len(all_fields) >= REMOTE_LINE_FIELD_COUNT and all_fields[1].lower().rstrip("/").removesuffix(GIT_URL_SUFFIX).endswith(
            all_repository_endings
        ):
            return True
    return False


def _first_unwaived_admission(all_admissions: list[str], all_covered_names: list[str]) -> str | None:
    """Return the first unproven line a new workflow's after-merge run does not explain, or None.

    ::

        "Not proven here: the live GitHub Actions run." with a covered new workflow -> None
        "Untested on Windows." with a covered new workflow                          -> that line
        "Not proven here: the live GitHub Actions run." with no covered workflow    -> that line
        no unproven line                                                            -> None

    Each admission line must use the word run and also say GitHub Actions or
    workflow, or name a covered workflow file, so an admission about anything
    else keeps the refusal. The line returned is the one that failed.

    Args:
        all_admissions: The proof section's unproven lines.
        all_covered_names: The added workflow files the After merge section covers.
    """
    return next(
        (each for each in all_admissions if not _admission_is_about_a_first_run(each, all_covered_names)), None
    )


def _admission_is_about_a_first_run(admission: str, all_workflow_names: list[str]) -> bool:
    admission_prose = re.sub(INLINE_CODE_SPAN_PATTERN, "", admission)
    if not all_workflow_names or re.search(RUN_WORD_PATTERN, admission_prose, re.IGNORECASE) is None:
        return False
    return re.search(WORKFLOW_SUBJECT_PATTERN, admission_prose, re.IGNORECASE) is not None or any(
        re.search(WORKFLOW_NAME_MATCH_TEMPLATE.format(workflow_name=re.escape(each_name)), admission, re.IGNORECASE)
        for each_name in all_workflow_names
    )


def _covered_workflow_names(create_call: CreateCall, working_directory: str) -> list[str]:
    """Return the added workflow files whose first run the body plans for after the merge.

    ::

        adds release.yml, "## After merge" names `release.yml` and "records the run link" -> ["release.yml"]
        the branch adds no workflow file, or git and the compare API cannot tell          -> []

    A workflow added by a pull request runs only from the default branch, so
    its live run cannot come before the merge. The section must name the added
    workflow file in backticks, by file name or by its full path, and say who
    records the run or its link in prose. Code spans and fenced blocks do not
    count as that prose. A sentence with a negation ahead of the verb does not count.

    Args:
        create_call: The create whose body and head branch are read.
        working_directory: The session directory the hook payload names.
    """
    after_merge = _section_text(create_call.body or "", AFTER_MERGE_HEADING_PATTERN)
    if not after_merge:
        return []
    outside_fence_text = _text_outside_fences(after_merge)
    if not _prose_names_a_recorder(re.sub(INLINE_CODE_SPAN_PATTERN, "", outside_fence_text)):
        return []
    all_names = []
    for each_path in _added_workflow_files_for_create(create_call, working_directory):
        each_name = each_path.rsplit("/", 1)[-1]
        if f"`{each_path}`" in outside_fence_text or f"`{each_name}`" in outside_fence_text:
            all_names.append(each_name)
    return all_names


def _text_outside_fences(section: str) -> str:
    return LINE_SEPARATOR.join(
        each_line for each_line, each_is_inside_fence in _lines_with_fence_state(section) if not each_is_inside_fence
    )


def _prose_names_a_recorder(prose: str) -> bool:
    return any(
        re.search(AFTER_MERGE_RECORDER_PATTERN, each_sentence, re.IGNORECASE) is not None
        and re.search(AFTER_MERGE_NO_RECORDER_PATTERN, each_sentence, re.IGNORECASE) is None
        for each_sentence in re.split(AFTER_MERGE_SENTENCE_SEPARATOR_PATTERN, prose)
    )


def missing_look_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a deny reason when a pull request changing visible files shows no picture, else None.

    ::

        branch changes page.html, proof has ![after](https://x/after.png) -> None
        branch changes page.html, proof quotes only command output        -> MISSING_LOOK_REASON
        branch changes only .py files                                     -> None
        git cannot read the branch, compare API lists only .py files      -> None
        git cannot read the branch, compare API returns 300 .py files     -> UNREADABLE_CHANGES_REASON
        neither git nor the compare API can read it, no picture           -> UNREADABLE_CHANGES_REASON
        create --head a && create --head b, only b changes page.html      -> MISSING_LOOK_REASON

    Every body is checked for a picture first. When each one shows a picture,
    the check passes and reads neither git nor the compare API. Each create
    is checked against its own head, base and repository, in command order,
    and the first deny wins.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    working_directory = str(all_payload_fields.get("cwd") or "")
    all_calls_without_picture = [
        each_call
        for each_call in _create_calls(all_payload_fields)
        if each_call.body is not None
        and not re.search(PROOF_IMAGE_PATTERN, proof_section(each_call.body) or "", re.IGNORECASE)
    ]
    all_reasons = (_look_reason_for_create(each_call, working_directory) for each_call in all_calls_without_picture)
    return next((each_reason for each_reason in all_reasons if each_reason is not None), None)


def _look_reason_for_create(create_call: CreateCall, working_directory: str) -> str | None:
    all_visible_files = _visible_files_for_create(create_call, working_directory)
    if all_visible_files == []:
        return None
    if all_visible_files is None:
        return UNREADABLE_CHANGES_REASON
    return MISSING_LOOK_REASON.format(changed_files=CHANGED_FILES_SEPARATOR.join(all_visible_files))


def _visible_files_for_create(create_call: CreateCall, working_directory: str) -> list[str] | None:
    repository, base_branch, head_branch = create_call.repository, create_call.base, create_call.head
    return answer_once(
        ("visible changed files", working_directory, repository, base_branch, head_branch),
        lambda: _read_visible_files(working_directory, repository, base_branch, head_branch),
    )


def _read_visible_files(
    working_directory: str, repository: str | None, base_branch: str | None, head_branch: str | None
) -> list[str] | None:
    all_visible_files = visible_changed_files(working_directory, head_branch)
    if all_visible_files is None:
        return remote_visible_changed_files(repository, base_branch, head_branch)
    return all_visible_files


def _compare_status_lines(
    repository: str | None, base_branch: str | None, head_branch: str | None
) -> list[str] | None:
    return answer_once(
        ("compare status lines", repository, base_branch, head_branch),
        lambda: _compare_lines(repository, base_branch, head_branch, COMPARE_FILE_STATUS_QUERY),
    )


class ChangedPathRead(NamedTuple):
    """Every path a pull request changes, and whether the local checkout listed them."""

    all_paths: list[str]
    is_local: bool


def _changed_paths(all_changes: list[ChangedFile]) -> list[str]:
    all_paths = (
        each_path for each_change in all_changes for each_path in (each_change.old_path, each_change.path) if each_path
    )
    return list(dict.fromkeys(all_paths))


def _changed_path_read(
    working_directory: str, repository: str | None, base_branch: str | None, head_branch: str | None
) -> ChangedPathRead | None:
    return answer_once(
        ("changed paths", working_directory, repository, base_branch, head_branch),
        lambda: _read_changed_paths(working_directory, repository, base_branch, head_branch),
    )


def _read_changed_paths(
    working_directory: str, repository: str | None, base_branch: str | None, head_branch: str | None
) -> ChangedPathRead | None:
    if working_directory and checkout_is_for(working_directory, repository):
        all_local_changes = _local_changes(working_directory, head_branch)
        if all_local_changes is not None:
            return ChangedPathRead(_changed_paths(all_local_changes), is_local=True)
    all_status_lines = _compare_status_lines(repository, base_branch, head_branch)
    if all_status_lines is None or len(all_status_lines) >= COMPARE_FILE_LIST_LIMIT:
        return None
    all_remote_changes = _compare_changes(all_status_lines)
    return None if all_remote_changes is None else ChangedPathRead(_changed_paths(all_remote_changes), is_local=False)


def _changed_path_read_for_create(create_call: CreateCall, working_directory: str) -> ChangedPathRead | None:
    return _changed_path_read(working_directory, create_call.repository, create_call.base, create_call.head)


def _local_surfaces_file_text(working_directory: str, head_branch: str | None) -> str | None:
    merge_base_and_head = _merge_base_and_head(working_directory, head_branch)
    if merge_base_and_head is None:
        return None
    return _git_output(working_directory, "show", f"{merge_base_and_head[0]}:{LIVE_SURFACES_FILE_PATH}")


def _remote_surfaces_file_text(repository: str | None, base_branch: str | None) -> str | None:
    resolved_base_branch = _compare_base_branch(repository, base_branch) if repository else None
    if resolved_base_branch is None:
        return None
    all_content_lines = _gh_api_lines(
        CONTENTS_ENDPOINT_TEMPLATE.format(
            repository=repository, path=LIVE_SURFACES_FILE_PATH, reference=resolved_base_branch
        ),
        CONTENTS_QUERY,
    )
    if all_content_lines is None:
        return None
    try:
        return base64.b64decode("".join(all_content_lines)).decode(DECLARED_SURFACES_FILE_ENCODING)
    except (binascii.Error, UnicodeDecodeError):
        return None


def _declared_globs(
    path_read: ChangedPathRead,
    working_directory: str,
    repository: str | None,
    base_branch: str | None,
    head_branch: str | None,
) -> tuple[str, ...] | None:
    if path_read.is_local:
        surfaces_file_text = _local_surfaces_file_text(working_directory, head_branch)
    else:
        surfaces_file_text = _remote_surfaces_file_text(repository, base_branch)
    return None if surfaces_file_text is None else declared_live_surface_globs(surfaces_file_text)


def _tier_choice(
    working_directory: str, repository: str | None, base_branch: str | None, head_branch: str | None
) -> TierChoice:
    return answer_once(
        ("evidence tier", working_directory, repository, base_branch, head_branch),
        lambda: _read_tier_choice(working_directory, repository, base_branch, head_branch),
    )


def _read_tier_choice(
    working_directory: str, repository: str | None, base_branch: str | None, head_branch: str | None
) -> TierChoice:
    path_read = _changed_path_read(working_directory, repository, base_branch, head_branch)
    if path_read is None or not path_read.all_paths:
        return choose_tier(None, None)
    all_declared_globs = _declared_globs(path_read, working_directory, repository, base_branch, head_branch)
    return choose_tier(path_read.all_paths, all_declared_globs)


def tier_choice_for_create(create_call: CreateCall, working_directory: str) -> TierChoice:
    """Return the evidence tier one create call's changed paths give it.

    ::

        checkout of the head, only docs and tests changed      -> ONLY_DOCS_AND_TESTS
        checkout of the head, src/a.py changed, base globs     -> CODE_WITHOUT_LIVE_SURFACE, "src/a.py"
        checkout of the head, src/a.py, base has no globs file -> NO_DECLARED_SURFACES, "src/a.py"
        skills/a/SKILL.md changed                              -> LIVE_SURFACE, "skills/a/SKILL.md"
        no checkout of the repository, compare API unread     -> UNREAD_FILE_LIST
        compare API returns its 300-file cap                   -> UNREAD_FILE_LIST

    The changed paths come from git in the working directory when that
    checkout's origin is the repository the create names, else from the GitHub
    compare API. A rename or a copy adds the path it came from too. The
    declared globs come from .claude/live-surfaces.txt at the merge base for a
    local read, or on the base branch through the contents API for a remote
    read; the working tree's copy is never read. The tier and every read
    behind it are read once per gate run.

    Args:
        create_call: The create whose head, base and repository are read.
        working_directory: The session directory the hook payload names.
    """
    return _tier_choice(working_directory, create_call.repository, create_call.base, create_call.head)


def checkout_sections(working_directory: str) -> dict[str, bool]:
    """Return which proof sections a pull request from this checkout's branch owes.

    ::

        docs-only branch                      -> {"needs_proof_section": False, "needs_eval_section_for_a_feature": False}
        src/a.py changed, no globs file        -> {"needs_proof_section": True, "needs_eval_section_for_a_feature": False}
        skills/a/SKILL.md changed              -> {"needs_proof_section": True, "needs_eval_section_for_a_feature": True}
        not a git checkout                     -> {"needs_proof_section": True, "needs_eval_section_for_a_feature": True}

    Args:
        working_directory: The checkout of the head branch.
    """
    with gate_run():
        tier_choice = _tier_choice(working_directory, None, None, None)
        path_read = _changed_path_read(working_directory, None, None, None)
    return {
        NEEDS_PROOF_SECTION_KEY: tier_choice.tier is not EvidenceTier.NONE,
        NEEDS_EVAL_SECTION_KEY: _eval_need_sentence(path_read) is not None,
    }


def main() -> int:
    """Print, as JSON, which proof sections a pull request from the named checkout owes."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("working_directory")
    arguments = parser.parse_args()
    sys.stdout.write(json.dumps(checkout_sections(arguments.working_directory)) + LINE_SEPARATOR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
