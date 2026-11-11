"""Read the author's own words out of a ``git commit`` or a pull request create command.

::

    git commit -m "fix(x): a, b" -m body                 -> subject "fix(x): a, b"
    git commit -F msg.txt                                -> the first line of msg.txt
    gh pr create --title "t" --body-file body.md         -> ("t", the text of body.md)
    python pull_request.py create --title "t" ...        -> ("t", the text of the body file)

A text the command passes on standard input, a missing file, a path that is not
a regular file (a folder, a named pipe, a device such as ``NUL``), and a quote
that never closes give no words. The module opens only a regular file a
``-F``, ``--file``, or ``--body-file`` option names, and reads at most
``MAXIMUM_FILE_BYTES`` bytes of it. It reads no network and starts no process.
"""

from __future__ import annotations

import bisect
import functools
import itertools
import os
import shlex
import stat
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.followup_pr_dedupe_constants import (
    ALL_BODY_FILE_OPTIONS,
    ALL_BODY_OPTIONS,
    ALL_TITLE_OPTIONS,
)
from hooks_constants.pieces_per_level_note_constants import (
    ALL_FILE_LONG_OPTIONS,
    ALL_GH_CREATE_WORDS,
    ALL_MESSAGE_LONG_OPTIONS,
    ALL_SHELL_CONTROL_TOKENS,
    ALL_SUBSTITUTION_MARKERS,
    BACKSLASH,
    CARRIAGE_RETURN,
    CARRIAGE_RETURN_LINE_FEED,
    COMMIT_WORD_PATTERN,
    DOUBLED_BACKSLASH,
    EXECUTABLE_SUFFIX,
    FILE_KIND,
    FILE_SHORT_OPTION,
    GH_PROGRAM_NAME,
    GIT_COMMIT_WORD,
    GIT_PROGRAM_NAME,
    GIT_WORD_PATTERN,
    HEREDOC_MESSAGE_PATTERN,
    HEREDOC_START_PATTERN,
    HEREDOC_TAG_GROUP,
    HEREDOC_TEXT_GROUP,
    LINE_LEADING_WORD_PATTERN,
    LINE_SEPARATOR,
    LONG_OPTION_PREFIX,
    MAXIMUM_FILE_BYTES,
    MAXIMUM_PROGRAM_MENTIONS,
    MAXIMUM_SUBSTITUTION_MARKERS,
    MAXIMUM_WRAPPED_TEXTS,
    PARSE_CACHE_SIZE,
    MESSAGE_KIND,
    MESSAGE_SHORT_FLAG,
    MINIMUM_HEREDOC_BODY_LINE_OFFSET,
    OPTION_VALUE_SEPARATOR,
    SHORT_OPTION_PREFIX,
    STANDARD_INPUT_PATH,
)
from hooks_constants.pull_request_proof_constants import (
    PULL_REQUEST_SCRIPT_CREATE_WORD,
    PULL_REQUEST_SCRIPT_NAME,
)
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING
from hooks_constants.shell_command_segments import git_subcommand_tokens, token_basename
from hooks_constants.shell_command_wrappers import all_wrapped_command_texts


def _tokens_or_none(text: str) -> list[str] | None:
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        return None


def _command_texts(command: str) -> list[str]:
    marker_count = sum(command.count(each_marker) for each_marker in ALL_SUBSTITUTION_MARKERS)
    if marker_count > MAXIMUM_SUBSTITUTION_MARKERS:
        return [command]
    return all_wrapped_command_texts(command, MAXIMUM_WRAPPED_TEXTS)


@functools.lru_cache(maxsize=PARSE_CACHE_SIZE)
def _all_token_lists(command: str) -> tuple[list[str], ...]:
    all_variants = (
        each_variant
        for each_text in _command_texts(command)
        for each_variant in (each_text, each_text.replace(BACKSLASH, DOUBLED_BACKSLASH))
    )
    return tuple(
        all_tokens
        for each_variant in all_variants
        if (all_tokens := _tokens_or_none(each_variant)) is not None
    )


def clear_parse_cache() -> None:
    """Forget the parsed commands, so the next read parses its command again."""
    _all_token_lists.cache_clear()


def _arguments_after(all_tokens: list[str], start_index: int) -> list[str]:
    all_arguments: list[str] = []
    for each_token in all_tokens[start_index:]:
        if each_token in ALL_SHELL_CONTROL_TOKENS:
            break
        all_arguments.append(each_token)
    return all_arguments


def _first_mentions(all_indexes: Iterable[int]) -> Iterator[int]:
    return itertools.islice(all_indexes, MAXIMUM_PROGRAM_MENTIONS)


def _program_indexes(all_tokens: list[str], program_name: str) -> Iterator[int]:
    return _first_mentions(
        each_index
        for each_index, each_token in enumerate(all_tokens)
        if token_basename(each_token).removesuffix(EXECUTABLE_SUFFIX) == program_name
    )


def _script_indexes(all_tokens: list[str]) -> Iterator[int]:
    return _first_mentions(
        each_index
        for each_index, each_token in enumerate(all_tokens)
        if token_basename(each_token) == PULL_REQUEST_SCRIPT_NAME
    )


def _all_commit_arguments(all_tokens: list[str]) -> Iterator[list[str]]:
    for each_index in _program_indexes(all_tokens, GIT_PROGRAM_NAME):
        all_subcommand_tokens = git_subcommand_tokens(_arguments_after(all_tokens, each_index + 1))
        if all_subcommand_tokens[:1] == [GIT_COMMIT_WORD]:
            yield all_subcommand_tokens[1:]


def _all_commit_argument_lists(command: str) -> Iterator[list[str]]:
    return (
        each_arguments
        for each_tokens in _all_token_lists(command)
        for each_arguments in _all_commit_arguments(each_tokens)
    )


def _message_text(message: str) -> str:
    heredoc_match = HEREDOC_MESSAGE_PATTERN.match(message)
    return heredoc_match.group(HEREDOC_TEXT_GROUP) if heredoc_match else message


def _file_text(path_text: str, working_directory: str) -> str | None:
    if path_text == STANDARD_INPUT_PATH:
        return None
    file_path = Path(working_directory) / path_text
    try:
        if not stat.S_ISREG(os.stat(file_path).st_mode):
            return None
        with file_path.open("rb") as file_handle:
            all_file_bytes = file_handle.read(MAXIMUM_FILE_BYTES)
    except (OSError, ValueError):
        return None
    return (
        all_file_bytes.decode(UTF8_ENCODING, errors=DECODE_ERRORS_POLICY)
        .replace(CARRIAGE_RETURN_LINE_FEED, LINE_SEPARATOR)
        .replace(CARRIAGE_RETURN, LINE_SEPARATOR)
    )


def _is_message_flag_cluster(argument: str) -> bool:
    return (
        argument.startswith(SHORT_OPTION_PREFIX)
        and not argument.startswith(LONG_OPTION_PREFIX)
        and argument[1:].isalpha()
        and argument.endswith(MESSAGE_SHORT_FLAG)
    )


def _option_kind(option_name: str) -> str | None:
    if option_name in ALL_MESSAGE_LONG_OPTIONS or _is_message_flag_cluster(option_name):
        return MESSAGE_KIND
    if option_name in ALL_FILE_LONG_OPTIONS or option_name == FILE_SHORT_OPTION:
        return FILE_KIND
    return None


def _option_at(all_arguments: list[str], index: int) -> tuple[str, str] | None:
    option_name, separator, inline_text = all_arguments[index].partition(OPTION_VALUE_SEPARATOR)
    option_kind = _option_kind(option_name)
    if option_kind is None:
        return None
    if separator:
        return option_kind, inline_text
    if index + 1 < len(all_arguments):
        return option_kind, all_arguments[index + 1]
    return None


def _option_message(option_kind: str, option_text: str, working_directory: str) -> str | None:
    if option_kind == MESSAGE_KIND:
        return _message_text(option_text)
    return _file_text(option_text, working_directory)


def _commit_messages(all_arguments: list[str], working_directory: str) -> list[str]:
    all_options = [
        each_option
        for each_index in range(len(all_arguments))
        if (each_option := _option_at(all_arguments, each_index)) is not None
    ]
    all_messages = [
        _option_message(each_kind, each_text, working_directory)
        for each_kind, each_text in all_options
    ]
    return [each_message for each_message in all_messages if each_message is not None]


def _heredoc_start_tag(line: str) -> str | None:
    git_match = GIT_WORD_PATTERN.search(line)
    commit_match = None if git_match is None else COMMIT_WORD_PATTERN.search(line, git_match.end())
    if commit_match is None:
        return None
    start_match = HEREDOC_START_PATTERN.search(line, commit_match.end())
    return None if start_match is None else start_match.group(HEREDOC_TAG_GROUP)


def _line_numbers_by_leading_word(all_lines: list[str]) -> dict[str, list[int]]:
    all_line_numbers: dict[str, list[int]] = {}
    for each_number, each_line in enumerate(all_lines):
        leading_word = LINE_LEADING_WORD_PATTERN.match(each_line)
        if leading_word is not None:
            all_line_numbers.setdefault(leading_word.group(1), []).append(each_number)
    return all_line_numbers


def _all_heredoc_commit_texts(command: str) -> Iterator[str]:
    all_lines = command.split(LINE_SEPARATOR)
    all_line_numbers: dict[str, list[int]] | None = None
    line_number = 0
    while line_number < len(all_lines):
        tag = _heredoc_start_tag(all_lines[line_number])
        if tag is None:
            line_number += 1
            continue
        if all_line_numbers is None:
            all_line_numbers = _line_numbers_by_leading_word(all_lines)
        all_closing_numbers = all_line_numbers.get(tag, [])
        closing_slot = bisect.bisect_left(
            all_closing_numbers, line_number + MINIMUM_HEREDOC_BODY_LINE_OFFSET
        )
        if closing_slot == len(all_closing_numbers):
            line_number += 1
            continue
        closing_number = all_closing_numbers[closing_slot]
        yield LINE_SEPARATOR.join(all_lines[line_number + 1 : closing_number])
        line_number = closing_number + 1


def _first_line(message: str) -> str:
    return next((each_line.strip() for each_line in message.splitlines() if each_line.strip()), "")


def commit_subjects(command: str, working_directory: str) -> list[str]:
    """Return the subject line of each ``git commit`` the command runs.

    The first message of a commit is its subject, so a repeated ``-m`` adds
    body paragraphs. A message in a heredoc inside ``-m "$(cat <<'EOF' ...)"``
    is read even when its text holds a double quote.

    Args:
        command: The shell command text the agent ran.
        working_directory: The folder a relative ``-F`` path resolves against.
    """
    all_subjects = []
    for each_arguments in _all_commit_argument_lists(command):
        all_messages = _commit_messages(each_arguments, working_directory)
        if all_messages:
            all_subjects.append(_first_line(all_messages[0]))
    all_subjects.extend(_first_line(each_text) for each_text in _all_heredoc_commit_texts(command))
    return list(dict.fromkeys(all_subjects))


def _named_option_text(all_arguments: list[str], all_option_names: frozenset[str]) -> str | None:
    for each_index, each_argument in enumerate(all_arguments):
        option_name, separator, inline_text = each_argument.partition(OPTION_VALUE_SEPARATOR)
        if option_name not in all_option_names:
            continue
        if separator:
            return inline_text
        return all_arguments[each_index + 1] if each_index + 1 < len(all_arguments) else None
    return None


def _all_pull_request_arguments(all_tokens: list[str]) -> Iterator[list[str]]:
    for each_index in _program_indexes(all_tokens, GH_PROGRAM_NAME):
        all_arguments = _arguments_after(all_tokens, each_index + 1)
        if all_arguments[: len(ALL_GH_CREATE_WORDS)] == list(ALL_GH_CREATE_WORDS):
            yield all_arguments[len(ALL_GH_CREATE_WORDS) :]
    for each_index in _script_indexes(all_tokens):
        all_arguments = _arguments_after(all_tokens, each_index + 1)
        if all_arguments[:1] == [PULL_REQUEST_SCRIPT_CREATE_WORD]:
            yield all_arguments[1:]


def _pull_request_body(all_arguments: list[str], working_directory: str) -> str | None:
    inline_body = _named_option_text(all_arguments, ALL_BODY_OPTIONS)
    if inline_body is not None:
        return inline_body
    body_path = _named_option_text(all_arguments, ALL_BODY_FILE_OPTIONS)
    return None if body_path is None else _file_text(body_path, working_directory)


def pull_request_words(command: str, working_directory: str) -> list[tuple[str | None, str | None]]:
    """Return the title and body of each pull request create call the command runs.

    Args:
        command: The shell command text the agent ran.
        working_directory: The folder a relative ``--body-file`` path resolves against.

    Returns:
        One ``(title, body)`` pair per call. A part the call does not pass, or
        a body file the hook cannot read, is None.
    """
    all_words = [
        (
            _named_option_text(each_arguments, ALL_TITLE_OPTIONS),
            _pull_request_body(each_arguments, working_directory),
        )
        for each_tokens in _all_token_lists(command)
        for each_arguments in _all_pull_request_arguments(each_tokens)
    ]
    return list(dict.fromkeys(all_words))
