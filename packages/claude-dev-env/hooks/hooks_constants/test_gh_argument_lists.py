"""Pin how gh_argument_lists finds the gh calls a shell command runs."""

from __future__ import annotations

import pytest

from hooks_constants import gh_argument_lists


@pytest.mark.parametrize(
    ("command", "all_expected_argument_lists"),
    [
        ("gh pr view 12", [["pr", "view", "12"]]),
        ("$s = gh run watch 1", [["run", "watch", "1"]]),
        ("{gh run view 1}", [["run", "view", "1", "}"]]),
        ("watch -n 5 gh run view 1", [["run", "view", "1"]]),
        ('bash -c "gh run view 1"', [["run", "view", "1"]]),
        ('echo "gh run watch"', []),
        ("git status", []),
    ],
)
def test_should_return_the_arguments_of_each_gh_call(
    command: str, all_expected_argument_lists: list[list[str]]
) -> None:
    assert gh_argument_lists.all_gh_call_argument_lists(command) == all_expected_argument_lists


def test_should_split_a_segment_at_each_glued_brace() -> None:
    assert gh_argument_lists.brace_split_segments(["{gh", "run", "view", "1}"]) == [
        ["{", "gh", "run", "view", "1", "}"]
    ]
    assert gh_argument_lists.brace_split_segments(["${name}"]) == [["${name}"]]


@pytest.mark.parametrize(
    ("all_arguments", "expected_interval_and_command"),
    [
        (["-n", "5", "gh", "run", "view", "1"], (5.0, "gh run view 1")),
        (["--interval=30", "gh", "pr", "view"], (30.0, "gh pr view")),
        (["gh", "run", "view", "1"], (2.0, "gh run view 1")),
        (["-n", "$delay", "gh", "run", "view"], (None, "gh run view")),
    ],
)
def test_should_read_the_watch_interval_and_the_command_it_runs(
    all_arguments: list[str], expected_interval_and_command: tuple[float | None, str]
) -> None:
    assert (
        gh_argument_lists.watch_interval_and_command(all_arguments) == expected_interval_and_command
    )
