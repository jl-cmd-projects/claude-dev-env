"""Pin wrapper stepping and command-string unwrapping in the shared wrapper helpers."""

from __future__ import annotations

import base64

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
    "command",
    [
        "git push",
        'bash -c "git add -A && git push"; echo done',
        "bash -c \"pwsh -Command 'git push; git status'\"",
        "sudo bash -c 'gh pr list' | head",
        'echo "$(git push)"',
        "x=`git push`",
    ],
)
def test_should_return_the_segments_of_every_wrapped_command_text(command: str) -> None:
    all_segments_from_texts = [
        each_segment
        for each_text in shell_command_wrappers.all_wrapped_command_texts(command)
        for each_segment, _following_operator in (
            shell_command_wrappers.pipeline_segments_for_command(each_text)
        )
    ]
    all_segments = shell_command_wrappers.all_wrapped_command_segments(command)
    assert sorted(all_segments) == sorted(all_segments_from_texts)


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
        (["if", "git", "push"], ("git", ["push"])),
        (["then", "git", "push"], ("git", ["push"])),
        (["if", "!", "git", "push"], ("git", ["push"])),
        (["while", "git", "push"], ("git", ["push"])),
        (["command", "git", "push"], ("git", ["push"])),
        (["command", "-p", "git", "push"], ("git", ["push"])),
        (["exec", "-a", "name", "git", "push"], ("git", ["push"])),
    ],
)
def test_should_return_the_program_past_its_wrappers(
    all_segment_tokens: list[str], expected_program_and_arguments: tuple[str, list[str]]
) -> None:
    assert (
        shell_command_wrappers.segment_program_and_arguments(all_segment_tokens)
        == expected_program_and_arguments
    )


@pytest.mark.parametrize(
    ("command", "all_expected_texts"),
    [
        ('echo "$(gh pr list)"', ["gh pr list"]),
        ("x=`git push`", ["git push"]),
        ("echo $(echo $(git push))", ["echo $(git push)"]),
        ("echo $(cat <(ls))", ["cat <(ls)"]),
        ("echo \"$(printf ')'; git push)\"", ["printf ')'; git push"]),
        ('echo $(echo "$(git push)")', ['echo "$(git push)"']),
        ("x=`echo \\`git push\\``", ["echo `git push`"]),
        ("echo '$(gh pr list)'", []),
        ("echo \\$(gh pr list)", []),
        ("git push", []),
    ],
)
def test_should_return_each_command_substitution_body_outside_single_quotes(
    command: str, all_expected_texts: list[str]
) -> None:
    assert shell_command_wrappers.all_command_substitution_texts(command) == all_expected_texts


def test_should_unwrap_a_command_substitution_in_turn() -> None:
    all_command_texts = shell_command_wrappers.all_wrapped_command_texts(
        "echo \"$(bash -c 'git push')\""
    )
    assert "bash -c 'git push'" in all_command_texts
    assert "git push" in all_command_texts


_ENCODED_GIT_PUSH = base64.b64encode("git push".encode("utf-16-le")).decode()


@pytest.mark.parametrize(
    ("all_segment_tokens", "expected_inner_command"),
    [
        (["eval", "git push"], "git push"),
        (["eval", "git", "push"], "git push"),
        (["Invoke-Expression", "'git push'"], "git push"),
        (["iex", '"git push"'], "git push"),
        (["find", ".", "-exec", "git", "push", ";"], "git push"),
        (["find", ".", "-execdir", "git", "push", "{}", "+"], "git push {}"),
        (["pwsh", "-EncodedCommand", _ENCODED_GIT_PUSH], "git push"),
        (["powershell.exe", "-enc", _ENCODED_GIT_PUSH], "git push"),
        (["pwsh", "-e", _ENCODED_GIT_PUSH], "git push"),
        (["pwsh", "-ec", _ENCODED_GIT_PUSH], "git push"),
        (["pwsh", "-e", "not-base64!"], None),
        (["find", ".", "-exec", "true", ";", "-exec", "git", "push", ";"], "true ; git push"),
        (["-exec", "git", "push", "\\"], "git push \\"),
        (["pwsh", "-e", f"'{_ENCODED_GIT_PUSH[:8]} {_ENCODED_GIT_PUSH[8:]}'"], "git push"),
        (["Start-Process", "git", "-ArgumentList", "'push'"], "git push"),
        (
            ["Start-Process", "-FilePath", "git", "-ArgumentList", "push,origin", "-Wait"],
            "git push origin",
        ),
        (["saps", "git", "-WorkingDirectory", "C:/repo", "-ArgumentList", "push"], "git push"),
        (["find", ".", "-name", "x"], None),
        (["git", "push"], None),
    ],
)
def test_should_return_the_command_an_evaluating_program_runs(
    all_segment_tokens: list[str], expected_inner_command: str | None
) -> None:
    assert (
        shell_command_wrappers.evaluated_inner_command(all_segment_tokens) == expected_inner_command
    )


def test_should_unwrap_an_evaluated_command_in_turn() -> None:
    assert "git push" in shell_command_wrappers.all_wrapped_command_texts('eval "git push"')


def test_should_read_a_quoted_value_that_spans_lines() -> None:
    command = f'pwsh -EncodedCommand "{_ENCODED_GIT_PUSH[:8]}\n{_ENCODED_GIT_PUSH[8:]}"'
    assert "git push" in shell_command_wrappers.all_wrapped_command_texts(command)


def test_should_stop_unwrapping_past_the_depth_limit_without_error() -> None:
    nesting_depth = 1000
    command = "echo " + "$(" * nesting_depth + "git push" + ")" * nesting_depth
    all_command_texts = shell_command_wrappers.all_wrapped_command_texts(command)
    assert all_command_texts[0] == command
    assert len(all_command_texts) <= nesting_depth


def test_should_parse_a_repeated_inner_command_once() -> None:
    all_command_texts = shell_command_wrappers.all_wrapped_command_texts(
        'bash -c "git push"; bash -c "git push"'
    )
    assert all_command_texts.count("git push") == 1
