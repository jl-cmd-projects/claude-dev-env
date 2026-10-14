"""Step over the wrappers in front of a shell command to reach the command it runs.

A wrapper either runs its own operands, as ``sudo``, ``xargs``, ``env``, and
``timeout`` do, or runs a command string, as ``bash -c``, ``sh -lc``, and
``pwsh -Command`` do::

    sudo git push                         git, ["push"]
    env GIT_DIR=x git push                git, ["push"]
    echo origin | xargs git push          git, ["push"]
    bash -lc "git commit -F m.txt"        "git commit -F m.txt" unwraps in turn
    echo "$(git push)"                    "git push" unwraps in turn

``pytest_invocation`` owns the wrapper and string-exec parsing, and this module
composes it into the answers a hook asks about any program.
"""

from __future__ import annotations

import base64
import collections
import itertools

from hooks_constants.piped_pytest_blocker_constants import (
    WINDOWS_EXECUTABLE_SUFFIX,
    WRAPPED_COMMAND_TOKEN_JOIN,
)
from hooks_constants.pytest_invocation import (
    all_tokens_after_wrappers,
    string_exec_inner_command,
    unquoted_token,
)
from hooks_constants.shell_command_evaluation_constants import (
    ALL_FIND_EXEC_ACTIONS,
    ALL_FIND_EXEC_TERMINATORS,
    ALL_POWERSHELL_PROGRAM_NAMES,
    ALL_START_PROCESS_NON_COMMAND_PARAMETERS,
    ALL_START_PROCESS_PROGRAM_NAMES,
    ALL_STRING_EVALUATING_PROGRAM_NAMES,
    ENCODED_COMMAND_OPTION,
    ENCODED_COMMAND_SHORT_ALIAS,
    ENCODED_COMMAND_TEXT_ENCODING,
    FIND_EXEC_COMMAND_SEPARATOR,
    FIND_PROGRAM_NAME,
    ALL_LINE_BREAK_CHARACTERS,
    MAXIMUM_UNWRAP_DEPTH,
    MINIMUM_ENCODED_COMMAND_PREFIX_LENGTH,
    QUOTED_LINE_BREAK_REPLACEMENT,
    START_PROCESS_ARGUMENT_SEPARATOR,
    START_PROCESS_PARAMETER_PREFIX,
    START_PROCESS_PARAMETER_VALUE_SEPARATOR,
)
from hooks_constants.shell_command_pipeline import pipeline_segments_for_command
from hooks_constants.shell_command_substitution_constants import (
    ALL_BACKTICK_ESCAPED_CHARACTERS,
    ALL_PARENTHESIS_DEPTH_CHANGES,
    BACKTICK,
    COMMAND_SUBSTITUTION_OPENER,
    DOUBLE_QUOTE,
    SHELL_ESCAPE_CHARACTER,
    SINGLE_QUOTE,
)
from hooks_constants.shell_command_segments import (
    effective_leading_program,
    token_basename,
)

__all__ = [
    "segment_program_and_arguments",
    "all_wrapped_command_texts",
    "all_wrapped_command_segments",
    "all_command_substitution_texts",
    "evaluated_inner_command",
]


def segment_program_and_arguments(all_segment_tokens: list[str]) -> tuple[str, list[str]]:
    """Return a segment's program basename past its wrappers and the tokens after it.

    The basename drops a ``.exe`` suffix, so ``git.exe push`` reads as ``git``.
    Returns an empty pair when the segment names no program.
    """
    all_unwrapped_tokens = all_tokens_after_wrappers(all_segment_tokens)
    program_token = effective_leading_program(all_unwrapped_tokens)
    if program_token is None:
        return "", []
    program_index = all_unwrapped_tokens.index(program_token)
    program_name = token_basename(unquoted_token(program_token)).removesuffix(
        WINDOWS_EXECUTABLE_SUFFIX
    )
    return program_name, all_unwrapped_tokens[program_index + 1 :]


def _quote_state_after(
    character: str, is_in_single_quotes: bool, is_in_double_quotes: bool
) -> tuple[bool, bool]:
    """Return the single and double quote state after one character."""
    if is_in_single_quotes:
        return character != SINGLE_QUOTE, False
    if character == SINGLE_QUOTE and not is_in_double_quotes:
        return True, False
    if character == DOUBLE_QUOTE:
        return False, not is_in_double_quotes
    return False, is_in_double_quotes


def _closing_parenthesis_index(command: str, body_start_index: int) -> int:
    """Return the index of the unquoted parenthesis that closes a substitution.

    Returns the command length when no parenthesis closes it.
    """
    depth = 1
    is_in_single_quotes = False
    is_in_double_quotes = False
    character_index = body_start_index
    while character_index < len(command):
        character = command[character_index]
        if character == SHELL_ESCAPE_CHARACTER and not is_in_single_quotes:
            character_index += 2
            continue
        if not (is_in_single_quotes or is_in_double_quotes):
            depth += ALL_PARENTHESIS_DEPTH_CHANGES.get(character, 0)
        if depth == 0:
            return character_index
        is_in_single_quotes, is_in_double_quotes = _quote_state_after(
            character, is_in_single_quotes, is_in_double_quotes
        )
        character_index += 1
    return len(command)


def _backtick_body(command: str, body_start_index: int) -> tuple[str, int]:
    """Return a backtick substitution's body with its escapes removed, and its closing index."""
    all_body_characters: list[str] = []
    character_index = body_start_index
    while character_index < len(command) and command[character_index] != BACKTICK:
        character = command[character_index]
        next_character = command[character_index + 1 : character_index + 2]
        if (
            character == SHELL_ESCAPE_CHARACTER
            and next_character in ALL_BACKTICK_ESCAPED_CHARACTERS
        ):
            all_body_characters.append(next_character)
            character_index += 2
            continue
        all_body_characters.append(character)
        character_index += 1
    return "".join(all_body_characters), character_index


def _substitution_at(command: str, character_index: int) -> tuple[str, int] | None:
    """Return the body and closing index of a substitution that opens at the index, else None."""
    if command.startswith(COMMAND_SUBSTITUTION_OPENER, character_index):
        body_start_index = character_index + len(COMMAND_SUBSTITUTION_OPENER)
        body_end_index = _closing_parenthesis_index(command, body_start_index)
        return command[body_start_index:body_end_index], body_end_index
    if command[character_index] != BACKTICK:
        return None
    return _backtick_body(command, character_index + 1)


def all_command_substitution_texts(command: str) -> list[str]:
    """Return the command text inside each ``$(...)`` and backtick pair outside single quotes.

    ::

        echo "$(gh pr list)"        ["gh pr list"]
        x=`git push`                ["git push"]
        echo '$(gh pr list)'        []
    """
    all_substitution_texts: list[str] = []
    is_in_single_quotes = False
    is_in_double_quotes = False
    character_index = 0
    while character_index < len(command):
        substitution = None if is_in_single_quotes else _substitution_at(command, character_index)
        if substitution is not None:
            all_substitution_texts.append(substitution[0])
            character_index = substitution[1] + 1
            continue
        if not is_in_single_quotes and command[character_index] == SHELL_ESCAPE_CHARACTER:
            character_index += 2
            continue
        is_in_single_quotes, is_in_double_quotes = _quote_state_after(
            command[character_index], is_in_single_quotes, is_in_double_quotes
        )
        character_index += 1
    return all_substitution_texts


def _find_exec_command(all_arguments: list[str]) -> str | None:
    """Return the commands every ``find -exec`` action runs as one command list, else None."""
    all_action_indexes = [
        each_index
        for each_index, each_argument in enumerate(all_arguments)
        if unquoted_token(each_argument) in ALL_FIND_EXEC_ACTIONS
    ]
    if not all_action_indexes:
        return None
    return FIND_EXEC_COMMAND_SEPARATOR.join(
        WRAPPED_COMMAND_TOKEN_JOIN.join(
            itertools.takewhile(
                lambda each_token: unquoted_token(each_token) not in ALL_FIND_EXEC_TERMINATORS,
                all_arguments[each_action_index + 1 :],
            )
        )
        for each_action_index in all_action_indexes
    )


def _is_encoded_command_option(argument: str) -> bool:
    lowered_argument = unquoted_token(argument).lower()
    return lowered_argument == ENCODED_COMMAND_SHORT_ALIAS or (
        len(lowered_argument) >= MINIMUM_ENCODED_COMMAND_PREFIX_LENGTH
        and ENCODED_COMMAND_OPTION.startswith(lowered_argument)
    )


def _decoded_utf16_base64_text(encoded_text: str) -> str | None:
    """Return the UTF-16LE text a base64 string holds, else None."""
    try:
        return base64.b64decode("".join(encoded_text.split()), validate=True).decode(
            ENCODED_COMMAND_TEXT_ENCODING
        )
    except ValueError:
        return None


def _decoded_powershell_command(all_arguments: list[str]) -> str | None:
    """Return the text a PowerShell ``-EncodedCommand`` value decodes to, else None."""
    for each_previous_argument, each_argument in itertools.pairwise(all_arguments):
        if _is_encoded_command_option(each_previous_argument):
            return _decoded_utf16_base64_text(unquoted_token(each_argument))
    return None


def _start_process_tokens(all_arguments: list[str]) -> list[str]:
    """Return the ``Start-Process`` arguments with each ``-Name:value`` split in two."""
    all_tokens: list[str] = []
    for each_argument in all_arguments:
        is_bound_parameter = each_argument.startswith(START_PROCESS_PARAMETER_PREFIX)
        if is_bound_parameter and START_PROCESS_PARAMETER_VALUE_SEPARATOR in each_argument:
            all_tokens.extend(each_argument.split(START_PROCESS_PARAMETER_VALUE_SEPARATOR, 1))
            continue
        all_tokens.append(each_argument)
    return all_tokens


def _start_process_command(all_arguments: list[str]) -> str | None:
    """Return the program and arguments a ``Start-Process`` call runs, else None."""
    all_start_process_tokens = _start_process_tokens(all_arguments)
    all_command_words = [
        unquoted_token(each_argument).replace(
            START_PROCESS_ARGUMENT_SEPARATOR, WRAPPED_COMMAND_TOKEN_JOIN
        )
        for each_previous_argument, each_argument in itertools.pairwise(
            ["", *all_start_process_tokens]
        )
        if not each_argument.startswith(START_PROCESS_PARAMETER_PREFIX)
        and each_previous_argument.lower() not in ALL_START_PROCESS_NON_COMMAND_PARAMETERS
    ]
    return WRAPPED_COMMAND_TOKEN_JOIN.join(all_command_words) or None


def evaluated_inner_command(all_segment_tokens: list[str]) -> str | None:
    """Return the command that an evaluating program in the segment runs, else None.

    ::

        eval "gh pr list"                      gh pr list
        iex 'gh pr list'                       gh pr list
        find . -exec gh pr list +              gh pr list
        pwsh -EncodedCommand ZwBoACAA...       the decoded text
        Start-Process gh -ArgumentList 'pr list'   gh pr list
        gh pr list                             None

    The pipeline parser splits a ``find`` call at an escaped ``\\;``, so a
    segment that starts with a ``-exec`` action is the rest of that call.
    """
    if all_segment_tokens and unquoted_token(all_segment_tokens[0]) in ALL_FIND_EXEC_ACTIONS:
        return _find_exec_command(all_segment_tokens)
    program_name, all_arguments = segment_program_and_arguments(all_segment_tokens)
    normalized_program_name = program_name.lower()
    if normalized_program_name in ALL_STRING_EVALUATING_PROGRAM_NAMES:
        return WRAPPED_COMMAND_TOKEN_JOIN.join(
            unquoted_token(each_argument) for each_argument in all_arguments
        )
    if normalized_program_name == FIND_PROGRAM_NAME:
        return _find_exec_command(all_arguments)
    if normalized_program_name in ALL_POWERSHELL_PROGRAM_NAMES:
        return _decoded_powershell_command(all_arguments)
    if normalized_program_name in ALL_START_PROCESS_PROGRAM_NAMES:
        return _start_process_command(all_arguments)
    return None


def _quoted_line_breaks_joined(command: str) -> str:
    """Return a copy of the command that holds a space at each quoted line break.

    The pipeline parser splits a command at every line break, so a quoted
    value that spans lines, such as an encoded PowerShell command, reads whole
    only in this copy.
    """
    all_characters: list[str] = []
    is_in_single_quotes = False
    is_in_double_quotes = False
    for each_character in command:
        is_quoted = is_in_single_quotes or is_in_double_quotes
        is_quoted_line_break = is_quoted and each_character in ALL_LINE_BREAK_CHARACTERS
        all_characters.append(
            QUOTED_LINE_BREAK_REPLACEMENT if is_quoted_line_break else each_character
        )
        is_in_single_quotes, is_in_double_quotes = _quote_state_after(
            each_character, is_in_single_quotes, is_in_double_quotes
        )
    return "".join(all_characters)


def _inner_commands(command: str, all_command_segments: list[list[str]]) -> list[str]:
    """Return each command string that a wrapper, evaluating program or substitution runs.

    A copy of the command with its quoted line breaks joined comes last when it differs.
    """
    joined_command = _quoted_line_breaks_joined(command)
    all_inner_commands = [
        joined_command if joined_command != command else None,
        *(string_exec_inner_command(each_segment) for each_segment in all_command_segments),
        *(evaluated_inner_command(each_segment) for each_segment in all_command_segments),
        *all_command_substitution_texts(command),
    ]
    return [each_command for each_command in all_inner_commands if each_command is not None]


def _all_wrapped_command_parses(command: str) -> list[tuple[str, list[list[str]]]]:
    """Return each command text with its segments, the command first, each text parsed once.

    The texts after the command are the command string every shell wrapper,
    evaluating program and command substitution inside it runs, unwrapped in
    turn to ``MAXIMUM_UNWRAP_DEPTH`` levels. A text met twice is parsed once.
    """
    all_parses: list[tuple[str, list[list[str]]]] = []
    all_seen_texts: set[str] = set()
    all_pending_texts = collections.deque([(command, 0)])
    while all_pending_texts:
        each_text, each_depth = all_pending_texts.popleft()
        if each_text in all_seen_texts or each_depth > MAXIMUM_UNWRAP_DEPTH:
            continue
        all_seen_texts.add(each_text)
        all_command_segments = [
            each_segment
            for each_segment, _following_operator in pipeline_segments_for_command(each_text)
        ]
        all_parses.append((each_text, all_command_segments))
        all_pending_texts.extend(
            (each_inner_command, each_depth + 1)
            for each_inner_command in _inner_commands(each_text, all_command_segments)
        )
    return all_parses


def all_wrapped_command_texts(command: str) -> list[str]:
    """Return the command plus each command string a wrapper or substitution inside it runs.

    The segments come from the quote-aware pipeline parser, so the quoted
    script in ``powershell -Command "git add -A; git push"`` stays whole until
    its own turn. Nested wrappers and ``$(...)`` or backtick substitutions
    unwrap in turn.
    """
    return [each_text for each_text, _all_segments in _all_wrapped_command_parses(command)]


def all_wrapped_command_segments(command: str) -> list[list[str]]:
    """Return every segment of the command and of each command string a wrapper inside it runs.

    Each command text goes through the pipeline parser once, and both this
    function and ``all_wrapped_command_texts`` read that one parse, so a hook
    that grades segments reads ``bash -c "gh pr list"`` as its outer segment
    plus ``gh pr list``.
    """
    return [
        each_segment
        for _each_text, all_segments in _all_wrapped_command_parses(command)
        for each_segment in all_segments
    ]
