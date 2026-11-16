"""Deny pull request lifecycle actions until their skill appears in the transcript.

A gate silent at its 30 s ``hooks.json`` timeout lets the call through, so its git and GitHub reads
and its transcript scans end by 21 s. ``blocking/gate_run_reads.py`` draws that budget.
A deny from a run that cut a read short says a second run may pass.
Each transcript scan reads the newest line first, so a recent skill load answers early.
A deny from a scan the deadline stopped says to load the skill again.
"""

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
    ALL_API_ACTION_NAMES,
    ALL_COMMAND_PREFIX_WORDS,
    ALL_GH_PULL_REQUEST_READ_SUBCOMMANDS,
    ALL_GH_PULL_REQUEST_SUBCOMMANDS,
    ALL_GITHUB_MCP_TOOL_SUFFIXES,
    ALL_PIECE_REPLACEMENT_TEXTS,
    ALL_PREFIX_OPTIONS_WITH_VALUE,
    ALL_PYTHON_EXECUTABLES,
    ALL_SHELL_WRAPPER_EXECUTABLES,
    ALL_SLASH_COMMAND_MARKERS,
    ALL_TRANSCRIPT_PATH_FIELDS,
    COMMAND_PIECE_PATTERN,
    BACKTICK_SUBSTITUTION_GROUP,
    COMMAND_SUBSTITUTION_PATTERN,
    DOLLAR_SUBSTITUTION_GROUP,
    COMMAND_WHITESPACE,
    DENY_DECISION,
    DENY_REASON,
    DOUBLE_QUOTE,
    DOUBLE_QUOTED_ESCAPE_PATTERN,
    ENVIRONMENT_ASSIGNMENT_PATTERN,
    ESCAPED_CHARACTER_GROUP,
    GATE_NAME,
    GH_API_COMMAND,
    GH_PULL_REQUEST_COMMAND,
    GIT_ACTIONS,
    GIT_GLOBAL_OPTIONS_WITH_VALUE,
    HOOK_EVENT_NAME,
    LINE_CONTINUATION_PIECE,
    LINE_END,
    MERGE_PATH_SUFFIX,
    NO_COMMENT_CHARACTERS,
    OPTION_AND_VALUE_WORD_COUNT,
    PATH_SEPARATOR_PATTERN,
    PERMISSION_DECISION_REASON_KEY,
    PULL_REQUEST_SCRIPT_NAME,
    SCAN_RAN_OUT_SENTENCE,
    ALL_NESTED_PROGRAM_NAMES,
    ALL_NESTED_PROGRAM_WRAPPER_NAMES,
    EVAL_ARGUMENT_SEPARATOR,
    EVAL_PROGRAM_NAME,
    PYTHON_OPTIONS_WITH_VALUE,
    REMOVED_TEXT,
    SEGMENT_BREAK,
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
from blocking.followup_pr_dedupe import all_create_argument_lists, create_tool_fields, duplicate_followup_reason
from blocking.gate_run_reads import (
    GateRun,
    ReadSlice,
    gate_run,
    read_deadlines_started,
    transcript_lines_within_slice,
)
from hooks_constants.gate_fault import gate_fault_reason
from hooks_constants.gate_run_reads_constants import READS_RAN_OUT_SENTENCE
from blocking import pull_request_proof as proof
from transcript_skill_scan import (
    is_skill_loaded_after_last_compaction_newest_first,
)


def _joined_piece_text(piece: re.Match[str]) -> str:
    """Return one command piece with its backslash-newline line continuations removed.

    ::

        \\<newline>          ->  ""
        "gi\\<newline>t"     ->  "git"
        'gi\\<newline>t'     ->  unchanged

    Args:
        piece: One match of ``COMMAND_PIECE_PATTERN`` on the raw command.

    Returns:
        The piece text as bash reads it after joining continuations.
    """
    if piece.lastgroup == LINE_CONTINUATION_PIECE:
        return REMOVED_TEXT
    if piece.group().startswith(DOUBLE_QUOTE):
        return DOUBLE_QUOTED_ESCAPE_PATTERN.sub(_without_line_continuation, piece.group())
    return piece.group()


def _without_line_continuation(escape: re.Match[str]) -> str:
    return REMOVED_TEXT if escape.group(ESCAPED_CHARACTER_GROUP) == LINE_END else escape.group()


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
    all_raw_pieces = list(COMMAND_PIECE_PATTERN.finditer(command))
    if any(each_piece.lastgroup == UNCLOSED_QUOTE_PIECE for each_piece in all_raw_pieces):
        return None
    joined_command = REMOVED_TEXT.join(_joined_piece_text(each_piece) for each_piece in all_raw_pieces)
    all_pieces = list(COMMAND_PIECE_PATTERN.finditer(joined_command))
    marked_command = REMOVED_TEXT.join(
        ALL_PIECE_REPLACEMENT_TEXTS.get(each_piece.lastgroup, each_piece.group()) for each_piece in all_pieces
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
            all_words = each_text.split()
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


def _is_pull_request_action(all_gh_words: list[str]) -> bool:
    all_subcommand_words = all_gh_words[1:]
    if not all_subcommand_words:
        return False
    subcommand, *all_later_words = all_subcommand_words
    if subcommand not in ALL_GH_PULL_REQUEST_READ_SUBCOMMANDS:
        return True
    return any(each_word in ALL_GH_PULL_REQUEST_SUBCOMMANDS for each_word in all_later_words)


def _is_gh_action(all_words: list[str]) -> bool:
    all_gh_words = gh_command_words(all_words[1:])
    if all_gh_words[:1] == [GH_PULL_REQUEST_COMMAND]:
        return _is_pull_request_action(all_gh_words)
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
        if file_name(each_word) not in ALL_COMMAND_PREFIX_WORDS:
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
        all_word_lists.extend(_command_and_nested_word_lists(all_command_words))
    for each_match in COMMAND_SUBSTITUTION_PATTERN.finditer(command):
        inner_command = (
            each_match.group(DOLLAR_SUBSTITUTION_GROUP)
            if each_match.group(DOLLAR_SUBSTITUTION_GROUP) is not None
            else each_match.group(BACKTICK_SUBSTITUTION_GROUP)
        )
        all_word_lists.extend(executable_word_lists(inner_command))
    return all_word_lists


def _command_and_nested_word_lists(all_command_words: list[str]) -> list[list[str]]:
    return [all_command_words, *_wrapped_word_lists(all_command_words), *_nested_program_word_lists(all_command_words)]


def _nested_program_word_lists(all_command_words: list[str]) -> list[list[str]]:
    if file_name(all_command_words[0]) not in ALL_NESTED_PROGRAM_WRAPPER_NAMES:
        return []
    all_word_lists: list[list[str]] = []
    for each_index in range(1, len(all_command_words)):
        if file_name(all_command_words[each_index]) in ALL_NESTED_PROGRAM_NAMES:
            all_word_lists.extend(_command_and_nested_word_lists(all_command_words[each_index:]))
    return all_word_lists


def _wrapped_word_lists(all_command_words: list[str]) -> list[list[str]]:
    if file_name(all_command_words[0]) == EVAL_PROGRAM_NAME:
        return executable_word_lists(EVAL_ARGUMENT_SEPARATOR.join(all_command_words[1:]))
    if file_name(all_command_words[0]) not in ALL_SHELL_WRAPPER_EXECUTABLES:
        return []
    return [
        each_word_list
        for each_argument in all_command_words[1:]
        for each_word_list in executable_word_lists(each_argument)
    ]


def _matches_shell_command(command: str) -> bool:
    if next(all_create_argument_lists(command), None) is not None:
        return True
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


def _scanned_transcript(path: str, scan: Callable[[Iterable[str]], bool], read_slice: ReadSlice) -> bool | None:
    try:
        with open(path, "rb") as transcript:
            return scan(transcript_lines_within_slice(transcript, UTF8_ENCODING, DECODE_ERRORS_POLICY, read_slice))
    except OSError:
        return None


def _shows_skill_load(all_lines_newest_first: Iterable[str]) -> bool:
    return is_skill_loaded_after_last_compaction_newest_first(
        all_lines_newest_first, (SKILL_NAME,), ALL_SLASH_COMMAND_MARKERS
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
        live or checked tier, no proof section            -> MISSING_PROOF_REASON or MISSING_CHECKED_PROOF_REASON, + tier
        proof, or a body edit, says not run               -> UNPROVEN_PROOF_REASON
        proof, or a body edit, holds a merge word         -> DEFERRED_PROOF_REASON
        body edit whose proof has no command              -> MISSING_PROOF_REASON or MISSING_CHECKED_PROOF_REASON, + tier
        live tier, proof or body edit runs only tests     -> TEST_ONLY_PROOF_REASON + tier
        new pull request with no existing-work section    -> MISSING_EXISTING_WORK_REASON
        pull request with no flowchart in What this does  -> MISSING_FLOWCHART_REASON
        feature changing an agent surface, no eval section -> MISSING_EVAL_SECTION_REASON + why
        changed page whose proof shows no picture         -> MISSING_LOOK_REASON
        second follow-up pull request for one parent      -> DUPLICATE_FOLLOWUP_REASON_TEMPLATE
        follow-up read of open pull requests unanswered   -> UNANSWERED_FOLLOWUP_REASON_TEMPLATE
        follow-up with no repository, origin unread       -> UNREAD_ORIGIN_FOLLOWUP_REASON_TEMPLATE
        skill deny from a scan the deadline stopped       -> that reason + SCAN_RAN_OUT_SENTENCE
        any deny above in a run whose deadline cut a read -> that reason + READS_RAN_OUT_SENTENCE
        a check raises once the call is known governed   -> gate_fault_reason naming the error

    The checks share one gate run, so two checks that ask git or GitHub one question read it once.
    A fault while the gate decides whether the call is governed still raises, so it never refuses an unrelated call.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    if not _is_governed_action(all_payload_fields):
        return None
    with gate_run() as run:
        try:
            reason = _first_broken_rule_reason(all_payload_fields, run)
        except Exception as error:
            return deny_decision(gate_fault_reason(GATE_NAME, error))
    note = READS_RAN_OUT_SENTENCE if run.was_read_cut_short else ""
    return None if reason is None else deny_decision(reason + note)


def _scan_note(run: GateRun, cut_scan_count_before: int) -> str:
    return SCAN_RAN_OUT_SENTENCE if run.cut_scan_count > cut_scan_count_before else ""


def _first_broken_rule_reason(all_fields: dict[str, object], run: GateRun) -> str | None:
    cut_scan_count_before = run.cut_scan_count
    if _is_skill_unloaded(all_fields):
        return DENY_REASON + _scan_note(run, cut_scan_count_before)
    return (
        proof.missing_proof_reason(all_fields)
        or proof.edit_proof_reason(all_fields)
        or proof.missing_existing_work_reason(all_fields)
        or proof.missing_flowchart_reason(all_fields)
        or proof.missing_eval_section_reason(all_fields)
        or proof.missing_look_reason(all_fields)
        or duplicate_followup_reason(all_fields)
    )


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
    statuses = [_scanned_transcript(path, _shows_skill_load, ReadSlice.PROOF_AND_LOOK) for path in readable_paths]
    return not any(status is None or status for status in statuses)


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
    """Start the read deadlines, read one payload, print a deny when needed, and exit zero."""
    with read_deadlines_started():
        return print_decision_from_stdin(decision_for)


if __name__ == "__main__":
    sys.exit(main())
