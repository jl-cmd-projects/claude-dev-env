"""Tests for headless_claude_broker_gate, which sends headless Claude through the broker."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import pytest

import headless_claude_broker_gate as gate

BROKER_COMMAND = (
    'python "$HOME/.claude/scripts/account_broker.py" run --product claude --report r.json '
    '-- claude -p "task" --output-format stream-json --verbose'
)


def _stdout_from_main(payload: dict[str, object]) -> str:
    """Return what main() wrote to stdout for one hook payload."""
    captured_stdout = StringIO()
    with patch("sys.stdin", StringIO(json.dumps(payload))), patch("sys.stdout", captured_stdout), patch.object(
        gate, "log_hook_block"
    ):
        gate.main()
    return captured_stdout.getvalue()


@pytest.mark.parametrize(
    "command",
    [
        'claude -p "fix the test"',
        'claude --print "fix the test"',
        'claude -p --resume abc-123 "next turn" --output-format stream-json --verbose',
        'cd /repo && claude -p "task"',
        'env -u CLAUDECODE claude -p "task"',
        'CLAUDE_CONFIG_DIR=/x claude -p "task"',
        'claude-ev -p "task"',
        "claude-ev.cmd -p task",
        "/opt/node22/bin/claude -p task",
        "& claude -p 'task'",
        "timeout 600 claude -p task > out.json",
        'bash -c "claude -p task"',
        "sudo -u builder claude -p task",
    ],
)
def test_headless_claude_without_the_broker_is_detected(command: str) -> None:
    assert gate.starts_unbrokered_headless_claude(command) is True


@pytest.mark.parametrize(
    "command",
    [
        BROKER_COMMAND,
        "python ~/.claude/scripts/claude_account_worker.py --prompt-file b.md --report-file r.json",
        "claude plugin eval suite.json",
        "claude --version",
        "claude",
        'grep -rn "claude -p" docs',
        'echo "run claude -p later"',
        "python claude_account_worker.py -p x",
        "git -C claude-dev-env log -p",
        "mkdir -p claude-dev-env",
        "cp -rp claude-dev-env /backup -p",
    ],
)
def test_broker_starts_and_other_claude_commands_pass(command: str) -> None:
    assert gate.starts_unbrokered_headless_claude(command) is False


def test_bash_payload_with_bare_headless_claude_is_denied_with_the_broker_command() -> None:
    decision = json.loads(_stdout_from_main({"tool_name": "Bash", "tool_input": {"command": 'claude -p "task"'}}))
    specific_output = decision["hookSpecificOutput"]
    assert specific_output["permissionDecision"] == "deny"
    assert "account_broker.py\" run --product claude" in specific_output["permissionDecisionReason"]


def test_powershell_payload_with_profile_launcher_is_denied() -> None:
    decision = json.loads(_stdout_from_main({"tool_name": "PowerShell", "tool_input": {"command": "claude-ev -p task"}}))
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_broker_command_payload_emits_nothing() -> None:
    assert _stdout_from_main({"tool_name": "Bash", "tool_input": {"command": BROKER_COMMAND}}) == ""


def test_other_tool_payload_emits_nothing() -> None:
    assert _stdout_from_main({"tool_name": "Write", "tool_input": {"command": 'claude -p "task"'}}) == ""
