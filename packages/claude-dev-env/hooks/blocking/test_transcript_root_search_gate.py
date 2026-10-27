"""Tests for transcript_root_search_gate, which stops walks over a Claude transcript root."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import pytest

import transcript_root_search_gate as gate

_OVERDUE_SEARCH_COMMAND = (
    '$p="C:/Users/dev/.claude-profiles/work/projects"; '
    "Get-ChildItem $p -Recurse -File -Filter *.jsonl | "
    "Where-Object LastWriteTime -gt (Get-Date).AddDays(-5) | "
    "Select-String -Pattern 'lock-clock-digit-port' -List"
)
_SCOPED_LISTING_COMMAND = (
    '$p="C:/Users/dev/.claude-profiles/work/projects"; '
    'Get-ChildItem $p -Directory -Filter "*01WUQeBG*"'
)


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


def _shell_payload(tool_name: str, command: str) -> dict[str, object]:
    return {"tool_name": tool_name, "tool_input": {"command": command}, "cwd": "C:/dev/repo"}


def _is_denied(stdout_text: str) -> bool:
    if not stdout_text.strip():
        return False
    return json.loads(stdout_text)["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize(
    "command",
    [
        _OVERDUE_SEARCH_COMMAND,
        r"Get-ChildItem C:\Users\dev\.claude\projects -Recurse -Filter *.jsonl",
        r'gci -Path "$env:USERPROFILE\.claude\projects" -Recurse:$true',
        r"dir C:\Users\dev\.claude\projects -Depth 3",
        "$p = '~/.claude/projects'; Get-ChildItem -LiteralPath $p -Recurse",
        r'Select-String -Path "$HOME\.claude\projects\*\*.jsonl" -Pattern needle',
        "Get-ChildItem ~/.claude/projects/* -Recurse",
    ],
)
def test_should_deny_a_powershell_walk_over_a_transcript_root(command: str) -> None:
    assert _is_denied(_stdout_from_main(_shell_payload("PowerShell", command)))


@pytest.mark.parametrize(
    "command",
    [
        "find ~/.claude/projects -name '*.jsonl'",
        "find -L /c/Users/dev/.claude/projects/ -type f",
        "grep -rn needle ~/.claude-profiles/work/projects/",
        "grep -Rl needle /home/u/.claude/projects",
        "rg needle /c/Users/dev/.claude-work/projects",
        "ls -laR ~/.claude/projects",
        'p=~/.claude/projects; grep -rl needle "$p"',
        'export ROOT="$HOME/.claude/projects" && find "${ROOT}" -newer x',
        "bash -c 'find ~/.claude/projects -name x'",
        "grep needle ~/.claude/projects/*/*.jsonl",
    ],
)
def test_should_deny_a_bash_walk_over_a_transcript_root(command: str) -> None:
    assert _is_denied(_stdout_from_main(_shell_payload("Bash", command)))


@pytest.mark.parametrize(
    ("tool_name", "command"),
    [
        ("PowerShell", _SCOPED_LISTING_COMMAND),
        ("PowerShell", r"Get-ChildItem C:\Users\dev\.claude\projects"),
        ("PowerShell", r"Get-ChildItem C:\Users\dev\.claude\projects\*01WUQeBG*"),
        ("PowerShell", r"Get-ChildItem C:\Users\dev\.claude\projects\C--dev-repo -Recurse"),
        ("PowerShell", "Select-String -Path ~/.claude/projects/C--dev-repo/a.jsonl -Pattern x"),
        ("PowerShell", r"dir C:\Users\dev\.claude\projects -Depth 0"),
        ("Bash", "find ~/.claude/projects -maxdepth 1 -name '*01WUQeBG*'"),
        ("Bash", "grep -rn needle ~/.claude/projects/C--dev-repo"),
        ("Bash", "grep -rn needle ~/.claude/skills"),
        ("Bash", "grep -n projects notes.txt"),
        ("Bash", "find . -name projects"),
        ("Bash", "ls -la ~/.claude/projects"),
        ("Bash", "rg needle packages/claude-dev-env"),
    ],
)
def test_should_allow_a_scoped_command(tool_name: str, command: str) -> None:
    assert _stdout_from_main(_shell_payload(tool_name, command)) == ""


@pytest.mark.parametrize(
    "tool_input",
    [
        {"pattern": "needle", "path": "C:/Users/dev/.claude/projects"},
        {"pattern": "needle", "path": "C:\\Users\\dev\\.claude-profiles\\work\\projects\\"},
        {"pattern": "needle", "path": "/home/u/.claude-work/projects", "glob": "*.jsonl"},
    ],
)
def test_should_deny_a_grep_tool_search_over_a_transcript_root(
    tool_input: dict[str, str],
) -> None:
    payload = {"tool_name": "Grep", "tool_input": tool_input, "cwd": "C:/dev/repo"}
    assert _is_denied(_stdout_from_main(payload))


def test_should_deny_a_grep_tool_search_that_starts_at_a_transcript_root_cwd() -> None:
    payload = {
        "tool_name": "Grep",
        "tool_input": {"pattern": "needle"},
        "cwd": "C:/Users/dev/.claude/projects",
    }
    assert _is_denied(_stdout_from_main(payload))


def test_should_allow_a_grep_tool_search_inside_one_project_folder() -> None:
    payload = {
        "tool_name": "Grep",
        "tool_input": {"pattern": "needle", "path": "C:/Users/dev/.claude/projects/C--dev-repo"},
        "cwd": "C:/dev/repo",
    }
    assert _stdout_from_main(payload) == ""


@pytest.mark.parametrize(
    "tool_input",
    [
        {"pattern": "**/*.jsonl", "path": "C:/Users/dev/.claude/projects"},
        {"pattern": "C:/Users/dev/.claude/projects/**/*.jsonl"},
        {"pattern": "*/*.jsonl", "path": "/home/u/.claude-profiles/work/projects"},
        {"pattern": "**", "path": "/home/u/.claude/projects"},
    ],
)
def test_should_deny_a_glob_tool_walk_over_a_transcript_root(
    tool_input: dict[str, str],
) -> None:
    payload = {"tool_name": "Glob", "tool_input": tool_input, "cwd": "C:/dev/repo"}
    assert _is_denied(_stdout_from_main(payload))


@pytest.mark.parametrize(
    "tool_input",
    [
        {"pattern": "*01WUQeBG*", "path": "C:/Users/dev/.claude/projects"},
        {"pattern": "*01WUQeBG*/*.jsonl", "path": "C:/Users/dev/.claude/projects"},
        {"pattern": "**/*.py", "path": "C:/dev/repo"},
    ],
)
def test_should_allow_a_glob_tool_listing_by_name(tool_input: dict[str, str]) -> None:
    payload = {"tool_name": "Glob", "tool_input": tool_input, "cwd": "C:/dev/repo"}
    assert _stdout_from_main(payload) == ""


def test_should_name_the_list_then_read_fix_in_the_deny_reason() -> None:
    stdout_text = _stdout_from_main(_shell_payload("PowerShell", _OVERDUE_SEARCH_COMMAND))
    deny_reason = json.loads(stdout_text)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "-Directory -Filter" in deny_reason
    assert "C:/Users/dev/.claude-profiles/work/projects" in deny_reason
    assert "read the one transcript" in deny_reason


def test_should_stay_quiet_for_another_tool() -> None:
    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": "C:/Users/dev/.claude/projects"},
        "cwd": "C:/dev/repo",
    }
    assert _stdout_from_main(payload) == ""
