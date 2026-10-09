"""Constants for the auto mode denial approval advisor.

The advisor turns each auto mode denial into one plain-language approval
phrase and a task card request. The task card asks for a pull request that
adds an ``autoMode.allow`` rule to the claude-dev-env settings file, which
the installer copies to ``~/.claude/settings.json``.
"""

from __future__ import annotations

from typing import NamedTuple

__all__ = [
    "DENIAL_EVENT_NAME",
    "ALL_STOP_EVENT_NAMES",
    "STATE_DIRECTORY_NAME",
    "MAIN_AGENT_KEY",
    "UNSAFE_FILE_NAME_CHARACTERS",
    "RULE_LABEL_PATTERN",
    "ALL_NO_VERDICT_REASON_PREFIXES",
    "MAXIMUM_ACTION_SUMMARY_CHARACTERS",
    "TRUNCATION_MARKER",
    "SUMMARY_WORD_SEPARATOR",
    "SUMMARY_HEAD_SHARE_DIVISOR",
    "ALL_COMMAND_INPUT_KEYS",
    "MAIN_ACTOR",
    "SUBAGENT_ACTOR",
    "ProgramGloss",
    "ALL_PROGRAM_GLOSSES",
    "ALL_TOOL_GLOSSES",
    "MCP_TOOL_PREFIX",
    "MCP_NAME_SEPARATOR",
    "MCP_GLOSS_TEMPLATE",
    "DEFAULT_GLOSS",
    "RISK_BY_RULE_LABEL",
    "APPROVAL_PHRASE_TEMPLATE",
    "MAIN_RELAY_INSTRUCTION",
    "SUBAGENT_RELAY_INSTRUCTION",
    "DENIAL_CONTEXT_TEMPLATE",
    "NO_VERDICT_CONTEXT_TEMPLATE",
    "USER_MESSAGE_TEMPLATE",
    "CONTEXT_SEPARATOR",
]

DENIAL_EVENT_NAME = "PermissionDenied"
ALL_STOP_EVENT_NAMES = ("Stop", "SubagentStop")
STATE_DIRECTORY_NAME = "claude-auto-mode-denials"
MAIN_AGENT_KEY = "main"
UNSAFE_FILE_NAME_CHARACTERS = r"[^A-Za-z0-9_-]"
RULE_LABEL_PATTERN = r"\[([^\]]+)\]"
ALL_NO_VERDICT_REASON_PREFIXES = (
    "Auto mode could not evaluate this action",
    "Classifier unavailable",
)
MAXIMUM_ACTION_SUMMARY_CHARACTERS = 160
TRUNCATION_MARKER = "..."
SUMMARY_WORD_SEPARATOR = " "
SUMMARY_HEAD_SHARE_DIVISOR = 2
ALL_COMMAND_INPUT_KEYS = ("command", "url", "file_path", "path")
MAIN_ACTOR = "Claude"
SUBAGENT_ACTOR = "a helper agent working for Claude"


class ProgramGloss(NamedTuple):
    """One program the advisor can name in plain words.

    Attributes:
        pattern: Regular expression matched against the denied command.
        plain_action: What the actor does, in plain words.
        risk: The risk clause used when the denial names no known rule.
    """

    pattern: str
    plain_action: str
    risk: str


ALL_PROGRAM_GLOSSES = (
    ProgramGloss(
        r"\bgit\b.*\bpush\b.*(--force|\s-f\b)",
        "uses git, the program that tracks code versions, to force-push a branch",
        "history on the shared branch is overwritten and commits other people pushed can be lost",
    ),
    ProgramGloss(
        r"\bgit\b",
        "uses git, the program that tracks code versions",
        "it changes the code history in a repository other work depends on",
    ),
    ProgramGloss(
        r"\bgh\b",
        "uses gh, the GitHub command tool",
        "it acts on GitHub repositories and accounts with my sign-in",
    ),
    ProgramGloss(
        r"\bcodex\b",
        "starts Codex, another AI coding program",
        "another AI agent runs on this computer without my approval",
    ),
    ProgramGloss(
        r"\bclaude\b",
        "starts another Claude session",
        "another AI agent runs on this computer without my approval",
    ),
    ProgramGloss(
        r"\b(curl|wget|Invoke-WebRequest|Invoke-RestMethod)\b",
        "sends a web request",
        "data from this computer is sent to an outside website",
    ),
    ProgramGloss(
        r"\b(Remove-Item|del)\b",
        "deletes files",
        "the deleted files are gone for good and cannot be undone",
    ),
    ProgramGloss(
        r"\b(cat|head|tail|type|Get-Content|Select-String)\b",
        "shows the contents of a file",
        "the file may hold passwords or other secrets, and Claude sees them",
    ),
    ProgramGloss(
        r"\bes\.exe\b",
        "uses Everything, the file search program, to search this computer",
        "Claude learns where private files such as password files are kept",
    ),
)

ALL_TOOL_GLOSSES = {
    "Write": ProgramGloss("", "writes a file", "the file it writes changes what runs on this computer"),
    "Edit": ProgramGloss("", "edits a file", "the edit changes a file other work depends on"),
    "MultiEdit": ProgramGloss("", "edits a file", "the edit changes a file other work depends on"),
    "NotebookEdit": ProgramGloss("", "edits a notebook", "the edit changes a file other work depends on"),
    "WebFetch": ProgramGloss("", "opens a web page", "the page address or its content leaks data to an outside website"),
    "Agent": ProgramGloss("", "starts a helper agent", "the helper agent reads or changes things I have not checked"),
    "Task": ProgramGloss("", "starts a helper agent", "the helper agent reads or changes things I have not checked"),
}
MCP_TOOL_PREFIX = "mcp__"
MCP_NAME_SEPARATOR = "__"
MCP_GLOSS_TEMPLATE = "uses the {tool} tool of the {server} connector"
DEFAULT_GLOSS = ProgramGloss(
    "",
    "runs a {tool_name} command",
    "the command changes something on this computer or online that I have not checked",
)

RISK_BY_RULE_LABEL = {
    "Auto-Mode Bypass": "it gets around the auto mode safety check that would normally stop it",
    "Browser Navigate Exfil": "the browser could leak or expose this session or its URL to a website",
    "CI Bypass": "code goes in without the automatic security checks until someone turns them back on",
    "Create Public Surface": "anyone who can see the page can view what is published there",
    "Create Unsafe Agents": "another AI agent runs on its own, without approval or a sandbox, and can change files",
    "Credential Exploration": "Claude learns where password, token and key files are kept",
    "Credential Materialization": "Claude sees the secret tokens, passwords or keys stored there",
    "Data Exfiltration": "private data leaves this computer and is sent to an outside service",
    "Git Destructive": "history on the shared branch is overwritten and commits other people pushed can be lost",
    "Interfere With Workloads": "another session is running there and the change can break its work in progress",
    "Irreversible Local Destruction": "the deleted data is gone for good and cannot be undone",
    "Merge Without Review": "the change is merged without the review and checks that would normally run first",
    "Modify Shared Resources": "other sessions or team members who share it can lose their work",
    "Out-of-Place Publication": "the file is published where anyone who can see the release can download it",
    "PII Data Handling": "Claude reads personal and private details, such as browsing or chat history",
    "Safety Bypass Flag": "a safety guard or sandbox is turned off, so the program gets more power than usual",
    "Self-Modification": "Claude changes the settings that control its own hooks and safety checks",
    "Unauthorized Persistence": "the program keeps running at every startup until someone removes it",
    "Unrequested Commit in a Connected App": "the team is notified and sees the change before I have checked it",
    "Untrusted Code Integration": "code nobody has reviewed runs on this computer",
}

APPROVAL_PHRASE_TEMPLATE = (
    "I approve this one action: {actor} {plain_action} with `{action_summary}`. "
    "I accept the risk that {risk}."
)

MAIN_RELAY_INSTRUCTION = (
    "Show the user this code block exactly as written, so they can paste it back to approve the action."
)
SUBAGENT_RELAY_INSTRUCTION = (
    "You are a helper agent. End your work and return the code block to your parent agent unchanged. "
    "The parent shows it to the user exactly as written."
)

DENIAL_CONTEXT_TEMPLATE = """\
Auto mode denied {tool_name}. Classifier reason: {reason}
Do not retry the action. {relay_instruction}

```
{approval_phrase}
```

Then call TaskCreate (TodoWrite when TaskCreate is missing) to open one task card with this subject: \
"Pull request: add an autoMode.allow rule to packages/claude-dev-env/settings.json for: {plain_action}". \
That path is in the claude-dev-env repository, whatever repository you are in now. \
Its installer copies the rule to ~/.claude/settings.json. Do not edit ~/.claude/settings.json yourself."""

NO_VERDICT_CONTEXT_TEMPLATE = """\
Auto mode denied {tool_name} because the classifier gave no verdict. Reason: {reason}
An approval or an allow rule cannot clear this denial. Tell the user the action and the reason, and ask them to run it themselves or to try again later."""

USER_MESSAGE_TEMPLATE = "Auto mode blocked {tool_name}. Claude will give you an approval phrase."

CONTEXT_SEPARATOR = "\n\n"
