"""Tests for python_windows_invocation_gate, which stops two Windows Python failures."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import pytest

import python_windows_invocation_gate as gate


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


@pytest.fixture
def windows_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the gate read the host as Windows."""
    monkeypatch.setattr(gate, "is_windows_host", lambda: True)


@pytest.fixture
def linux_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the gate read the host as Linux."""
    monkeypatch.setattr(gate, "is_windows_host", lambda: False)


@pytest.mark.parametrize(
    "command",
    [
        "python -I script.py",
        "python3 -I -c pass",
        "py -3 -I script.py",
        "python3.12.exe -I -m json.tool data.json",
        "python -Iu script.py",
        "python -Ic pass",
        "python -I -X dev script.py",
        "python -I -X utf8=0 script.py",
        "cd repo && python -I script.py",
        "git status; python -I script.py | tee out.txt",
        "bash -c 'python -I script.py'",
    ],
)
def test_should_flag_isolated_python_without_utf8_mode(command: str) -> None:
    assert gate.runs_isolated_python_without_utf8_mode(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "python -I -X utf8 script.py",
        "python -IX utf8 script.py",
        "python -IXutf8 script.py",
        "python -X utf8 -I script.py",
        "python -I -X utf8=1 -c pass",
        "py -3 -I -X utf8 script.py",
        "python script.py -I",
        "python -c pass -I",
        "python -m pytest -I",
        "python script.py",
        "pip install -I package",
        'echo "python -I script.py"',
    ],
)
def test_should_pass_python_with_utf8_mode_or_without_isolated_mode(
    command: str,
) -> None:
    assert gate.runs_isolated_python_without_utf8_mode(command) is False


@pytest.mark.parametrize(
    "command",
    [
        'python -X utf8 -c "import json; print(\\"select 1\\")"',
        'python -c "print(\\"x\\")"',
        'py -3 -c "print(\\"x\\")"',
        'python3.exe -I -X utf8 -c "print(\\"x\\")"',
        '& python -c "print(\\"x\\")"',
        'Set-Location repo; python -c "print(\\"x\\")"',
    ],
)
def test_should_flag_a_backslash_quote_inside_a_python_code_argument(
    command: str,
) -> None:
    assert gate.has_backslash_quote_in_python_code_argument(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "python -c \"print('x')\"",
        "python -c 'print(\"x\")'",
        'python script.py "a\\"b"',
        'python -c "print(1)"; Write-Output "a\\"b"',
        'Write-Output "python -c"',
        'copy -c "a\\"b"',
    ],
)
def test_should_pass_a_python_code_argument_without_a_backslash_quote(
    command: str,
) -> None:
    assert gate.has_backslash_quote_in_python_code_argument(command) is False


def test_should_deny_isolated_python_on_windows_and_name_the_utf8_flag(
    windows_host: None,
) -> None:
    decision = json.loads(
        _stdout_from_main(
            {"tool_name": "Bash", "tool_input": {"command": "python -I s.py"}}
        )
    )
    specific_output = decision["hookSpecificOutput"]
    assert specific_output["permissionDecision"] == "deny"
    assert "python -I -X utf8" in specific_output["permissionDecisionReason"]


def test_should_stay_quiet_for_isolated_python_on_linux(linux_host: None) -> None:
    assert (
        _stdout_from_main(
            {"tool_name": "Bash", "tool_input": {"command": "python -I s.py"}}
        )
        == ""
    )


def test_should_deny_a_powershell_backslash_quote_and_name_the_here_string(
    linux_host: None,
) -> None:
    command = 'python -X utf8 -c "print(\\"select 1\\")"'
    decision = json.loads(
        _stdout_from_main(
            {"tool_name": "PowerShell", "tool_input": {"command": command}}
        )
    )
    specific_output = decision["hookSpecificOutput"]
    assert specific_output["permissionDecision"] == "deny"
    assert "here-string" in specific_output["permissionDecisionReason"]


def test_should_pass_a_backslash_quote_under_bash(windows_host: None) -> None:
    command = 'python -X utf8 -c "print(\\"select 1\\")"'
    assert (
        _stdout_from_main({"tool_name": "Bash", "tool_input": {"command": command}})
        == ""
    )


def test_should_name_both_fixes_when_a_powershell_command_has_both_failures(
    windows_host: None,
) -> None:
    command = 'python -I -c "print(\\"x\\")"'
    decision = json.loads(
        _stdout_from_main(
            {"tool_name": "PowerShell", "tool_input": {"command": command}}
        )
    )
    reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
    assert "python -I -X utf8" in reason
    assert "here-string" in reason


def test_should_stay_quiet_for_another_tool(windows_host: None) -> None:
    assert (
        _stdout_from_main(
            {"tool_name": "Write", "tool_input": {"command": "python -I s.py"}}
        )
        == ""
    )
