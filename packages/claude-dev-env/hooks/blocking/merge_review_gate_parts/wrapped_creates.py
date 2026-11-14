"""Find each create that a wrapped inner text holds and the folder walk did not place.

::

    bash -c "cd sub && gh pr create --fill"     -> ("--fill",) when the walk missed it
    gh pr create --body "a\\ngh pr create"       -> nothing: a quoted value runs no command

``hooks_constants.shell_command_wrappers.all_wrapped_command_texts`` lists the
command and each text a wrapper or substitution inside it runs. A text is
skipped when it is the command itself, or a closed text with its line breaks
read as spaces, or a text unwrapped from one. Each other text is cut into POSIX
words, and each create it holds is compared with the creates the walk placed,
line breaks read as spaces.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.followup_pr_dedupe import create_arguments
from blocking.merge_review_gate_parts.quoted_lines import quote_aware_lines
from hooks_constants.merge_review_gate_constants import (
    IS_POSIX_TOKENIZATION,
    SUBSHELL_CLOSE_TOKEN,
)
from hooks_constants.pytest_invocation import unquoted_token
from hooks_constants.shell_command_evaluation_constants import (
    ALL_LINE_BREAK_CHARACTERS,
    QUOTED_LINE_BREAK_REPLACEMENT,
)
from hooks_constants.shell_command_pipeline import (
    join_line_continuations,
    operator_aware_tokens,
    scannable_command_lines,
    segments_with_following_operator,
)
from hooks_constants.shell_command_wrappers import (
    all_wrapped_command_texts,
    quoted_line_breaks_joined,
)


def unplaced_creates(
    command: str, all_placed_arguments: Sequence[Sequence[str]]
) -> list[tuple[tuple[str, ...], tuple[str, ...]]]:
    """Return the arguments and command words of each wrapped create the walk did not place.

    ::

        'bash -c "gh pr create --fill"', []             -> [(("--fill",), ("gh", "pr", "create", "--fill"))]
        'bash -c "gh pr create --fill"', [("--fill",)]  -> []

    Args:
        command: The shell command text.
        all_placed_arguments: The arguments of each create the walk placed.

    Returns:
        Each unplaced create's arguments and the words of the simple command that runs it,
        in the order the wrapped texts list them.
    """
    all_known = {_normalized(each_arguments) for each_arguments in all_placed_arguments}
    return [
        (tuple(all_arguments), tuple(all_words))
        for all_arguments, all_words in _wrapped_creates(command)
        if _normalized(all_arguments) not in all_known
    ]


def _normalized(all_arguments: Sequence[str]) -> tuple[str, ...]:
    all_words = [
        _line_breaks_as_spaces(unquoted_token(each_argument)) for each_argument in all_arguments
    ]
    while all_words and all_words[-1] == SUBSHELL_CLOSE_TOKEN:
        all_words.pop()
    return tuple(all_words)


def _line_breaks_as_spaces(word: str) -> str:
    return "".join(
        QUOTED_LINE_BREAK_REPLACEMENT
        if each_character in ALL_LINE_BREAK_CHARACTERS
        else each_character
        for each_character in word
    )


def _wrapped_creates(command: str) -> list[tuple[list[str], list[str]]]:
    all_wrapped_texts = all_wrapped_command_texts(command)
    all_skipped_texts = {
        command,
        quoted_line_breaks_joined(command),
        *_flattened_balanced_texts(all_wrapped_texts),
    }
    return [
        (each_arguments, each_segment)
        for each_text in all_wrapped_texts
        if each_text not in all_skipped_texts
        for each_segment in _posix_segments(each_text)
        if (each_arguments := create_arguments(each_segment)) is not None
    ]


def _flattened_balanced_texts(all_texts: list[str]) -> set[str]:
    return {
        each_unwrapped
        for each_text in all_texts
        if quote_aware_lines(each_text) is not None
        and (each_flattened := _line_breaks_as_spaces(each_text)) != each_text
        for each_unwrapped in all_wrapped_command_texts(each_flattened)
    }


def _posix_segments(text: str) -> list[list[str]]:
    return [
        each_segment
        for each_line in scannable_command_lines(join_line_continuations(text))
        for each_segment, _each_operator in segments_with_following_operator(
            operator_aware_tokens(each_line, IS_POSIX_TOKENIZATION) or []
        )
    ]
