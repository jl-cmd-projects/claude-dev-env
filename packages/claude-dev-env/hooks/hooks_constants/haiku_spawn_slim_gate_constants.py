"""Constants for the Haiku spawn slim-profile PreToolUse gate.

Groups: the model family the gate denies, the hook event name, the hook input and output keys, and
the deny reason that gives the headless slim-profile command.
"""

from __future__ import annotations

HAIKU_MODEL_FAMILY = "haiku"
HOOK_EVENT_NAME = "PreToolUse"
TOOL_INPUT_KEY = "tool_input"
MODEL_INPUT_KEY = "model"
DENY_DECISION = "deny"
PERMISSION_DECISION_REASON_KEY = "permissionDecisionReason"
SLIM_PROFILE_DENY_REASON = (
    "BLOCKED: A Haiku agent started from this session runs with this session's settings, plugins, "
    "MCP servers, and CLAUDE.md files. An Agent, Task, or thread spawn has no field for setting sources, "
    "a plugin directory, or an MCP config, so it cannot load the slim profile. "
    "Start Haiku as a headless run with the slim profile. Set CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 and "
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 in the environment, then run this from Bash or another POSIX shell, "
    "because PowerShell strips the double quotes inside the single-quoted JSON: "
    'python "$HOME/.claude/scripts/account_broker.py" run --product claude --report <report.json> -- '
    "claude -p --model haiku --setting-sources local "
    '--settings \'{"enabledPlugins": {}, "autoMemoryEnabled": false, "autoCompactWindow": 100000}\' '
    "--strict-mcp-config --mcp-config '{\"mcpServers\": {}}' --autocompact 100k. "
    "Send the task on standard input. In a cloud session, run the same claude -p command without the broker. "
    "Where the efficient-review skill is installed, /efficient-review headless or /efficient-review auto builds "
    "this profile. To keep the agent in this session, spawn it on opus or sonnet."
)
