"""Tests for gh_global_account_switch_gate, which keeps the global gh account fixed."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import pytest

import gh_global_account_switch_gate as gate


def _stdout_from_main(payload: dict[str, object]) -> str:
    """Return what main() wrote to stdout for one hook payload."""
    captured_stdout = StringIO()
    with (
        patch("sys.stdin", StringIO(json.dumps(payload))),
        patch("sys.stdout", captured_stdout),
        patch.object(gate, "log_hook_block"),
    ):
        gate.main()
    return captured_stdout.getvalue()


@pytest.mark.parametrize(
    "command",
    [
        "gh auth switch",
        "gh auth switch -u account-a",
        "gh auth login",
        "gh auth login --with-token",
        "gh auth logout -u account-b",
        "gh.exe auth switch -u account-b",
        "cd repo && gh auth switch -u account-a",
        "gh auth status; gh auth switch -u account-a",
        "gh auth status || gh auth login",
        'bash -c "gh auth switch -u account-a"',
        'pwsh -Command "gh auth logout"',
        "& gh auth switch",
        "sudo gh auth switch --user account-b",
    ],
)
def test_global_account_change_is_detected(command: str) -> None:
    assert gate.changes_global_gh_account(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "gh auth status",
        "gh auth status --active",
        "gh auth token -u account-a",
        "GH_TOKEN=$(gh auth token -u account-a) gh repo list",
        "$env:GH_TOKEN = gh auth token -u account-a; gh repo list; Remove-Item Env:GH_TOKEN",
        "gh pr view 12",
        "gh api user",
        "gh",
        'git commit -m "never call gh auth switch"',
        'echo "gh auth switch"',
        'grep -rn "gh auth login" docs',
        "git switch main",
    ],
)
def test_read_only_and_unrelated_commands_pass(command: str) -> None:
    assert gate.changes_global_gh_account(command) is False


def test_bash_payload_with_switch_is_denied_with_the_scoped_token_forms() -> None:
    decision = json.loads(
        _stdout_from_main(
            {"tool_name": "Bash", "tool_input": {"command": "gh auth switch -u account-a"}}
        )
    )
    specific_output = decision["hookSpecificOutput"]
    assert specific_output["permissionDecision"] == "deny"
    reason = specific_output["permissionDecisionReason"]
    assert "GH_TOKEN=$(gh auth token -u <account>) gh <command>" in reason
    assert (
        "$env:GH_TOKEN = gh auth token -u <account>; gh <command>; Remove-Item Env:GH_TOKEN"
        in reason
    )


def test_powershell_payload_with_logout_is_denied() -> None:
    decision = json.loads(
        _stdout_from_main({"tool_name": "PowerShell", "tool_input": {"command": "gh auth logout"}})
    )
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_scoped_token_payload_emits_nothing() -> None:
    scoped_command = "GH_TOKEN=$(gh auth token -u account-b) gh repo list"
    assert _stdout_from_main({"tool_name": "Bash", "tool_input": {"command": scoped_command}}) == ""


def test_other_tool_payload_emits_nothing() -> None:
    assert (
        _stdout_from_main({"tool_name": "Write", "tool_input": {"command": "gh auth switch"}}) == ""
    )
