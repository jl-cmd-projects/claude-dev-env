"""Behavioral tests for finding wrapped creates the folder walk did not place.

bash -c "gh pr create --fill"                 -> ("--fill",) unless the walk placed it
--body "$(cat <<'B' ... B)" with a create     -> nothing: the heredoc body runs no command
"""

from __future__ import annotations

from blocking.merge_review_gate_parts.wrapped_creates import unplaced_creates


def _unplaced_create_arguments(
    command: str, all_placed_arguments: list[tuple[str, ...]]
) -> list[tuple[str, ...]]:
    return [each_arguments for each_arguments, _each_words in unplaced_creates(command, all_placed_arguments)]


def test_should_give_each_unplaced_create_the_words_of_the_command_that_runs_it() -> None:
    command = 'bash -c "cd sub && gh -R o/r pr create --repo a/b"'
    assert unplaced_creates(command, []) == [
        (("--repo", "a/b", "-R", "o/r"), ("gh", "-R", "o/r", "pr", "create", "--repo", "a/b"))
    ]


def test_should_return_a_wrapped_create_the_walk_did_not_place() -> None:
    assert _unplaced_create_arguments('bash -c "cd sub && gh pr create --fill"', []) == [("--fill",)]


def test_should_return_nothing_for_a_create_the_walk_placed_with_a_quoted_line_break() -> None:
    command = "bash -c \"gh pr create --head one --body 'a\nb'\""
    assert _unplaced_create_arguments(command, [("--head", "one", "--body", "a\nb")]) == []


def test_should_not_join_the_next_line_of_a_wrapped_script_to_its_create() -> None:
    assert _unplaced_create_arguments("bash -c 'gh pr create --fill\nls'", [("--fill",)]) == []


def test_should_read_no_create_in_a_heredoc_body_inside_a_quoted_substitution() -> None:
    command = (
        'gh pr create --head one --body "$(cat <<\'B\'\nsee "q" ; gh pr create --head two\nB\n)"'
    )
    assert _unplaced_create_arguments(command, [("--head", "one", "--body", "x")]) == []
