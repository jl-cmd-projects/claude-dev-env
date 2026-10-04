"""Deny pull request lifecycle actions until their skill appears in the transcript."""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.pr_lifecycle_skill_gate_constants import (
    ALL_API_ACTION_NAMES,
    ALL_COMMAND_PREFIX_WORDS,
    ALL_GITHUB_MCP_TOOL_SUFFIXES,
    ALL_PREFIX_OPTIONS_WITH_VALUE,
    ALL_PYTHON_EXECUTABLES,
    ALL_SHELL_WRAPPER_EXECUTABLES,
    ALL_SLASH_COMMAND_MARKERS,
    ALL_TRANSCRIPT_PATH_FIELDS,
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
    HOOK_SPECIFIC_OUTPUT_KEY,
    MERGE_PATH_SUFFIX,
    OPTION_AND_VALUE_WORD_COUNT,
    PATH_SEPARATOR_PATTERN,
    PERMISSION_DECISION_KEY,
    PERMISSION_DECISION_REASON_KEY,
    PULL_REQUEST_SCRIPT_NAME,
    PYTHON_OPTIONS_WITH_VALUE,
    SHELL_TOOL_NAMES,
    SKILL_NAME,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING
from transcript_skill_scan import is_skill_loaded_after_last_compaction


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
    if tool_name.endswith(ALL_GITHUB_MCP_TOOL_SUFFIXES):
        return True
    if tool_name not in SHELL_TOOL_NAMES:
        return False
    tool_input = all_payload_fields.get("tool_input")
    return isinstance(tool_input, dict) and isinstance(tool_input.get("command"), str) and _matches_shell_command(tool_input["command"])


def _transcript_load_status(path: str) -> bool | None:
    try:
        with open(path, encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY) as transcript:
            return is_skill_loaded_after_last_compaction(
                transcript, (SKILL_NAME,), ALL_SLASH_COMMAND_MARKERS
            )
    except OSError:
        return None


def decision_for(all_payload_fields: dict[str, object]) -> dict[str, object] | None:
    """Return a deny for a governed action with readable, unloaded transcripts.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    if not _is_governed_action(all_payload_fields):
        return None
    paths = [all_payload_fields.get(field) for field in ALL_TRANSCRIPT_PATH_FIELDS]
    readable_paths = [path for path in paths if isinstance(path, str) and path]
    if not readable_paths:
        return None
    statuses = [_transcript_load_status(path) for path in readable_paths]
    if any(status is None or status for status in statuses):
        return None
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            "hookEventName": HOOK_EVENT_NAME,
            PERMISSION_DECISION_KEY: DENY_DECISION,
            PERMISSION_DECISION_REASON_KEY: DENY_REASON,
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
