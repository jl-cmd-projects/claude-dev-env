"""Pin which shell commands the mutation check reads as writes."""

from __future__ import annotations

import pytest

from hooks_constants.shell_command_mutation import is_mutating_shell_command


@pytest.mark.parametrize(
    "command",
    [
        "sudo git push",
        'bash -c "git commit -F m.txt"',
        "pwsh -Command git push origin HEAD; echo done",
        "gh api repos/o/r/issues -f title=x",
        "Get-ChildItem | ForEach-Object { Remove-Item $_ }",
        "echo hi > notes.txt",
    ],
)
def test_should_read_a_write_as_mutating(command: str) -> None:
    assert is_mutating_shell_command(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "rg 'gh pr merge' docs",
        "rg 'Remove-Item' docs",
        'grep "a|cp b" notes.md',
        "gh api -X GET search/issues -f q=x",
        'bash -c "git status"',
        "git log --format='%h > %s'",
    ],
)
def test_should_read_a_check_as_not_mutating(command: str) -> None:
    assert is_mutating_shell_command(command) is False
