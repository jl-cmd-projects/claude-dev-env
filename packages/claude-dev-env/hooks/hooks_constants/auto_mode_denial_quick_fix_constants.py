"""Constants for the auto mode denial quick-fix advisor.

The advisor is a PermissionDenied hook. It never retries the call. It turns
each auto mode denial into a proposed fix: the rule name, a draft
``autoMode.allow`` entry, and a PowerShell 7 block that adds the entry to
``~/.claude/settings.json`` with ``"$defaults"`` kept in the list.
"""

from __future__ import annotations

__all__ = [
    "HOOK_EVENT_NAME",
    "ALL_NO_VERDICT_REASON_PREFIXES",
    "UNEXPLAINED_VERDICT_REASON_PREFIX",
    "UNEXPLAINED_RULE_LABEL",
    "BRACKETED_LABEL_PATTERN",
    "BARE_LABEL_PATTERN",
    "SENTENCE_END_PATTERN",
    "RULE_LABEL_DISALLOWED_CHARACTER_PATTERN",
    "ALL_POWERSHELL_SINGLE_QUOTE_CHARACTERS",
    "MAXIMUM_PROSE_RULE_NAME_CHARACTERS",
    "UNNAMED_RULE_LABEL",
    "MAXIMUM_ACTION_SUMMARY_CHARACTERS",
    "TRUNCATION_MARKER",
    "SUMMARY_WORD_SEPARATOR",
    "ALL_COMMAND_INPUT_KEYS",
    "ALLOW_ENTRY_TEMPLATE",
    "POWERSHELL_BLOCK_TEMPLATE",
    "LABELLED_RULE_WORDING_COMMAND_TEMPLATE",
    "UNLABELLED_RULE_WORDING_COMMAND",
    "LABELLED_RULE_WORDING_LINE_TEMPLATE",
    "UNLABELLED_RULE_WORDING_LINE_TEMPLATE",
    "VERDICT_CONTEXT_TEMPLATE",
    "NO_VERDICT_CONTEXT_TEMPLATE",
    "USER_MESSAGE_TEMPLATE",
    "CLASSIFIER_REASON_PREFIX_PATTERN",
    "QUESTION_CONTEXT_TEMPLATE",
    "DEFAULT_TOOL_NAME",
]

HOOK_EVENT_NAME = "PermissionDenied"
DEFAULT_TOOL_NAME = "tool"
ALL_NO_VERDICT_REASON_PREFIXES = (
    "auto mode could not evaluate this action",
    "classifier unavailable",
)
UNEXPLAINED_VERDICT_REASON_PREFIX = "the server-side auto mode classifier judged this action dangerous"
UNEXPLAINED_RULE_LABEL = "Unexplained"
BRACKETED_LABEL_PATTERN = r"^\s*\[(?P<label>[^\]]+)\]\s*(?P<prose>.*)$"
BARE_LABEL_PATTERN = (
    r"^\s*(?P<label>[A-Z][\w-]*(?:\s+[A-Z][\w-]*)+)\s*(?:[,:;.]|\s-\s|$)\s*(?P<prose>.*)$"
)
SENTENCE_END_PATTERN = r"[.!?](?:\s+|$)"
RULE_LABEL_DISALLOWED_CHARACTER_PATTERN = r"[^A-Za-z0-9 _/-]"
ALL_POWERSHELL_SINGLE_QUOTE_CHARACTERS = ("'", "\u2018", "\u2019", "\u201a", "\u201b")
MAXIMUM_PROSE_RULE_NAME_CHARACTERS = 80
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
{rule_wording_line}"""

LABELLED_RULE_WORDING_COMMAND_TEMPLATE = "claude auto-mode defaults --label '{escaped_label}'"
UNLABELLED_RULE_WORDING_COMMAND = "claude auto-mode defaults"
LABELLED_RULE_WORDING_LINE_TEMPLATE = "Read the rule wording with: {command}"
UNLABELLED_RULE_WORDING_LINE_TEMPLATE = "Find the matching rule with: {command}"

NO_VERDICT_CONTEXT_TEMPLATE = """\
=== AUTO MODE DENIAL QUICK FIX ===
Auto mode denied {tool_name} with no classifier verdict.
Denial reason: {denial_reason}
Denied action: {action_summary}

An autoMode.allow entry cannot clear a denial with no verdict. Tell the user the action and the reason, and ask them to run it themselves or to retry it later."""

USER_MESSAGE_TEMPLATE = (
    "Auto mode blocked {tool_name} [{rule_label}]. Claude will propose a quick fix."
)

CLASSIFIER_REASON_PREFIX_PATTERN = (
    r"^\s*(?:Permission for this action was denied by the Claude Code auto mode classifier\.\s*)?"
    r"(?:Reason:\s*)?"
)

QUESTION_CONTEXT_TEMPLATE = """

=== AUTO MODE QUESTION ===
Before you end the turn, ask the user this question with one AskUserQuestion call. Copy the question word for word, use the header `Auto mode`, and give the options `Keep refusing` and `Allow it`:
{question}
On Allow it, follow {playbook_path}: retry the step once and add one allow rule for this kind of step. On Keep refusing, go on with other work."""
