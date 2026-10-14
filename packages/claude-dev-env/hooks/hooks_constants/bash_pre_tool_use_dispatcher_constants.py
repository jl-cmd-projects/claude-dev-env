"""Constants for the Bash and PowerShell PreToolUse dispatcher.

Holds the permission outcomes, the two tool-name sets, and the ordered hosted-hook
roster with each hook's applicable-tool set. The dispatcher imports these to
select and run the hooks that a Bash or PowerShell tool call fires.
"""

from __future__ import annotations

from dataclasses import dataclass

from hooks_constants.mod_handoff_constants import SHELL_GUARDS_PLUGIN_NAME

__all__ = [
    "DENY_DECISION",
    "ASK_DECISION",
    "ALLOW_DECISION",
    "HOOK_EVENT_NAME",
    "REASON_JOIN_SEPARATOR",
    "CONTEXT_JOIN_SEPARATOR",
    "BASH_TOOL_NAME",
    "POWERSHELL_TOOL_NAME",
    "ALL_BASH_ONLY_TOOL_NAMES",
    "ALL_BASH_AND_POWERSHELL_TOOL_NAMES",
    "BashHostedHookEntry",
    "ALL_BASH_HOSTED_HOOK_ENTRIES",
]

DENY_DECISION = "deny"
ASK_DECISION = "ask"
ALLOW_DECISION = "allow"
HOOK_EVENT_NAME = "PreToolUse"
REASON_JOIN_SEPARATOR = " | "
CONTEXT_JOIN_SEPARATOR = "\n"

BASH_TOOL_NAME = "Bash"
POWERSHELL_TOOL_NAME = "PowerShell"

ALL_BASH_ONLY_TOOL_NAMES: frozenset[str] = frozenset({BASH_TOOL_NAME})
ALL_BASH_AND_POWERSHELL_TOOL_NAMES: frozenset[str] = frozenset(
    {BASH_TOOL_NAME, POWERSHELL_TOOL_NAME}
)


@dataclass(frozen=True)
class BashHostedHookEntry:
    """A single hosted hook with the tool names it applies to.

    Attributes:
        script_relative_path: Hook path relative to the hooks/ directory.
        applicable_tool_names: Tool names this hook runs for. The dispatcher
            skips the hook when the payload's tool is not in this set.
        replaced_by_plugin_name: The plugin whose mod holds this hook. The
            dispatcher skips the hook while that plugin is on, so a session
            runs the hook or the mod and never both.
    """

    script_relative_path: str
    applicable_tool_names: frozenset[str]
    replaced_by_plugin_name: str | None = None


ALL_BASH_HOSTED_HOOK_ENTRIES: tuple[BashHostedHookEntry, ...] = (
    BashHostedHookEntry(
        script_relative_path="blocking/msys_rev_path_rewriter.py",
        applicable_tool_names=ALL_BASH_ONLY_TOOL_NAMES,
    ),
    BashHostedHookEntry(
        script_relative_path="blocking/headless_claude_broker_gate.py",
        applicable_tool_names=ALL_BASH_AND_POWERSHELL_TOOL_NAMES,
        replaced_by_plugin_name=SHELL_GUARDS_PLUGIN_NAME,
    ),
    BashHostedHookEntry(
        script_relative_path="blocking/gh_global_account_switch_gate.py",
        applicable_tool_names=ALL_BASH_AND_POWERSHELL_TOOL_NAMES,
        replaced_by_plugin_name=SHELL_GUARDS_PLUGIN_NAME,
    ),
    BashHostedHookEntry(
        script_relative_path="blocking/cloud_graphql_gate.py",
        applicable_tool_names=ALL_BASH_AND_POWERSHELL_TOOL_NAMES,
    ),
)
