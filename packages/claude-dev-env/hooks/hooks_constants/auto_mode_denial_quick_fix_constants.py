"""Constants for the auto mode denial quick-fix advisor.

The advisor is a PermissionDenied hook. It never retries the call. It turns
each auto mode denial into a proposed fix: the rule name, a draft
``autoMode.allow`` entry, and a PowerShell 7 block that adds the entry to
``~/.claude/settings.json`` with ``"$defaults"`` kept in the list.
"""

from __future__ import annotations

__all__ = [
    "HOOK_EVENT_NAME",
    "RULE_LABEL_PATTERN",
    "UNNAMED_RULE_LABEL",
    "MAXIMUM_ACTION_SUMMARY_CHARACTERS",
    "TRUNCATION_MARKER",
    "SUMMARY_WORD_SEPARATOR",
    "ALL_COMMAND_INPUT_KEYS",
    "ALLOW_ENTRY_TEMPLATE",
    "POWERSHELL_BLOCK_TEMPLATE",
    "VERDICT_CONTEXT_TEMPLATE",
    "NO_VERDICT_CONTEXT_TEMPLATE",
    "USER_MESSAGE_TEMPLATE",
]

HOOK_EVENT_NAME = "PermissionDenied"
RULE_LABEL_PATTERN = r"\[([^\]]+)\]"
UNNAMED_RULE_LABEL = "unnamed rule"
MAXIMUM_ACTION_SUMMARY_CHARACTERS = 160
TRUNCATION_MARKER = "..."
SUMMARY_WORD_SEPARATOR = " "
ALL_COMMAND_INPUT_KEYS = ("command", "url", "file_path", "path")

ALLOW_ENTRY_TEMPLATE = (
    "{rule_label} exception: {tool_name} calls like `{action_summary}` "
    "are allowed when they serve the task the user gave."
)

POWERSHELL_BLOCK_TEMPLATE = """\
$settingsPath = Join-Path $HOME '.claude/settings.json'
New-Item -ItemType Directory -Force -Path (Split-Path $settingsPath) | Out-Null
$settings = if (Test-Path $settingsPath) { Get-Content -Raw $settingsPath | ConvertFrom-Json -AsHashtable } else { @{} }
if (-not $settings.ContainsKey('autoMode')) { $settings['autoMode'] = @{} }
$allowList = [System.Collections.Generic.List[string]]::new()
if ($settings['autoMode'].ContainsKey('allow')) { $allowList.AddRange([string[]]@($settings['autoMode']['allow'])) } else { $allowList.Add('$defaults') }
$entry = '{escaped_entry}'
if ($allowList -notcontains $entry) { $allowList.Add($entry) }
$settings['autoMode']['allow'] = $allowList.ToArray()
$settings | ConvertTo-Json -Depth 32 | Set-Content -Encoding utf8NoBOM $settingsPath
claude auto-mode config"""

VERDICT_CONTEXT_TEMPLATE = """\
=== AUTO MODE DENIAL QUICK FIX ===
Auto mode denied {tool_name} under rule [{rule_label}].
Denial reason: {denial_reason}
Denied action: {action_summary}

In your next message to the user, propose these two fixes. Do not retry and do not run the block yourself.
1. One-off: the user replies with a message that names this exact action and its target; then you retry once.
2. Lasting: the user runs this PowerShell 7 block on their machine. It adds one autoMode.allow entry to ~/.claude/settings.json and keeps "$defaults". Narrow the entry text to this action before you send it.

```powershell
{powershell_block}
```

For cloud sessions, the same entry must land in the ~/.claude/settings.json that the session's setup installs.
Read the rule wording with: claude auto-mode defaults --label '{rule_label}'"""

NO_VERDICT_CONTEXT_TEMPLATE = """\
=== AUTO MODE DENIAL QUICK FIX ===
Auto mode denied {tool_name} with no classifier verdict.
Denial reason: {denial_reason}
Denied action: {action_summary}

An autoMode.allow entry cannot clear a denial with no verdict. Tell the user the action and the reason, and ask them to run it themselves or to retry it later."""

USER_MESSAGE_TEMPLATE = (
    "Auto mode blocked {tool_name} [{rule_label}]. Claude will propose a quick fix."
)
