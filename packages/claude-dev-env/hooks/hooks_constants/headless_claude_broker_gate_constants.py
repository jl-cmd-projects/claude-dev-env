"""Constants for the headless Claude broker gate.

Holds the Claude program name and its profile-launcher prefix, the Windows
launcher suffixes stripped before the name check, the two print-mode flags, the
hook name the block log records, and the deny message that names the broker
command to run instead. It also names the environment variable a Claude Code
cloud session sets, where the gate stands aside because the session has one
account.
"""

from __future__ import annotations

__all__ = [
    "CLAUDE_PROGRAM_NAME",
    "CLAUDE_PROFILE_LAUNCHER_PREFIX",
    "ALL_WINDOWS_LAUNCHER_SUFFIXES",
    "ALL_PRINT_MODE_FLAGS",
    "PRINT_MODE_LONG_FLAG_WITH_VALUE_PREFIX",
    "GATE_HOOK_NAME",
    "BROKER_COMMAND_DENY_REASON",
    "CLOUD_SESSION_ENV_VAR",
    "CLOUD_SESSION_ENV_TRUE_VALUE",
]

CLAUDE_PROGRAM_NAME: str = "claude"
CLAUDE_PROFILE_LAUNCHER_PREFIX: str = "claude-"
ALL_WINDOWS_LAUNCHER_SUFFIXES: tuple[str, ...] = (".cmd", ".exe", ".ps1", ".bat")
ALL_PRINT_MODE_FLAGS: frozenset[str] = frozenset({"-p", "--print"})
PRINT_MODE_LONG_FLAG_WITH_VALUE_PREFIX: str = "--print="
GATE_HOOK_NAME: str = "headless_claude_broker_gate.py"
CLOUD_SESSION_ENV_VAR: str = "CLAUDE_CODE_REMOTE"
CLOUD_SESSION_ENV_TRUE_VALUE: str = "true"
BROKER_COMMAND_DENY_REASON: str = (
    "BLOCKED: Start a headless Claude session through the account broker. "
    "Run: python \"$HOME/.claude/scripts/account_broker.py\" run --product claude "
    "--report <report.json> -- <the same claude -p command>. "
    "The broker picks an account with room, sends a --resume turn to the account that owns the session, "
    "and starts the child without this session's variables. "
    "Exit 3 means no account has room: report the reset time from the report file. "
    "For a worker that edits code, use claude_account_worker.py from the second-account-workers skill."
)
