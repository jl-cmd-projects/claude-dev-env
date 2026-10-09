"""Tests for the Bash and PowerShell dispatcher hosted-hook roster."""

from pathlib import Path
from runpy import run_path

ALL_CONSTANT_BINDINGS = run_path(
    str(Path(__file__).with_name("bash_pre_tool_use_dispatcher_constants.py"))
)
ALL_BASH_HOSTED_HOOK_ENTRIES = ALL_CONSTANT_BINDINGS["ALL_BASH_HOSTED_HOOK_ENTRIES"]
ALL_BASH_ONLY_TOOL_NAMES = ALL_CONSTANT_BINDINGS["ALL_BASH_ONLY_TOOL_NAMES"]
ALL_BASH_AND_POWERSHELL_TOOL_NAMES = ALL_CONSTANT_BINDINGS["ALL_BASH_AND_POWERSHELL_TOOL_NAMES"]
BashHostedHookEntry = ALL_CONSTANT_BINDINGS["BashHostedHookEntry"]


def test_roster_hosts_the_three_gates_and_hands_two_to_the_shell_guards_mod() -> None:
    assert ALL_BASH_HOSTED_HOOK_ENTRIES == (
        BashHostedHookEntry(
            script_relative_path="blocking/msys_rev_path_rewriter.py",
            applicable_tool_names=ALL_BASH_ONLY_TOOL_NAMES,
        ),
        BashHostedHookEntry(
            script_relative_path="blocking/headless_claude_broker_gate.py",
            applicable_tool_names=ALL_BASH_AND_POWERSHELL_TOOL_NAMES,
            replaced_by_plugin_name="shell-guards",
        ),
        BashHostedHookEntry(
            script_relative_path="blocking/gh_global_account_switch_gate.py",
            applicable_tool_names=ALL_BASH_AND_POWERSHELL_TOOL_NAMES,
            replaced_by_plugin_name="shell-guards",
        ),
    )
