"""Deny pull request lifecycle actions until their skill appears in the transcript."""

from __future__ import annotations

import json
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
    COMMAND_SEPARATORS,
    COMMAND_WHITESPACE,
    DENY_DECISION,
    DENY_REASON,
    ENVIRONMENT_ASSIGNMENT_PATTERN,
    GH_API_COMMAND,
    GH_OPTIONS_WITH_VALUE,
    GH_PULL_REQUEST_COMMAND,
    GIT_ACTIONS,
    GIT_GLOBAL_OPTIONS_WITH_VALUE,
    HOOK_EVENT_NAME,
    MERGE_PATH_SUFFIX,
    OPTION_AND_VALUE_WORD_COUNT,
    PATH_SEPARATOR_PATTERN,
    PERMISSION_DECISION_REASON_KEY,
    PULL_REQUEST_SCRIPT_NAME,
    PYTHON_OPTIONS_WITH_VALUE,
    SESSION_TRANSCRIPT_PATH_FIELD,
    SHELL_TOOL_NAMES,
    SKILL_NAME,
    SUBAGENT_TRANSCRIPT_DIRECTORY_NAME,
    SUBAGENT_TRANSCRIPT_FILE_TEMPLATE,
)
from hooks_constants.hook_specific_output_keys import (
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
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


def _command_segments(command: str) -> list[list[str]]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=COMMAND_SEPARATORS)
    lexer.whitespace = COMMAND_WHITESPACE
    lexer.whitespace_split = True
    all_segments: list[list[str]] = []
    each_segment: list[str] = []
    try:
        all_words = list(lexer)
    except ValueError:
        return []
    for each_word in all_words:
        if each_word[0] in COMMAND_SEPARATORS:
            all_segments.append(each_segment)
            each_segment = []
            continue
        each_segment.append(each_word)
    if each_segment:
        all_segments.append(each_segment)
    return [each_group for each_group in all_segments if each_group]


def _next_command_word(
    all_words: list[str], start: int, all_options_with_value: frozenset[str]
) -> tuple[str | None, int]:
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
    action, _ = _next_command_word(all_words, 1, GIT_GLOBAL_OPTIONS_WITH_VALUE)
    return action in GIT_ACTIONS


def _is_gh_action(all_words: list[str]) -> bool:
    action, next_index = _next_command_word(all_words, 1, GH_OPTIONS_WITH_VALUE)
    if action == GH_PULL_REQUEST_COMMAND:
        subcommand, _ = _next_command_word(all_words, next_index, GH_OPTIONS_WITH_VALUE)
        return subcommand is not None
    if action != GH_API_COMMAND:
        return False
    all_api_arguments = all_words[next_index:]
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


def _file_name(path_word: str) -> str:
    return re.split(PATH_SEPARATOR_PATTERN, path_word)[-1].lower()


def _runs_pull_request_script(all_words: list[str]) -> bool:
    script, _ = _next_command_word(all_words, 1, PYTHON_OPTIONS_WITH_VALUE)
    return script is not None and _file_name(script) == PULL_REQUEST_SCRIPT_NAME


def _matches_shell_command(command: str) -> bool:
    for each_segment in _command_segments(command):
        all_command_words = _words_from_executable(each_segment)
        if not all_command_words:
            continue
        executable = _file_name(all_command_words[0])
        if executable == PULL_REQUEST_SCRIPT_NAME:
            return True
        if executable in ALL_PYTHON_EXECUTABLES and _runs_pull_request_script(all_command_words):
            return True
        if executable in ALL_SHELL_WRAPPER_EXECUTABLES and any(
            _matches_shell_command(each_argument) for each_argument in all_command_words[1:]
        ):
            return True
        if executable in {"git", "git.exe"} and _is_git_action(all_command_words):
            return True
        if executable in {"gh", "gh.exe"} and _is_gh_action(all_command_words):
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
        return _deny(DENY_REASON)
    proof_reason = missing_proof_reason(all_payload_fields)
    if proof_reason is not None:
        return _deny(proof_reason)
    search_reason = missing_existing_work_reason(all_payload_fields)
    if search_reason is not None:
        return _deny(search_reason)
    eval_reason = missing_eval_section_reason(all_payload_fields)
    if eval_reason is not None:
        return _deny(eval_reason)
    look_reason = missing_look_reason(all_payload_fields)
    if look_reason is not None:
        return _deny(look_reason)
    if is_feature_pull_request(all_payload_fields) and _is_build_eval_missing(all_payload_fields):
        return _deny(MISSING_BUILD_EVAL_REASON)
    duplicate_reason = duplicate_followup_reason(all_payload_fields)
    return None if duplicate_reason is None else _deny(duplicate_reason)


def _transcript_paths(all_payload_fields: dict[str, object]) -> list[str]:
    paths = [all_payload_fields.get(field) for field in ALL_TRANSCRIPT_PATH_FIELDS]
    paths.append(_subagent_transcript_path(all_payload_fields))
    return list(dict.fromkeys(path for path in paths if isinstance(path, str) and path))


def _is_skill_unloaded(all_payload_fields: dict[str, object]) -> bool:
    readable_paths = _transcript_paths(all_payload_fields)
    if not readable_paths:
        return False
    statuses = [_scanned_transcript(path, _shows_skill_load) for path in readable_paths]
    return not any(status is None or status for status in statuses)


def _is_build_eval_missing(all_payload_fields: dict[str, object]) -> bool:
    all_statuses = [
        _scanned_transcript(each_path, _shows_build_eval)
        for each_path in _transcript_paths(all_payload_fields)
    ]
    all_read_statuses = [each_status for each_status in all_statuses if each_status is not None]
    return bool(all_read_statuses) and not any(all_read_statuses)


def _deny(reason: str) -> dict[str, object]:
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            "hookEventName": HOOK_EVENT_NAME,
            PERMISSION_DECISION_KEY: DENY_DECISION,
            PERMISSION_DECISION_REASON_KEY: reason,
        }
    }


def main() -> int:
    """Read one payload, print a deny when needed, and exit zero."""
    payload = read_hook_input_dictionary_from_stdin()
    if payload is not None:
        decision = decision_for(payload)
        if decision is not None:
            sys.stdout.write(json.dumps(decision) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
