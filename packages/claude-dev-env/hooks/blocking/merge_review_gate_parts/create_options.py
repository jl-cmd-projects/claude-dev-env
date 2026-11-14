"""Read the values one create's flags give, the way gh reads them.

::

    ["--head", "a", "-dHb"], "--head", "H"          -> ["a", "b"]
    ["--title", "-Hx", "--head", "a"], "--head", "H" -> ["a"]
    ["--title", "--repo=x/y"], "--repo", "R"       -> []

A word that is the value of another option is that option's value, not a
flag. A short-flag cluster such as ``-dHb`` gives the rest of the cluster
to its first letter that takes a value. Reading stops at ``--``.
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.merge_review_gate_constants import (
    ALL_VALUELESS_LONG_CREATE_OPTIONS,
    ALL_VALUELESS_SHORT_CREATE_LETTERS,
    LONG_OPTION_PREFIX,
    OPTION_AND_VALUE_WIDTH,
    OPTION_VALUE_SEPARATOR,
    SHORT_OPTION_PREFIX,
)
from hooks_constants.pytest_invocation import unquoted_token


def all_option_values(all_words: list[str], long_option: str, short_letter: str) -> list[str]:
    """Return each value one option is given, in command order.

    ::

        ["-H", "a", "--head=b"], "--head", "H"  -> ["a", "b"]
        ["--body", "-H", "x"], "--head", "H"     -> []

    Args:
        all_words: The create's words after the program.
        long_option: The long spelling, such as ``--head``.
        short_letter: The short letter, such as ``H``.
    """
    all_values: list[str] = []
    index = 0
    while index < len(all_words) and unquoted_token(all_words[index]) != LONG_OPTION_PREFIX:
        following = all_words[index + 1] if index + 1 < len(all_words) else None
        flag_value, width = _option_reading(
            unquoted_token(all_words[index]), following, long_option, short_letter
        )
        if flag_value is not None:
            all_values.append(unquoted_token(flag_value))
        index += width
    return all_values


def _option_reading(
    word: str, following: str | None, long_option: str, short_letter: str
) -> tuple[str | None, int]:
    if not word.startswith(SHORT_OPTION_PREFIX) or word == SHORT_OPTION_PREFIX:
        return None, 1
    if not word.startswith(LONG_OPTION_PREFIX):
        return _short_cluster_reading(word[len(SHORT_OPTION_PREFIX) :], following, short_letter)
    option_name, separator, inline_value = word.partition(OPTION_VALUE_SEPARATOR)
    if option_name == long_option:
        return (inline_value, 1) if separator else (following, OPTION_AND_VALUE_WIDTH)
    if separator or option_name in ALL_VALUELESS_LONG_CREATE_OPTIONS:
        return None, 1
    return None, OPTION_AND_VALUE_WIDTH


def _short_cluster_reading(
    all_letters: str, following: str | None, short_letter: str
) -> tuple[str | None, int]:
    for each_index, each_letter in enumerate(all_letters):
        if each_letter in ALL_VALUELESS_SHORT_CREATE_LETTERS:
            continue
        inline_value = all_letters[each_index + 1 :].removeprefix(OPTION_VALUE_SEPARATOR)
        flag_value, width = (
            (inline_value, 1) if inline_value else (following, OPTION_AND_VALUE_WIDTH)
        )
        return (flag_value if each_letter == short_letter else None), width
    return None, 1
