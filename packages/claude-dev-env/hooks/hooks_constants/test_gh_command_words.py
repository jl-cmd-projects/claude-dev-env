"""Tests for the shared reader of gh command words and standalone options."""

from __future__ import annotations

import pytest

from hooks_constants.gh_command_words import gh_command_words, gh_command_words_and_options


@pytest.mark.parametrize(
    ("all_arguments", "all_expected_words"),
    [
        (["pr", "list"], ["pr", "list"]),
        (["-R", "o/r", "pr", "list"], ["pr", "list"]),
        (["pr", "--repo", "o/r", "view", "12"], ["pr", "view", "12"]),
        (["api", "-X", "POST", "graphql", "-f", "query=x"], ["api", "graphql"]),
        (["api", "-H", "Accept: application/json", "graphql"], ["api", "graphql"]),
        (["release", "view", "--json", "name"], ["release", "view"]),
        (["pr", "merge", "12", "--body", "-h"], ["pr", "merge", "12"]),
        (["pr", "list", "--repo=o/r"], ["pr", "list"]),
    ],
)
def test_should_return_the_words_past_options_and_their_values(
    all_arguments: list[str], all_expected_words: list[str]
) -> None:
    assert gh_command_words(all_arguments) == all_expected_words


@pytest.mark.parametrize(
    ("all_arguments", "all_expected_options"),
    [
        (["pr", "list", "--web"], ["--web"]),
        (["pr", "list", "--search", "-w"], ["--search"]),
        (["pr", "merge", "12", "--body", "-h"], ["--body"]),
        (["pr", "view", "-w", "-h"], ["-w", "-h"]),
        (["workflow", "run", "ci.yml", "--ref=main"], ["--ref"]),
        (["api", "graphql", "-f", "-X"], ["-f"]),
        (["repo", "create", "n", "-p", "o/t"], ["-p"]),
    ],
)
def test_should_return_each_option_that_is_not_another_option_value(
    all_arguments: list[str], all_expected_options: list[str]
) -> None:
    assert gh_command_words_and_options(all_arguments)[1] == all_expected_options
