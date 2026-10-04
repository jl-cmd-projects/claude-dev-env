"""Constants for the gate that keeps agents from changing the global gh account.

Holds the GitHub CLI program name, the ``gh auth`` command paths that change the
account every session on the machine uses and their word count, the hook name
the block log records, and the deny message that names the per-command token
form to run instead.
"""

from __future__ import annotations

__all__ = [
    "GH_PROGRAM_NAME",
    "GH_COMMAND_PATH_LENGTH",
    "ALL_GLOBAL_ACCOUNT_CHANGING_COMMAND_PATHS",
    "GATE_HOOK_NAME",
    "GLOBAL_ACCOUNT_CHANGE_DENY_REASON",
]

GH_PROGRAM_NAME: str = "gh"
GH_COMMAND_PATH_LENGTH: int = 2
ALL_GLOBAL_ACCOUNT_CHANGING_COMMAND_PATHS: frozenset[tuple[str, ...]] = frozenset(
    {("auth", "switch"), ("auth", "login"), ("auth", "logout")}
)
GATE_HOOK_NAME: str = "gh_global_account_switch_gate.py"
GLOBAL_ACCOUNT_CHANGE_DENY_REASON: str = (
    "BLOCKED: gh auth switch, login, and logout change the active GitHub CLI account "
    "for every session on this machine, so other running agents lose access. "
    "Scope the other signed-in account to one command instead. "
    "Bash: GH_TOKEN=$(gh auth token -u <account>) gh <command>. "
    "PowerShell: $env:GH_TOKEN = gh auth token -u <account>; gh <command>; Remove-Item Env:GH_TOKEN. "
    "Run gh auth status to list the signed-in accounts. "
    "Signing an account in or out is a step for the user to run."
)
