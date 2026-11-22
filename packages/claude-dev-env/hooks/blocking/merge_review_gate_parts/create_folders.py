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
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.followup_pr_dedupe import create_arguments
from blocking.merge_review_gate_parts.create_options import text_value_indexes
from blocking.merge_review_gate_parts.folder_state import FolderState, state_after_folder_change
from blocking.merge_review_gate_parts.quoted_lines import (
    expansion_marked_line,
    holds_unquoted_expansion,
    quote_aware_lines,
)
from blocking.merge_review_gate_parts.settled_steps import (
    holds_expanding_heredoc,
    holds_process_substitution,
    holds_subscript_expansion,
    holds_unsettled_expansion,
    is_settled_create_segment,
    is_settled_pipe_reader,
    is_settled_step,
)
from blocking.merge_review_gate_parts.wrapped_creates import unplaced_creates
from hooks_constants.merge_review_gate_constants import (
    ALL_BACKGROUND_OPERATORS,
    ALL_CLOSING_CHARACTERS,
    ALL_COMMAND_PREFIX_WORDS,
    ALL_COMPOUND_BODY_WORDS,
    ALL_COMPOUND_CLOSE_WORDS,
    ALL_COMPOUND_OPEN_WORDS,
    ALL_EXPANSION_MARKS,
    ALL_EXPANSION_OPENER_CHARACTERS,
    EXPANSION_START_CHARACTER,
    QUOTED_EXPANSION_MARK,
    UNREADABLE_WORD_MARK,
    ALL_FOLDER_CHANGE_WORDS,
    ALL_PIPE_OPERATORS,
    ALL_SHELL_EXPANSION_CHARACTERS,
    EXTENDED_GLOB_WORD_PATTERN,
    ALL_UNBALANCED_TOKENIZATION_MODES,
    BRACE_CLOSE_TOKEN,
    BRACE_OPEN_OPERATOR,
    END_OF_OPTIONS_PREFIX,
    IS_POSIX_TOKENIZATION,
    LINE_FEED,
    LOOSE_GH_PROGRAM_PATTERN,
    LOOSE_OPEN_WORD_PATTERN,
    LOOSE_PULL_REQUEST_SCRIPT_PATTERN,
    SEGMENT_TOKEN_JOIN,
    SUBSHELL_CLOSE_TOKEN,
    SUBSHELL_OPEN_OPERATOR,
    SUBSTITUTION_KEY_IGNORED_PATTERN,
    TILDE_CHARACTER,
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
        is_plain_words: False when an option word bash may split or change,
            such as an unquoted ``$X`` or brace, or a ``$`` expansion in a flag
            or its value other than a text value such as a title, body or label, so bash may hand gh
            other words than these.
        is_head_settled: False unless every step before the create and its
            own words are shapes ``settled_steps`` counts as settled, so no
            step may move the head, branch or repository after the gate reads them.
    """

    all_arguments: tuple[str, ...]
    folder: str | None
    is_folder_followed: bool
    all_command_words: tuple[str, ...] = field(default=(), compare=False)
    is_plain_words: bool = True
    is_head_settled: bool = True


@dataclass
class _Walk:
    all_creates: list[PlacedCreate]
    has_expanding_heredoc: bool = False
    has_unsettled_expansion: bool = False
    has_run_other_program: bool = False
    is_in_create_words: bool = False


@dataclass(frozen=True)
class _Group:
    first_create_index: int
    is_after_pipe: bool
    is_unsettling_after_close: bool = False


@dataclass
class _Scope:
    state: FolderState
    is_posix: bool = IS_POSIX_TOKENIZATION
    previous_operator: str = ""
    brace_depth: int = 0
    compound_depth: int = 0
    all_saved: list[FolderState] = field(default_factory=list)
    all_live_substitution_keys: frozenset[str] = frozenset()
    heredoc_substitution_by_key: dict[str, str] = field(default_factory=dict)
    all_marks_by_word: dict[str, frozenset[str]] | None = None
    is_expanding_text: bool = True
    all_open_groups: list[_Group] = field(default_factory=list)
    all_pipeline_create_indexes: list[int] = field(default_factory=list)
    is_next_group_unsettling: bool = False


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
    walk did not place, and it comes back unfollowed. Two creates with the
    same options stay two creates when their command words differ, so a
    ``GH_REPO=`` prefix on one of them is kept.

    Args:
        command: The shell command text.
        folder: The folder the command starts in, or None for the gate's own.
    """
    start = FolderState(folder, True)
    all_creates: list[PlacedCreate] = []
    walk = _Walk(all_creates, has_expanding_heredoc=holds_expanding_heredoc(command))
    _walk_text(walk, command, start, 0)
    if (
        holds_process_substitution(command)
        or holds_subscript_expansion(command)
        or walk.has_unsettled_expansion
    ):
        _unsettle(walk, range(len(all_creates)))
    all_placed_arguments = [each_create.all_arguments for each_create in all_creates]
    all_creates.extend(
        PlacedCreate(each_arguments, None, False, each_words, is_head_settled=False)
        for each_arguments, each_words in unplaced_creates(command, all_placed_arguments)
    )
    return list(
        {(each_create, each_create.all_command_words): each_create for each_create in all_creates}.values()
    )


def _walk_text(walk: _Walk, text: str, state: FolderState, depth: int) -> FolderState:
    if depth > MAXIMUM_UNWRAP_DEPTH:
        if _may_hold_create(text):
            walk.all_creates.append(PlacedCreate((), None, False, is_head_settled=False))
        return state
    walk.has_unsettled_expansion = walk.has_unsettled_expansion or holds_unsettled_expansion(text)
    all_lines = quote_aware_lines(text)
    all_token_lines = _posix_token_lines(all_lines) if all_lines is not None else None
    if all_lines is None or all_token_lines is None:
        return _walk_unbalanced_text(walk, text, state, depth)
    all_marks_by_word = _marks_by_word(all_lines, all_token_lines)
    scope = _Scope(
        state,
        all_live_substitution_keys=_substitution_keys(text),
        heredoc_substitution_by_key=_heredoc_substitution_by_key(text),
        all_marks_by_word=all_marks_by_word,
        is_expanding_text=all_marks_by_word is None and holds_unquoted_expansion(text),
    )
    return _walk_token_lines(walk, all_token_lines, scope, depth)


def _may_hold_create(text: str) -> bool:
    is_gh_create = LOOSE_GH_PROGRAM_PATTERN.search(text) and LOOSE_OPEN_WORD_PATTERN.search(text)
    return bool(is_gh_create or LOOSE_PULL_REQUEST_SCRIPT_PATTERN.search(text))


def _posix_token_lines(all_lines: list[str]) -> list[list[str]] | None:
    all_token_lines = [
        each_tokens
        for each_line in all_lines
        if (each_tokens := operator_aware_tokens(each_line, IS_POSIX_TOKENIZATION)) is not None
    ]
    return all_token_lines if len(all_token_lines) == len(all_lines) else None


def _marks_by_word(all_lines: list[str], all_token_lines: list[list[str]]) -> dict[str, frozenset[str]] | None:
    """Return the expansion marks each POSIX word of a text carries, gathered over every place it appears.

    ::

        gh pr create --body "$(date)" --head x  -> {"$(date)": {quoted mark}, ...}
        X=--head=y; gh pr create $X             -> {"$X": {unreadable mark}, ...}

    A word that appears twice, once quoted and once not, carries both
    marks. None means a marked line split into other words, so no word can
    be judged.
    """
    all_marks_by_word: dict[str, set[str]] = {}
    for each_line, each_tokens in zip(all_lines, all_token_lines, strict=False):
        all_marked_tokens = operator_aware_tokens(expansion_marked_line(each_line), IS_POSIX_TOKENIZATION)
        if all_marked_tokens is None or len(all_marked_tokens) != len(each_tokens):
            return None
        for each_token, each_marked_token in zip(each_tokens, all_marked_tokens, strict=True):
            all_marks_by_word.setdefault(each_token, set()).update(ALL_EXPANSION_MARKS.intersection(each_marked_token))
    return {each_word: frozenset(each_marks) for each_word, each_marks in all_marks_by_word.items()}


def _walk_unbalanced_text(
    walk: _Walk, text: str, state: FolderState, depth: int
) -> FolderState:
    all_end_states: set[FolderState] = set()
    has_run_other_program = walk.has_run_other_program
    for each_text in dict.fromkeys([text, quoted_line_breaks_joined(text)]):
        for each_is_posix in ALL_UNBALANCED_TOKENIZATION_MODES:
            walk.has_run_other_program = has_run_other_program
            all_token_lines = _line_tokens(each_text, each_is_posix)
            scope = _Scope(
                state,
                each_is_posix,
                all_live_substitution_keys=_substitution_keys(each_text),
                is_expanding_text=holds_unquoted_expansion(each_text),
            )
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
    _count_unsettling_inner_closes(walk, scope, all_segment_tokens)
    closing_count = _closing_count(all_segment_tokens)
    _close_groups(walk, scope, closing_count, operator)
    _restore_closed_subshells(scope, closing_count)
    if operator in (SUBSHELL_OPEN_OPERATOR, BRACE_OPEN_OPERATOR):
        is_after_pipe = scope.previous_operator in ALL_PIPE_OPERATORS
        scope.all_open_groups.append(
            _Group(len(walk.all_creates), is_after_pipe, scope.is_next_group_unsettling)
        )
        scope.is_next_group_unsettling = False
    if operator == SUBSHELL_OPEN_OPERATOR:
        scope.all_saved.append(scope.state)
    scope.brace_depth += operator == BRACE_OPEN_OPERATOR
    scope.previous_operator = operator


def _close_groups(walk: _Walk, scope: _Scope, closing_count: int, operator: str) -> None:
    """Leave each create in a closing group unsettled when a pipe or a background job holds the group.

    ::

        (gh pr create --fill; echo x) | git push ...   -> the create is not settled
        echo | { gh pr create --fill; }                 -> the create is not settled
        (cd sub && gh pr create --fill)                 -> nothing changes
        x=$(gh pr create --fill) ; gh pr create         -> the later create is not settled

    A substitution the words split off as a group, such as ``x=$(...)``,
    runs before the words around it, so an unsettled step there counts once
    the group closes.
    """
    if closing_count == 0:
        return
    kept_count = max(0, len(scope.all_open_groups) - closing_count)
    is_held = operator in ALL_PIPE_OPERATORS or operator in ALL_BACKGROUND_OPERATORS
    for each_group in scope.all_open_groups[kept_count:]:
        if each_group.is_unsettling_after_close:
            walk.has_run_other_program = True
        if is_held or each_group.is_after_pipe:
            _unsettle(walk, range(each_group.first_create_index, len(walk.all_creates)))
    del scope.all_open_groups[kept_count:]


def _count_unsettling_inner_closes(
    walk: _Walk, scope: _Scope, all_segment_tokens: list[str]
) -> None:
    """Count an unsettled step whose substitution closes inside the words that follow it.

    ::

        printf $(echo -v) PATH %s /x && gh pr create   -> the create is not settled
        x=$(echo a) ; gh pr create                     -> left to ``_close_groups``

    The words split ``printf $(echo -v) PATH`` into ``printf $`` and
    ``echo -v ) PATH``, so the ``)`` sits inside a segment and no group
    closes there. An open group whose opener step was not settled counts
    once such a ``)`` is read, as ``_close_groups`` counts it at a close.
    """
    inner_close_count = _without_closing_tokens(all_segment_tokens).count(SUBSHELL_CLOSE_TOKEN)
    if inner_close_count == 0:
        return
    first_closed_index = max(0, len(scope.all_open_groups) - inner_close_count)
    if any(
        each_group.is_unsettling_after_close
        for each_group in scope.all_open_groups[first_closed_index:]
    ):
        walk.has_run_other_program = True


def _unsettle(walk: _Walk, all_create_indexes: Iterable[int]) -> None:
    for each_index in all_create_indexes:
        walk.all_creates[each_index] = replace(walk.all_creates[each_index], is_head_settled=False)


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
        _close_groups(walk, scope, 1, operator)
    first_word = unquoted_token(all_tokens[0]).lower() if all_tokens else ""
    scope.compound_depth += first_word in ALL_COMPOUND_OPEN_WORDS
    is_piped = scope.previous_operator in ALL_PIPE_OPERATORS or operator in ALL_PIPE_OPERATORS
    is_modeled = (
        not is_piped
        and scope.brace_depth == 0
        and scope.compound_depth == 0
        and first_word not in ALL_COMPOUND_BODY_WORDS
    )
    next_state = _segment_step(walk, scope, all_tokens, operator, depth, is_modeled)
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
    walk: _Walk, scope: _Scope, all_tokens: list[str], operator: str, depth: int, is_modeled: bool
) -> FolderState:
    state = scope.state
    all_readings = _wrapper_readings(all_tokens)
    create_index = _placed_create_index(walk, scope, all_readings)
    if _runs_a_wrapped_text_after_prefixes(all_readings):
        walk.has_run_other_program = True
    is_outer_in_create_words = walk.is_in_create_words
    walk.is_in_create_words = is_outer_in_create_words or create_index is not None
    for each_child_text in dict.fromkeys(
        each_text for each_reading in all_readings for each_text in _child_shell_texts(each_reading, scope)
    ):
        _walk_text(walk, each_child_text, state, depth + 1)
    walk.is_in_create_words = is_outer_in_create_words
    next_state = _state_after_evaluation(walk, scope, all_readings, depth)
    _settle_segment(walk, scope, all_tokens, operator, create_index)
    next_state = state_after_folder_change(_without_command_prefixes(all_tokens), next_state)
    if (next_state != state and not is_modeled) or _has_unmodeled_folder_word(all_tokens):
        return FolderState(None, False)
    return next_state


def _placed_create_index(walk: _Walk, scope: _Scope, all_readings: list[list[str]]) -> int | None:
    for each_reading in all_readings:
        all_arguments = create_arguments(each_reading)
        if all_arguments is None:
            continue
        walk.all_creates.append(
            PlacedCreate(
                tuple(all_arguments),
                scope.state.folder,
                scope.state.is_followed,
                tuple(each_reading),
                _are_plain_words(all_arguments, scope),
            )
        )
        return len(walk.all_creates) - 1
    return None


def _settle_segment(
    walk: _Walk, scope: _Scope, all_tokens: list[str], operator: str, create_index: int | None
) -> None:
    """Record whether a segment leaves the head settled, once the substitutions in its words have run.

    ::

        cd ../a, cat body.md, echo hi 2>&1        -> later creates stay settled
        git push ..., X=1, echo a > f, ./cat     -> later creates are not settled
        gh pr create --title "$(git push ...)"   -> this create is not settled
        gh pr create --fill | git push ...       -> this create is not settled

    ``settled_steps`` judges each shape. A create is settled when every step
    the walk read before it was settled, its own words are settled, it is the
    first member of any pipeline that holds it and no background job holds
    it. An unsettled create counts as an unsettled step for later creates.
    """
    is_after_pipe = scope.previous_operator in ALL_PIPE_OPERATORS
    if is_after_pipe and (
        create_index is not None or not is_settled_pipe_reader(all_tokens, walk.has_expanding_heredoc)
    ):
        _unsettle(walk, scope.all_pipeline_create_indexes)
    if create_index is None:
        is_settled = is_settled_step(
            all_tokens, walk.is_in_create_words, walk.has_expanding_heredoc
        )
        if _opens_substitution(all_tokens, operator):
            scope.is_next_group_unsettling = not is_settled
        elif not is_settled:
            walk.has_run_other_program = True
    else:
        _settle_create(walk, scope, all_tokens, operator, create_index)
    if operator not in ALL_PIPE_OPERATORS:
        if operator in ALL_BACKGROUND_OPERATORS:
            _unsettle(walk, scope.all_pipeline_create_indexes)
        scope.all_pipeline_create_indexes = []


def _opens_substitution(all_tokens: list[str], operator: str) -> bool:
    return (
        operator == SUBSHELL_OPEN_OPERATOR
        and bool(all_tokens)
        and all_tokens[-1].endswith(EXPANSION_START_CHARACTER)
    )


def _settle_create(walk: _Walk, scope: _Scope, all_tokens: list[str], operator: str, create_index: int) -> None:
    is_settled = (
        not walk.has_run_other_program
        and scope.previous_operator not in ALL_PIPE_OPERATORS
        and operator not in ALL_BACKGROUND_OPERATORS
        and is_settled_create_segment(all_tokens, walk.has_expanding_heredoc)
    )
    if not is_settled:
        _unsettle(walk, [create_index])
        walk.has_run_other_program = True
    if operator in ALL_PIPE_OPERATORS:
        scope.all_pipeline_create_indexes.append(create_index)


def _runs_a_wrapped_text_after_prefixes(all_readings: list[list[str]]) -> bool:
    """Return whether a segment runs a ``bash -c`` or ``eval`` text behind an assignment or a wrapper word.

    ::

        bash -c "gh pr create"              -> False
        BASH_ENV=x bash -c "gh pr create"   -> True
        env bash -c "gh pr create"          -> True
    """
    for each_reading in all_readings:
        if not each_reading:
            continue
        program = segment_program_and_arguments(each_reading)[0]
        is_wrapping = (
            string_exec_inner_command(each_reading) is not None
            or program.lower() in ALL_STRING_EVALUATING_PROGRAM_NAMES
        )
        if is_wrapping and unquoted_token(each_reading[0]) != program:
            return True
    return False


def _are_plain_words(all_create_words: list[str], scope: _Scope) -> bool:
    """Return whether bash hands gh the create options the walk read, one for one.

    Each option word is judged on its own quoting::

        --head feature, --base main, --title "a [b] $(date)"  -> True
        --body "$(cat <<'EOF' ... EOF)"                        -> True, a title or body value in quotes
        $X, "$@", --he{ad=a,ad=b}, --body $(cat f)             -> False, bash may split or change the word
        --label "$L", --reviewer "$(gh api user -q .login)"    -> True, gh takes the quoted word as that flag's value
        --head "$B", --base "$M", -R "$REPO"                   -> False, a flag or its value the gate cannot read
        --title -t "$X", --body -b "--he$(printf ad)=x"        -> False, -t is the title, so gh reads "$X" as a flag

    A title, body, body file, label, reviewer, assignee, milestone, project
    or template value may hold an expansion inside quotes, since bash keeps
    it one word that gh takes as that flag's value. The option walk that
    reads the head, ``create_options.text_value_indexes``, decides which
    words are such values. Any other word must hold none.
    """
    all_text_value_indexes = text_value_indexes(all_create_words)
    for each_index, each_word in enumerate(all_create_words):
        all_marks = _word_marks(each_word, scope)
        if UNREADABLE_WORD_MARK in all_marks:
            return False
        if QUOTED_EXPANSION_MARK in all_marks and each_index not in all_text_value_indexes:
            return False
    return True


def _word_marks(word: str, scope: _Scope) -> frozenset[str]:
    """Return the marks of one word: from the marked lines, or from its own characters when no line marked it.

    ::

        a word the marked lines hold           -> the marks gathered there
        a word with $ or a backtick, unmarked  -> the quoted mark
        a brace, glob or leading ~ word in a
        text that holds one outside quotes     -> the unreadable mark
    """
    if scope.all_marks_by_word is not None and word in scope.all_marks_by_word:
        return scope.all_marks_by_word[word]
    all_marks: set[str] = set(ALL_EXPANSION_MARKS.intersection(word))
    if not ALL_EXPANSION_OPENER_CHARACTERS.isdisjoint(word):
        all_marks.add(QUOTED_EXPANSION_MARK)
    if scope.is_expanding_text and _holds_expansion_word(word):
        all_marks.add(UNREADABLE_WORD_MARK)
    return frozenset(all_marks)


def _holds_expansion_word(word: str) -> bool:
    return (
        word.startswith(TILDE_CHARACTER)
        or not ALL_SHELL_EXPANSION_CHARACTERS.isdisjoint(word)
        or EXTENDED_GLOB_WORD_PATTERN.search(word) is not None
    )


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
    all_substitution_texts: list[str] = []
    for each_text in all_command_substitution_texts(SEGMENT_TOKEN_JOIN.join(all_tokens)):
        each_key = _substitution_key(each_text)
        if each_key in scope.all_live_substitution_keys:
            all_substitution_texts.append(each_text)
        elif each_key in scope.heredoc_substitution_by_key:
            all_substitution_texts.append(scope.heredoc_substitution_by_key[each_key])
    return [*([string_exec_text] if string_exec_text is not None else []), *all_substitution_texts]


def _heredoc_substitution_by_key(text: str) -> dict[str, str]:
    """Return each substitution of a text, as written, by the key of its words once heredoc bodies are cut.

    ::

        --body "$(cat <<'EOF' / hi / EOF / git push / )"
            -> {key of "cat <<'EOF' / git push": "cat <<'EOF' / hi / EOF / git push / "}

    The lines bash reads drop each heredoc body, so a substitution read from
    a word no longer matches the text it came from. This map gives the walk
    the substitution with its bodies, so each body is cut once.
    """
    all_texts_by_key: dict[str, str] = {}
    for each_text in all_command_substitution_texts(text):
        all_lines = quote_aware_lines(each_text)
        if all_lines is not None:
            all_texts_by_key.setdefault(_substitution_key(LINE_FEED.join(all_lines)), each_text)
    return all_texts_by_key


def _substitution_keys(text: str) -> frozenset[str]:
    return frozenset(_substitution_key(each_text) for each_text in all_command_substitution_texts(text))


def _substitution_key(text: str) -> str:
    return SUBSTITUTION_KEY_IGNORED_PATTERN.sub("", text)

