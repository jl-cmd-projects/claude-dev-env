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
from dataclasses import dataclass
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.merge_review_gate_constants import (
    ALL_CREATE_TEXT_OPTIONS,
    ALL_VALUELESS_LONG_CREATE_OPTIONS,
    ALL_VALUELESS_SHORT_CREATE_LETTERS,
    LONG_OPTION_PREFIX,
    OPTION_AND_VALUE_WIDTH,
    OPTION_VALUE_SEPARATOR,
    SHORT_OPTION_PREFIX,
)
from hooks_constants.pytest_invocation import unquoted_token


@dataclass(frozen=True)
class _OptionValue:
    """One value gh gives an option: the option as written, the index of the word that holds the value, and the value."""

    option: str
    value_index: int
    value: str | None


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
    all_spellings = {long_option, SHORT_OPTION_PREFIX + short_letter}
    return [
        unquoted_token(each_reading.value)
        for each_reading in _all_option_readings(all_words)
        if each_reading.option in all_spellings and each_reading.value is not None
    ]


def text_value_indexes(all_words: list[str]) -> frozenset[int]:
    """Return the index of each word gh reads as the value of a title, body, label or other text option.

    The same walk that reads a head or a repository decides it, so a word
    that is itself a text option's value is never an option::

        ["--title", "$X"]                -> {1}
        ["--title=$X"], ["-dt$X"]        -> {0}
        ["--title", "-t", "$X"]          -> {1}, so "$X" sits where gh reads a flag
        ["--head", "--title=$X"]         -> {}, the word is the head

    Args:
        all_words: The create's words after the program.
    """
    return frozenset(
        each_reading.value_index
        for each_reading in _all_option_readings(all_words)
        if each_reading.option in ALL_CREATE_TEXT_OPTIONS
    )


def _all_option_readings(all_words: list[str]) -> list[_OptionValue]:
    all_readings: list[_OptionValue] = []
    index = 0
    while index < len(all_words) and unquoted_token(all_words[index]) != LONG_OPTION_PREFIX:
        following = all_words[index + 1] if index + 1 < len(all_words) else None
        option, flag_value, width = _option_reading(unquoted_token(all_words[index]), following)
        if option is not None:
            value_index = index if width == 1 else index + 1
            all_readings.append(_OptionValue(option, value_index, flag_value))
        index += width
    return all_readings


def _option_reading(word: str, following: str | None) -> tuple[str | None, str | None, int]:
    if not word.startswith(SHORT_OPTION_PREFIX) or word == SHORT_OPTION_PREFIX:
        return None, None, 1
    if not word.startswith(LONG_OPTION_PREFIX):
        return _short_cluster_reading(word[len(SHORT_OPTION_PREFIX) :], following)
    option_name, separator, inline_value = word.partition(OPTION_VALUE_SEPARATOR)
    if option_name in ALL_VALUELESS_LONG_CREATE_OPTIONS:
        return None, None, 1
    if separator:
        return option_name, inline_value, 1
    return option_name, following, OPTION_AND_VALUE_WIDTH


def _short_cluster_reading(
    all_letters: str, following: str | None
) -> tuple[str | None, str | None, int]:
    for each_index, each_letter in enumerate(all_letters):
        if each_letter in ALL_VALUELESS_SHORT_CREATE_LETTERS:
            continue
        inline_value = all_letters[each_index + 1 :].removeprefix(OPTION_VALUE_SEPARATOR)
        option = SHORT_OPTION_PREFIX + each_letter
        if inline_value:
            return option, inline_value, 1
        return option, following, OPTION_AND_VALUE_WIDTH
    return None, None, 1
