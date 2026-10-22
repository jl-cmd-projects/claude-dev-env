"""Deny pull request lifecycle actions until their skill appears in the transcript."""

from __future__ import annotations

import re
import shlex
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.pr_lifecycle_skill_gate_constants import (
    AGENT_ID_FIELD,
    AGENT_ID_PATTERN,
    ALL_BUILD_EVAL_SKILL_NAMES,
    ALL_API_ACTION_NAMES,
    ALL_COMMAND_PREFIX_WORDS,
    ALL_GITHUB_MCP_TOOL_SUFFIXES,
    ALL_PREFIX_OPTIONS_WITH_VALUE,
    ALL_PYTHON_EXECUTABLES,
    ALL_SHELL_WRAPPER_EXECUTABLES,
    ALL_SLASH_COMMAND_MARKERS,
    ALL_TRANSCRIPT_PATH_FIELDS,
    BUILD_EVAL_ARGUMENT_WORD,
    BUILD_EVAL_COMMAND_MARKER,
    COMMAND_PIECE_PATTERN,
    COMMAND_WHITESPACE,
    COMMENT_PIECE,
    DENY_DECISION,
    DENY_REASON,
    ENVIRONMENT_ASSIGNMENT_PATTERN,
    GH_API_COMMAND,
    GH_PULL_REQUEST_COMMAND,
    GIT_ACTIONS,
    GIT_GLOBAL_OPTIONS_WITH_VALUE,
    HOOK_EVENT_NAME,
    LINE_CONTINUATION_PIECE,
    MERGE_PATH_SUFFIX,
    NO_COMMENT_CHARACTERS,
    OPTION_AND_VALUE_WORD_COUNT,
    PATH_SEPARATOR_PATTERN,
    PERMISSION_DECISION_REASON_KEY,
    PULL_REQUEST_SCRIPT_NAME,
    PYTHON_OPTIONS_WITH_VALUE,
    REMOVED_TEXT,
    SEGMENT_BREAK,
    SEPARATOR_PIECE,
    SESSION_TRANSCRIPT_PATH_FIELD,
    SHELL_TOOL_NAMES,
    SKILL_NAME,
    SUBAGENT_TRANSCRIPT_DIRECTORY_NAME,
    SUBAGENT_TRANSCRIPT_FILE_TEMPLATE,
    UNCLOSED_QUOTE_PIECE,
)
from hooks_constants.gh_command_words import gh_command_words
from hooks_constants.hook_specific_output_keys import (
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
)
from hooks_constants.pre_tool_use_stdin import print_decision_from_stdin
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING
from blocking.followup_pr_dedupe import create_tool_fields, duplicate_followup_reason
from blocking.pull_request_proof import (
    is_feature_pull_request,
    missing_eval_section_reason,
    missing_existing_work_reason,
    missing_look_reason,
    missing_proof_reason,
)
from hooks_constants.pull_request_proof_constants import MISSING_BUILD_EVAL_REASON
from transcript_skill_scan import (
    invokes_skill_with_argument,
    is_skill_loaded_after_last_compaction,
)


def _unquoted_segment_texts(command: str) -> list[str] | None:
    """Split a command at each separator outside quotes, escapes, and comments.

    ::

        git commit -m "&" -a && git push  ->  ['git commit -m "&" -a ', '', ' git push']
        git status # a; b                 ->  ['git status ']

    Args:
        command: One shell command as the tool received it.

    Returns:
        The raw text of each segment in order, or None when a quote never closes.
    """
    all_pieces = list(COMMAND_PIECE_PATTERN.finditer(command))
    if any(each_piece.lastgroup == UNCLOSED_QUOTE_PIECE for each_piece in all_pieces):
        return None
    all_replacement_texts: dict[str | None, str] = {
        SEPARATOR_PIECE: SEGMENT_BREAK,
        COMMENT_PIECE: REMOVED_TEXT,
        LINE_CONTINUATION_PIECE: REMOVED_TEXT,
    }
    marked_command = REMOVED_TEXT.join(
        all_replacement_texts.get(each_piece.lastgroup, each_piece.group()) for each_piece in all_pieces
    )
    return marked_command.split(SEGMENT_BREAK)


def _command_segments(command: str) -> list[list[str]]:
    all_segment_texts = _unquoted_segment_texts(command)
    if all_segment_texts is None:
        return []
    all_segments: list[list[str]] = []
    for each_text in all_segment_texts:
        lexer = shlex.shlex(each_text, posix=True)
        lexer.whitespace = COMMAND_WHITESPACE
        lexer.whitespace_split = True
        lexer.commenters = NO_COMMENT_CHARACTERS
        try:
            all_words = list(lexer)
        except ValueError:
            return []
        if all_words:
            all_segments.append(all_words)
    return all_segments


def next_command_word(
    all_words: list[str], start: int, all_options_with_value: frozenset[str]
) -> tuple[str | None, int]:
    """Return the first word from ``start`` that is no option, and the index after it.

    ::

        ["git", "-C", "repo", "commit"], 1, {"-C"}  -> ("commit", 4)
        ["git", "--no-pager"], 1, {"-C"}            -> (None, 2)

    Args:
        all_words: One command's words, executable first.
        start: The index to start reading at.
        all_options_with_value: Options whose next word is their value.
    """
    index = start
    while index < len(all_words):
        each_word = all_words[index]
        if each_word in all_options_with_value:
            index += OPTION_AND_VALUE_WORD_COUNT
            continue
        if each_word.startswith("-"):
            index += 1
            continue
        return each_word, index + 1
    return None, index


def _is_git_action(all_words: list[str]) -> bool:
    action, _ = next_command_word(all_words, 1, GIT_GLOBAL_OPTIONS_WITH_VALUE)
    return action in GIT_ACTIONS


def _is_gh_action(all_words: list[str]) -> bool:
    all_gh_words = gh_command_words(all_words[1:])
    if all_gh_words[:1] == [GH_PULL_REQUEST_COMMAND]:
        return len(all_gh_words) > 1
    if all_gh_words[:1] != [GH_API_COMMAND]:
        return False
    all_api_arguments = all_words[all_words.index(GH_API_COMMAND, 1) + 1 :]
    if any(each_name in each_word for each_word in all_api_arguments for each_name in ALL_API_ACTION_NAMES):
        return True
    return any(
        each_word.split("?", 1)[0].rstrip("/").endswith(MERGE_PATH_SUFFIX)
        for each_word in all_api_arguments
    )


def _words_from_executable(all_words: list[str]) -> list[str]:
    index = 0
    while index < len(all_words):
        each_word = all_words[index]
        if re.match(ENVIRONMENT_ASSIGNMENT_PATTERN, each_word):
            index += 1
            continue
        if each_word not in ALL_COMMAND_PREFIX_WORDS:
            return all_words[index:]
        index += 1
        while index < len(all_words) and all_words[index].startswith("-"):
            is_valued = all_words[index] in ALL_PREFIX_OPTIONS_WITH_VALUE
            index += OPTION_AND_VALUE_WORD_COUNT if is_valued else 1
    return []


def file_name(path_word: str) -> str:
    """Return the lowercased last path part of a word, such as ``git.exe`` for ``C:\\Git\\git.exe``.

    Args:
        path_word: A command word that may carry a path.
    """
    return re.split(PATH_SEPARATOR_PATTERN, path_word)[-1].lower()


def _runs_pull_request_script(all_words: list[str]) -> bool:
    script, _ = next_command_word(all_words, 1, PYTHON_OPTIONS_WITH_VALUE)
    return script is not None and file_name(script) == PULL_REQUEST_SCRIPT_NAME


def executable_word_lists(command: str) -> list[list[str]]:
    """Return each command's words from its executable on, with shell wrapper arguments read as commands.

    ::

        "cd repo && git commit -m x"        -> [["cd", "repo"], ["git", "commit", "-m", "x"]]
        "env A=1 git push"                  -> [["git", "push"]]
        "bash -c 'git add x; git commit'"   -> ends with [["git", "add", "x"], ["git", "commit"]]

    Args:
        command: The shell command text.
    """
    all_word_lists: list[list[str]] = []
    for each_segment in _command_segments(command):
        all_command_words = _words_from_executable(each_segment)
        if not all_command_words:
            continue
        all_word_lists.append(all_command_words)
        all_word_lists.extend(_wrapped_word_lists(all_command_words))
    return all_word_lists


def _wrapped_word_lists(all_command_words: list[str]) -> list[list[str]]:
    if file_name(all_command_words[0]) not in ALL_SHELL_WRAPPER_EXECUTABLES:
        return []
    return [
        each_word_list
        for each_argument in all_command_words[1:]
        for each_word_list in executable_word_lists(each_argument)
    ]


def _matches_shell_command(command: str) -> bool:
    for each_command_words in executable_word_lists(command):
        executable = file_name(each_command_words[0])
        if executable == PULL_REQUEST_SCRIPT_NAME:
            return True
        if executable in ALL_PYTHON_EXECUTABLES and _runs_pull_request_script(each_command_words):
            return True
        if executable in {"git", "git.exe"} and _is_git_action(each_command_words):
            return True
        if executable in {"gh", "gh.exe"} and _is_gh_action(each_command_words):
            return True
    return False


def _is_governed_action(all_payload_fields: dict[str, object]) -> bool:
    tool_name = all_payload_fields.get("tool_name")
    if not isinstance(tool_name, str):
        return False
    if tool_name.endswith(ALL_GITHUB_MCP_TOOL_SUFFIXES) or create_tool_fields(all_payload_fields) is not None:
        return True
    if tool_name not in SHELL_TOOL_NAMES:
        return False
    tool_input = all_payload_fields.get("tool_input")
    return isinstance(tool_input, dict) and isinstance(tool_input.get("command"), str) and _matches_shell_command(tool_input["command"])


def _scanned_transcript(path: str, scan: Callable[[Iterable[str]], bool]) -> bool | None:
    try:
        with open(path, encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY) as transcript:
            return scan(transcript)
    except OSError:
        return None


def _shows_skill_load(all_transcript_lines: Iterable[str]) -> bool:
    return is_skill_loaded_after_last_compaction(
        all_transcript_lines, (SKILL_NAME,), ALL_SLASH_COMMAND_MARKERS
    )


def _shows_build_eval(all_transcript_lines: Iterable[str]) -> bool:
    return invokes_skill_with_argument(
        all_transcript_lines,
        ALL_BUILD_EVAL_SKILL_NAMES,
        BUILD_EVAL_ARGUMENT_WORD,
        BUILD_EVAL_COMMAND_MARKER,
    )


def _subagent_transcript_path(all_payload_fields: dict[str, object]) -> str | None:
    session_path = all_payload_fields.get(SESSION_TRANSCRIPT_PATH_FIELD)
    agent_id = all_payload_fields.get(AGENT_ID_FIELD)
    if not isinstance(session_path, str) or not session_path:
        return None
    if not isinstance(agent_id, str) or not re.fullmatch(AGENT_ID_PATTERN, agent_id):
        return None
    subagent_path = (
        Path(session_path).with_suffix("")
        / SUBAGENT_TRANSCRIPT_DIRECTORY_NAME
        / SUBAGENT_TRANSCRIPT_FILE_TEMPLATE.format(agent_id=agent_id)
    )
    return str(subagent_path) if subagent_path.is_file() else None


def decision_for(all_payload_fields: dict[str, object]) -> dict[str, object] | None:
    """Return a deny for the first rule a pull request action breaks, else None.

    ::

        pr-lifecycle skill not loaded                     -> DENY_REASON
        new pull request with no proof section            -> MISSING_PROOF_REASON
        new pull request with no existing-work section    -> MISSING_EXISTING_WORK_REASON
        feature pull request with no eval section         -> MISSING_EVAL_SECTION_REASON
        changed page whose proof shows no picture         -> MISSING_LOOK_REASON
        feature pull request, no /claude-api build-eval   -> MISSING_BUILD_EVAL_REASON
        second follow-up pull request for one parent      -> DUPLICATE_FOLLOWUP_REASON_TEMPLATE

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    if not _is_governed_action(all_payload_fields):
        return None
    if _is_skill_unloaded(all_payload_fields):
        return deny_decision(DENY_REASON)
    proof_reason = missing_proof_reason(all_payload_fields)
    if proof_reason is not None:
        return deny_decision(proof_reason)
    search_reason = missing_existing_work_reason(all_payload_fields)
    if search_reason is not None:
        return deny_decision(search_reason)
    eval_reason = missing_eval_section_reason(all_payload_fields)
    if eval_reason is not None:
        return deny_decision(eval_reason)
    look_reason = missing_look_reason(all_payload_fields)
    if look_reason is not None:
        return deny_decision(look_reason)
    if is_feature_pull_request(all_payload_fields) and is_build_eval_missing(all_payload_fields):
        return deny_decision(MISSING_BUILD_EVAL_REASON)
    duplicate_reason = duplicate_followup_reason(all_payload_fields)
    return None if duplicate_reason is None else deny_decision(duplicate_reason)


def transcript_paths(all_payload_fields: dict[str, object]) -> list[str]:
    """Return each transcript path a hook payload names, with the subagent transcript last.

    ::

        transcript_path only                     -> [transcript_path]
        transcript_path and a known agent_id     -> [transcript_path, <session>/subagents/agent-<id>.jsonl]

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    paths = [all_payload_fields.get(field) for field in ALL_TRANSCRIPT_PATH_FIELDS]
    paths.append(_subagent_transcript_path(all_payload_fields))
    return list(dict.fromkeys(path for path in paths if isinstance(path, str) and path))


def _is_skill_unloaded(all_payload_fields: dict[str, object]) -> bool:
    readable_paths = transcript_paths(all_payload_fields)
    if not readable_paths:
        return False
    statuses = [_scanned_transcript(path, _shows_skill_load) for path in readable_paths]
    return not any(status is None or status for status in statuses)


def eval_skill_call_status(all_payload_fields: dict[str, object]) -> bool | None:
    """Return whether the session's transcripts show a /claude-api build-eval call.

    ::

        one transcript shows the call         -> True
        transcripts read, none shows the call -> False
        no transcript could be read           -> None

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    has_read_transcript = False
    for each_path in transcript_paths(all_payload_fields):
        status = _scanned_transcript(each_path, _shows_build_eval)
        if status:
            return True
        has_read_transcript = has_read_transcript or status is not None
    return False if has_read_transcript else None


def is_build_eval_missing(all_payload_fields: dict[str, object]) -> bool:
    """Return whether every readable transcript lacks a /claude-api build-eval call.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    return eval_skill_call_status(all_payload_fields) is False


def deny_decision(reason: str) -> dict[str, object]:
    """Return the PreToolUse output that denies a tool call with this reason.

    Args:
        reason: The text the agent reads as the deny reason.
    """
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            "hookEventName": HOOK_EVENT_NAME,
            PERMISSION_DECISION_KEY: DENY_DECISION,
            PERMISSION_DECISION_REASON_KEY: reason,
        }
    }


def main() -> int:
    """Read one payload, print a deny when needed, and exit zero."""
    return print_decision_from_stdin(decision_for)


if __name__ == "__main__":
    sys.exit(main())
