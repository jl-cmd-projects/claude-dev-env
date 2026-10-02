"""Pin wrapper stepping and command-string unwrapping in the shared wrapper helpers."""

from __future__ import annotations

import pytest

from hooks_constants import shell_command_wrappers


@pytest.mark.parametrize(
    ("command", "inner_command"),
    [
        ('pwsh -NoProfile -Command "git add -A; git push"', "git add -A; git push"),
        ("pwsh -Command git push origin HEAD; echo done", "git push origin HEAD"),
        ('bash -c "git push"', "git push"),
        ("sh -c 'git commit -F m.txt'", "git commit -F m.txt"),
        ("bash -lc 'git push'", "git push"),
        ("sudo bash -c 'git push'", "git push"),
        ("bash -c \"pwsh -Command 'git push'\"", "git push"),
    ],
)
def test_should_return_the_command_string_a_shell_wrapper_runs(
    command: str, inner_command: str
) -> None:
    all_command_texts = shell_command_wrappers.all_wrapped_command_texts(command)
    assert all_command_texts[0] == command
    assert inner_command in all_command_texts


def test_should_return_only_the_command_when_no_wrapper_runs() -> None:
    assert shell_command_wrappers.all_wrapped_command_texts("git push") == ["git push"]


@pytest.mark.parametrize(
    ("all_segment_tokens", "expected_program_and_arguments"),
    [
        (["git", "push"], ("git", ["push"])),
        (["sudo", "git", "push"], ("git", ["push"])),
        (["sudo", "-u", "root", "git", "push"], ("git", ["push"])),
        (["env", "VAR=x", "git", "push"], ("git", ["push"])),
        (["xargs", "git", "push"], ("git", ["push"])),
        (["xargs", "-r", "rm"], ("rm", [])),
        (["xargs", "-I", "{}", "rm", "{}"], ("rm", ["{}"])),
        (["xargs", "-n", "1", "git", "push"], ("git", ["push"])),
        (["env", "-u", "HOME", "git", "push"], ("git", ["push"])),
        (["env", "-i", "VAR=x", "git", "push"], ("git", ["push"])),
        (["timeout", "--signal", "KILL", "5", "git", "push"], ("git", ["push"])),
        (["timeout", "--signal=KILL", "5", "git", "push"], ("git", ["push"])),
        (["sudo", "-nu", "ci", "env", "-u", "HOME", "git", "push"], ("git", ["push"])),
        (["time", "sudo", "git", "push"], ("git", ["push"])),
        (["'/usr/bin/git'", "push"], ("git", ["push"])),
        (["VAR=x"], ("", [])),
    ],
)
def test_should_return_the_program_past_its_wrappers(
    all_segment_tokens: list[str], expected_program_and_arguments: tuple[str, list[str]]
) -> None:
    assert (
        shell_command_wrappers.segment_program_and_arguments(all_segment_tokens)
        == expected_program_and_arguments
    )
