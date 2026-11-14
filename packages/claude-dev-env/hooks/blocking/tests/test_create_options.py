"""Behavioral tests for reading the values one create's flags give.

["--head", "a", "-dHb"]          -> ["a", "b"]
["--title", "-Hx", "--head", "a"] -> ["a"]
"""

from __future__ import annotations

import pytest

from blocking.merge_review_gate_parts.create_options import all_option_values


@pytest.mark.parametrize(
    ("all_words", "all_expected"),
    [
        (["--head", "a", "-dHb", "-H=c", "--head=d", "-Hf"], ["a", "b", "c", "d", "f"]),
        (["-dH", "a"], ["a"]),
        (["--title", "-Hx", "--head", "a"], ["a"]),
        (["--body", "-H", "--title", "x"], []),
        (["-bHx", "-tH", "y"], []),
        (["--fill", "-H", "a"], ["a"]),
        (["--draft", "--head", "a", "--", "--head", "b"], ["a"]),
        (["--label=x", "-H", "'a'"], ["a"]),
    ],
)
def test_should_return_each_value_the_option_is_given_as_gh_reads_it(
    all_words: list[str], all_expected: list[str]
) -> None:
    assert all_option_values(all_words, "--head", "H") == all_expected


def test_should_read_a_repository_flag_word_that_is_a_title_value_as_the_title() -> None:
    assert all_option_values(["--title", "--repo=x/y", "-R", "o/r"], "--repo", "R") == ["o/r"]
