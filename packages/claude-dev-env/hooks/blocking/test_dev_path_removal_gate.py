"""Tests for dev_path_removal_gate, which stops a Bash command from removing a file under /dev."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

import dev_path_removal_gate as gate


def _bash_payload(command: str) -> dict[str, object]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _stdout_from_main(payload: dict[str, object]) -> str:
    captured_stdout = StringIO()
    with (
        patch("sys.stdin", StringIO(json.dumps(payload))),
        patch("sys.stdout", captured_stdout),
        patch.object(gate, "log_hook_block"),
    ):
        gate.main()
    return captured_stdout.getvalue()


@pytest.mark.parametrize(
    "path_operand",
    ["/dev/null", "/dev/", "/dev", "//dev//null", "/tmp/../dev/null", "/dev/n*"],
)
def test_should_treat_a_path_under_dev_as_a_dev_path(path_operand: str) -> None:
    assert gate.is_dev_path(path_operand) is True


@pytest.mark.parametrize(
    "path_operand",
    ["/devices/null", "/dev_backup/null", "/tmp/dev/null", "notes.txt"],
)
def test_should_not_treat_a_path_outside_dev_as_a_dev_path(path_operand: str) -> None:
    assert gate.is_dev_path(path_operand) is False


@pytest.mark.parametrize(
    "all_segment_tokens",
    [
        ["rm", "-f", "/dev/null"],
        ["unlink", "/dev/null"],
        ["mv", "/dev/null", "/tmp/saved"],
        ["mv", "notes.txt", "/dev/null"],
        ["shred", "-u", "/dev/null"],
        ["truncate", "-s", "0", "/dev/null"],
        ["rm", "-f", "/dev/null", "2", ">&", "1"],
        ["rm", "-f", "/dev/null", ">", "/tmp/log"],
        ["mv", "--target-directory=/dev", "notes.txt"],
        ["mv", "notes.txt", "--target-directory=/dev"],
        ["mv", "-t/dev", "notes.txt"],
        ["mv", "-ft/dev", "notes.txt"],
    ],
)
def test_should_flag_a_removal_segment_with_a_dev_operand(all_segment_tokens: list[str]) -> None:
    assert gate.segment_removes_dev_path(all_segment_tokens) is True


@pytest.mark.parametrize(
    "all_segment_tokens",
    [
        ["cat", "/dev/null"],
        ["echo", "x", ">", "/dev/null"],
        ["rm", "notes.txt", ">", "/dev/null"],
        ["rm", "notes.txt", "2", ">", "/dev/null"],
        ["rm", "notes.txt", "&>", "/dev/null"],
        ["rm", "-f", "notes.txt"],
        ["rm", "-f", "/devices/null"],
        ["mv", "--target-directory=/tmp/out", "notes.txt"],
        ["mv", "-t/tmp/out", "notes.txt"],
    ],
)
def test_should_pass_a_segment_that_reads_or_only_redirects_into_dev(
    all_segment_tokens: list[str],
) -> None:
    assert gate.segment_removes_dev_path(all_segment_tokens) is False


@pytest.mark.parametrize(
    "command",
    [
        "rm -f /dev/null",
        "rm -rf /dev/null",
        "unlink /dev/null",
        "mv /dev/null /tmp/saved",
        "shred -u /dev/null",
        "truncate -s 0 /dev/null",
        "rm -- /dev/null",
        'rm -f "/dev/null"',
        "/bin/rm -f /dev/null",
        "sudo rm -f /dev/null",
        "cd repo && rm -f /dev/null",
        "echo x; rm -f /dev/null",
        "cat notes | head; rm -f /dev/null",
        "rm -f /dev/null 2>&1",
        "rm /tmp/../dev/null",
        "bash -c 'rm -f /dev/null'",
        "mv notes.txt --target-directory=/dev",
        "mv -t/dev notes.txt",
    ],
)
def test_should_flag_a_command_that_removes_a_dev_path(command: str) -> None:
    assert gate.runs_dev_path_removal(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "cat notes | head",
        "echo x > /dev/null",
        "rm notes.txt > /dev/null",
        "rm notes.txt 2>/dev/null",
        "cat /dev/null",
        "ls /dev/null",
        "rm -f notes.txt",
    ],
)
def test_should_pass_a_command_that_does_not_remove_a_dev_path(command: str) -> None:
    assert gate.runs_dev_path_removal(command) is False


def test_should_deny_a_bash_removal_of_dev_null_with_the_redirect_fix() -> None:
    decision = json.loads(_stdout_from_main(_bash_payload("rm -f /dev/null")))
    hook_specific = decision["hookSpecificOutput"]
    assert hook_specific["hookEventName"] == "PreToolUse"
    assert hook_specific["permissionDecision"] == "deny"
    assert "> /dev/null" in hook_specific["permissionDecisionReason"]


def test_should_stay_quiet_for_a_bash_redirect_into_dev_null() -> None:
    assert _stdout_from_main(_bash_payload("echo x > /dev/null")) == ""


def test_should_stay_quiet_for_the_powershell_tool() -> None:
    payload = {"tool_name": "PowerShell", "tool_input": {"command": "rm -f /dev/null"}}
    assert _stdout_from_main(payload) == ""


def test_should_log_the_block_with_the_gate_name_and_command() -> None:
    mock_log_hook_block = MagicMock()
    with (
        patch("sys.stdin", StringIO(json.dumps(_bash_payload("rm -f /dev/null")))),
        patch("sys.stdout", StringIO()),
        patch.object(gate, "log_hook_block", mock_log_hook_block),
    ):
        gate.main()
    mock_log_hook_block.assert_called_once()
    logged_arguments = mock_log_hook_block.call_args.args
    assert logged_arguments[0] == "dev_path_removal_gate"
    assert logged_arguments[3] == "Bash"
    assert logged_arguments[4] == "rm -f /dev/null"
