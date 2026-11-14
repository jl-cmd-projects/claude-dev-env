"""Walk a shell command in order and give each pull request create the folder it runs in.

::

    cd ../a && gh pr create --head x           -> ["--head", "x"] in ../a
    (cd ../a && gh pr create) ; gh pr create   -> one in ../a, one in the starting folder
    pushd ../a && popd && gh pr create         -> the starting folder
    cd "$WORK" && gh pr create                 -> folder not followed
    { cd ../a; } | true; gh pr create          -> folder not followed

The walk follows ``cd``, ``chdir``, ``Set-Location``, ``pushd`` and ``popd``,
also after ``builtin`` or ``command``, and the end of a subshell. A folder
change in a background job stays in that job. ``bash -c`` and substitutions
run as child shells, while ``eval`` changes the folder of the shell that runs
it. A folder change the walk does not model leaves each later create in that
scope unfollowed: one in a pipeline member, a brace group, ``if``, ``case``,
a loop or a function body, one after a redirect, or a folder word anywhere
but the program place. So does a folder it cannot name, such as one a
variable holds. ``quoted_lines.quote_aware_lines`` cuts each text into the
lines bash reads, and ``followup_pr_dedupe.create_arguments`` decides what
counts as a create. Shell variables, aliases and functions that hold a program
name are not followed. Text nested past ``MAXIMUM_UNWRAP_DEPTH`` that names
``gh`` and a create word, or ``pull_request.py``, gives one create with no
options, unfollowed.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.followup_pr_dedupe import create_arguments
from blocking.merge_review_gate_parts.folder_state import FolderState, state_after_folder_change
from blocking.merge_review_gate_parts.quoted_lines import quote_aware_lines
from blocking.merge_review_gate_parts.wrapped_creates import unplaced_creates
from hooks_constants.merge_review_gate_constants import (
    ALL_BACKGROUND_OPERATORS,
    ALL_CLOSING_CHARACTERS,
    ALL_COMMAND_PREFIX_WORDS,
    ALL_COMPOUND_BODY_WORDS,
    ALL_COMPOUND_CLOSE_WORDS,
    ALL_COMPOUND_OPEN_WORDS,
    ALL_FOLDER_CHANGE_WORDS,
    ALL_PIPE_OPERATORS,
    ALL_UNBALANCED_TOKENIZATION_MODES,
    BRACE_CLOSE_TOKEN,
    BRACE_OPEN_OPERATOR,
    END_OF_OPTIONS_PREFIX,
    IS_POSIX_TOKENIZATION,
    LOOSE_GH_PROGRAM_PATTERN,
    LOOSE_OPEN_WORD_PATTERN,
    LOOSE_PULL_REQUEST_SCRIPT_PATTERN,
    SEGMENT_TOKEN_JOIN,
    SUBSHELL_CLOSE_TOKEN,
    SUBSHELL_OPEN_OPERATOR,
    SUBSTITUTION_KEY_IGNORED_PATTERN,
)
from hooks_constants.pytest_invocation import string_exec_inner_command, unquoted_token
from hooks_constants.shell_command_evaluation_constants import (
    ALL_STRING_EVALUATING_PROGRAM_NAMES,
    MAXIMUM_UNWRAP_DEPTH,
)
from hooks_constants.shell_command_pipeline import (
    join_line_continuations,
    operator_aware_tokens,
    scannable_command_lines,
    segments_with_following_operator,
)
from hooks_constants.shell_command_wrappers import (
    all_command_substitution_texts,
    evaluated_inner_command,
    quoted_line_breaks_joined,
    segment_program_and_arguments,
)


@dataclass(frozen=True)
class PlacedCreate:
    """One create in a shell command and the folder it runs in.

    Attributes:
        all_arguments: The create's options, as ``create_arguments`` gives them.
        folder: The folder in effect at the create, or None for the gate's own.
        is_folder_followed: False when a folder change before it could not be followed.
        all_command_words: The words of the simple command that runs it, in the order bash
            passes them, or empty when the create was read without them.
    """

    all_arguments: tuple[str, ...]
    folder: str | None
    is_folder_followed: bool
    all_command_words: tuple[str, ...] = field(default=(), compare=False)


@dataclass
class _Walk:
    all_creates: list[PlacedCreate]


@dataclass
class _Scope:
    state: FolderState
    is_posix: bool = IS_POSIX_TOKENIZATION
    previous_operator: str = ""
    brace_depth: int = 0
    compound_depth: int = 0
    all_saved: list[FolderState] = field(default_factory=list)
    all_live_substitution_keys: frozenset[str] = frozenset()


def all_placed_creates(command: str, folder: str | None) -> list[PlacedCreate]:
    """Return each create in a shell command with the folder it runs in, in command order.

    ::

        "cd sub && gh pr create --fill", "/w"   -> [PlacedCreate(("--fill",), "/w/sub", True)]
        "cd $X && gh pr create --fill", "/w"    -> [PlacedCreate(("--fill",), None, False)]

    Each text is cut into lines and words as bash reads its quotes, so a line
    break inside ``bash -c "..."`` or ``eval '...'`` starts a command while one
    inside ``--body "..."`` does not. ``eval`` runs its words joined by spaces,
    and the words after a ``)`` in a segment, such as a ``case`` arm's command,
    are read for a wrapper too. A text whose quotes do not close is read as
    written and with its quoted line breaks joined, each in POSIX and raw
    words. ``wrapped_creates.unplaced_creates`` gives each create the
    walk did not place, and it comes back unfollowed.

    Args:
        command: The shell command text.
        folder: The folder the command starts in, or None for the gate's own.
    """
    start = FolderState(folder, True)
    all_creates: list[PlacedCreate] = []
    _walk_text(_Walk(all_creates), command, start, 0)
    all_placed_arguments = [each_create.all_arguments for each_create in all_creates]
    all_creates.extend(
        PlacedCreate(each_arguments, None, False, each_words)
        for each_arguments, each_words in unplaced_creates(command, all_placed_arguments)
    )
    return list(dict.fromkeys(all_creates))


def _walk_text(walk: _Walk, text: str, state: FolderState, depth: int) -> FolderState:
    if depth > MAXIMUM_UNWRAP_DEPTH:
        if _may_hold_create(text):
            walk.all_creates.append(PlacedCreate((), None, False))
        return state
    all_token_lines = _posix_token_lines(text)
    if all_token_lines is None:
        return _walk_unbalanced_text(walk, text, state, depth)
    scope = _Scope(state, all_live_substitution_keys=_substitution_keys(text))
    return _walk_token_lines(walk, all_token_lines, scope, depth)


def _may_hold_create(text: str) -> bool:
    is_gh_create = LOOSE_GH_PROGRAM_PATTERN.search(text) and LOOSE_OPEN_WORD_PATTERN.search(text)
    return bool(is_gh_create or LOOSE_PULL_REQUEST_SCRIPT_PATTERN.search(text))


def _posix_token_lines(text: str) -> list[list[str]] | None:
    all_lines = quote_aware_lines(text)
    if all_lines is None:
        return None
    all_token_lines = [
        each_tokens
        for each_line in all_lines
        if (each_tokens := operator_aware_tokens(each_line, IS_POSIX_TOKENIZATION)) is not None
    ]
    return all_token_lines if len(all_token_lines) == len(all_lines) else None


def _walk_unbalanced_text(
    walk: _Walk, text: str, state: FolderState, depth: int
) -> FolderState:
    all_end_states: set[FolderState] = set()
    for each_text in dict.fromkeys([text, quoted_line_breaks_joined(text)]):
        for each_is_posix in ALL_UNBALANCED_TOKENIZATION_MODES:
            all_token_lines = _line_tokens(each_text, each_is_posix)
            scope = _Scope(state, each_is_posix, all_live_substitution_keys=_substitution_keys(each_text))
            all_end_states.add(_walk_token_lines(walk, all_token_lines, scope, depth))
    return state if all_end_states == {state} else FolderState(None, False)


def _line_tokens(text: str, is_posix: bool) -> list[list[str]]:
    return [
        operator_aware_tokens(each_line, is_posix) or []
        for each_line in scannable_command_lines(join_line_continuations(text))
    ]


def _walk_token_lines(
    walk: _Walk, all_token_lines: list[list[str]], scope: _Scope, depth: int
) -> FolderState:
    for each_tokens in all_token_lines:
        for each_segment, each_operator in segments_with_following_operator(each_tokens):
            _walk_step(walk, scope, each_segment, each_operator, depth)
    return scope.state


def _walk_step(
    walk: _Walk, scope: _Scope, all_segment_tokens: list[str], operator: str, depth: int
) -> None:
    _walk_segment(walk, scope, all_segment_tokens, operator, depth)
    _restore_closed_subshells(scope, _closing_count(all_segment_tokens))
    if operator == SUBSHELL_OPEN_OPERATOR:
        scope.all_saved.append(scope.state)
    scope.brace_depth += operator == BRACE_OPEN_OPERATOR
    scope.previous_operator = operator


def _restore_closed_subshells(scope: _Scope, closing_count: int) -> None:
    if closing_count == 0 or not scope.all_saved:
        return
    kept_count = max(0, len(scope.all_saved) - closing_count)
    scope.state = scope.all_saved[kept_count]
    del scope.all_saved[kept_count:]


def _walk_segment(
    walk: _Walk, scope: _Scope, all_segment_tokens: list[str], operator: str, depth: int
) -> None:
    all_tokens = _without_closing_tokens(all_segment_tokens)
    while all_tokens[:1] == [BRACE_CLOSE_TOKEN]:
        all_tokens = all_tokens[1:]
        scope.brace_depth = max(0, scope.brace_depth - 1)
    first_word = unquoted_token(all_tokens[0]).lower() if all_tokens else ""
    scope.compound_depth += first_word in ALL_COMPOUND_OPEN_WORDS
    is_piped = scope.previous_operator in ALL_PIPE_OPERATORS or operator in ALL_PIPE_OPERATORS
    is_modeled = (
        not is_piped
        and scope.brace_depth == 0
        and scope.compound_depth == 0
        and first_word not in ALL_COMPOUND_BODY_WORDS
    )
    next_state = _segment_step(walk, scope, all_tokens, depth, is_modeled)
    if operator not in ALL_BACKGROUND_OPERATORS:
        scope.state = next_state
    if first_word in ALL_COMPOUND_CLOSE_WORDS:
        scope.compound_depth = max(0, scope.compound_depth - 1)


def _closing_count(all_segment_tokens: list[str]) -> int:
    all_closing_tokens = all_segment_tokens[len(_without_closing_tokens(all_segment_tokens)) :]
    return sum(each_token.count(SUBSHELL_CLOSE_TOKEN) for each_token in all_closing_tokens)


def _without_closing_tokens(all_segment_tokens: list[str]) -> list[str]:
    all_tokens = list(all_segment_tokens)
    while all_tokens and SUBSHELL_CLOSE_TOKEN in all_tokens[-1] and not all_tokens[-1].strip(ALL_CLOSING_CHARACTERS):
        all_tokens.pop()
    return all_tokens


def _segment_step(
    walk: _Walk, scope: _Scope, all_tokens: list[str], depth: int, is_modeled: bool
) -> FolderState:
    state = scope.state
    all_readings = _wrapper_readings(all_tokens)
    for each_reading in all_readings:
        all_arguments = create_arguments(each_reading)
        if all_arguments is not None:
            walk.all_creates.append(PlacedCreate(tuple(all_arguments), state.folder, state.is_followed, tuple(each_reading)))
            break
    for each_child_text in dict.fromkeys(
        each_text for each_reading in all_readings for each_text in _child_shell_texts(each_reading, scope)
    ):
        _walk_text(walk, each_child_text, state, depth + 1)
    next_state = _state_after_evaluation(walk, scope, all_readings, depth)
    next_state = state_after_folder_change(_without_command_prefixes(all_tokens), next_state)
    if (next_state != state and not is_modeled) or _has_unmodeled_folder_word(all_tokens):
        return FolderState(None, False)
    return next_state


def _state_after_evaluation(
    walk: _Walk, scope: _Scope, all_readings: list[list[str]], depth: int
) -> FolderState:
    for each_reading in all_readings:
        evaluated_text = _evaluated_text(each_reading, scope.is_posix)
        if evaluated_text is None:
            continue
        evaluated_state = _walk_text(walk, evaluated_text, scope.state, depth + 1)
        is_same_shell = (
            segment_program_and_arguments(each_reading)[0] in ALL_STRING_EVALUATING_PROGRAM_NAMES
        )
        return evaluated_state if is_same_shell else scope.state
    return scope.state


def _wrapper_readings(all_tokens: list[str]) -> list[list[str]]:
    if SUBSHELL_CLOSE_TOKEN not in all_tokens:
        return [all_tokens]
    last_close_index = len(all_tokens) - 1 - all_tokens[::-1].index(SUBSHELL_CLOSE_TOKEN)
    all_after_pattern = all_tokens[last_close_index + 1 :]
    return [all_tokens, all_after_pattern] if all_after_pattern else [all_tokens]


def _evaluated_text(all_tokens: list[str], is_posix: bool) -> str | None:
    program, all_arguments = segment_program_and_arguments(all_tokens)
    if is_posix and program.lower() in ALL_STRING_EVALUATING_PROGRAM_NAMES:
        return SEGMENT_TOKEN_JOIN.join(all_arguments)
    return evaluated_inner_command(all_tokens)


def _without_command_prefixes(all_tokens: list[str]) -> list[str]:
    all_remaining = list(all_tokens)
    while (
        len(all_remaining) > 1
        and unquoted_token(all_remaining[0]).lower() in ALL_COMMAND_PREFIX_WORDS
    ):
        all_remaining = all_remaining[1:]
    return all_remaining


def _has_unmodeled_folder_word(all_tokens: list[str]) -> bool:
    all_command_tokens = _without_command_prefixes(all_tokens)
    program = segment_program_and_arguments(all_command_tokens)[0]
    if program in ALL_FOLDER_CHANGE_WORDS:
        return False
    return any(each_token.lower() in ALL_FOLDER_CHANGE_WORDS for each_token in all_command_tokens)


def _child_shell_texts(all_tokens: list[str], scope: _Scope) -> list[str]:
    string_exec_text = string_exec_inner_command(all_tokens)
    if string_exec_text is not None:
        string_exec_text = string_exec_text.removeprefix(END_OF_OPTIONS_PREFIX)
    all_substitution_texts = [
        each_text
        for each_text in all_command_substitution_texts(SEGMENT_TOKEN_JOIN.join(all_tokens))
        if _substitution_key(each_text) in scope.all_live_substitution_keys
    ]
    return [*([string_exec_text] if string_exec_text is not None else []), *all_substitution_texts]


def _substitution_keys(text: str) -> frozenset[str]:
    return frozenset(_substitution_key(each_text) for each_text in all_command_substitution_texts(text))


def _substitution_key(text: str) -> str:
    return SUBSTITUTION_KEY_IGNORED_PATTERN.sub("", text)

