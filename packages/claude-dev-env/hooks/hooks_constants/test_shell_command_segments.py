"""Pin git global-option parsing in the shared segment helpers."""

from __future__ import annotations

import pytest

from hooks_constants import shell_command_segments


@pytest.mark.parametrize(
    ("all_arguments", "all_expected_tokens"),
    [
        (["push", "origin", "HEAD"], ["push", "origin", "HEAD"]),
        (["-C", "/repo", "push"], ["push"]),
        (["-c", "user.name=x", "commit", "-F", "m.txt"], ["commit", "-F", "m.txt"]),
        (["--git-dir=/repo/.git", "push"], ["push"]),
        (["--git-dir", "/repo/.git", "push"], ["push"]),
        (["--work-tree", "/repo", "commit"], ["commit"]),
        (["--namespace", "n", "push"], ["push"]),
        (["--no-pager", "log"], ["log"]),
        (["stash", "push", "-u"], ["stash", "push", "-u"]),
        (["log", "--grep", "push"], ["log", "--grep", "push"]),
        (["--version"], []),
    ],
)
def test_should_return_the_subcommand_tokens_past_global_options(
    all_arguments: list[str], all_expected_tokens: list[str]
) -> None:
    assert shell_command_segments.git_subcommand_tokens(all_arguments) == all_expected_tokens
