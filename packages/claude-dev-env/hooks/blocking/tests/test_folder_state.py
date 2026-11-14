"""Behavioral tests for the folder state the create walk carries."""

from __future__ import annotations

import pytest

from blocking.merge_review_gate_parts.folder_state import FolderState, state_after_folder_change

START = FolderState("/w", True)


@pytest.mark.parametrize(
    ("all_tokens", "expected"),
    [
        (["cd", "sub"], FolderState("/w/sub", True)),
        (["cd", "/abs"], FolderState("/abs", True)),
        (["cd", "-"], FolderState(None, False)),
        (["cd", "$X"], FolderState(None, False)),
        (["pushd", "a"], FolderState("/w/a", True, (("/w", True),))),
        (["popd"], FolderState(None, False)),
        (["git", "status"], START),
    ],
)
def test_state_after_folder_change_should_follow_each_folder_change(
    all_tokens: list[str], expected: FolderState
) -> None:
    assert state_after_folder_change(all_tokens, START) == expected


def test_state_after_folder_change_should_return_to_the_pushed_folder_on_popd() -> None:
    pushed = state_after_folder_change(["pushd", "a"], START)
    assert state_after_folder_change(["popd"], pushed) == START


def test_state_after_folder_change_should_not_follow_a_relative_change_from_an_unfollowed_folder() -> (
    None
):
    assert state_after_folder_change(["cd", "sub"], FolderState(None, False)) == FolderState(
        None, False
    )
