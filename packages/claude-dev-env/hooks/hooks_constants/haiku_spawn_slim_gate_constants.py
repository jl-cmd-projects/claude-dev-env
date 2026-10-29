"""Constants for the Haiku spawn slim-profile PreToolUse gate.

Groups: the model family the gate denies, the hook event name, the hook input and output keys, and
the deny reason that gives the headless slim-profile command.
"""

from __future__ import annotations

HAIKU_MODEL_FAMILY = "haiku"
LEAN_WORKER_SUBAGENT_TYPE = "lean-worker"
LEAN_WORKER_SPAWN_TOOL_NAMES = frozenset({"Agent", "Task"})
SLIM_PROFILE_NAME = "slim"
SLIM_PROFILE_EXECUTABLE = "claude"
SLIM_PROFILE_SETTINGS_JSON = (
    '{"enabledPlugins": {}, "autoMemoryEnabled": false, "autoCompactWindow": 100000}'
)
SLIM_PROFILE_MCP_CONFIG_JSON = '{"mcpServers": {}}'
SHELL_ARGUMENT_SEPARATOR = " "
ENVIRONMENT_NAME_SEPARATOR = " and "
JSON_ARGUMENT_PREFIX = "{"
ALL_SLIM_PROFILE_ENVIRONMENT = (
    "CLAUDE_CODE_DISABLE_CLAUDE_MDS=1",
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY=1",
)
ALL_SLIM_PROFILE_ARGUMENTS = (
    "-p",
    "--model",
    HAIKU_MODEL_FAMILY,
    "--setting-sources",
    "local",
    "--settings",
    SLIM_PROFILE_SETTINGS_JSON,
    "--strict-mcp-config",
    "--mcp-config",
    SLIM_PROFILE_MCP_CONFIG_JSON,
    "--autocompact",
    "100k",
)
HOOK_EVENT_NAME = "PreToolUse"
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
MODEL_INPUT_KEY = "model"
SUBAGENT_TYPE_INPUT_KEY = "subagent_type"
DENY_DECISION = "deny"
PERMISSION_DECISION_REASON_KEY = "permissionDecisionReason"


def _shell_argument(argument: str) -> str:
    if argument.startswith(JSON_ARGUMENT_PREFIX):
        return f"'{argument}'"
    return argument


SLIM_PROFILE_SHELL_COMMAND = SHELL_ARGUMENT_SEPARATOR.join(
    (
        SLIM_PROFILE_EXECUTABLE,
        *(_shell_argument(each_argument) for each_argument in ALL_SLIM_PROFILE_ARGUMENTS),
    )
)
SLIM_PROFILE_ENVIRONMENT_TEXT = ENVIRONMENT_NAME_SEPARATOR.join(ALL_SLIM_PROFILE_ENVIRONMENT)
SLIM_PROFILE_DENY_REASON = (
    "BLOCKED: A Haiku agent started from this session runs with this session's settings, plugins, "
    "MCP servers, and CLAUDE.md files. An Agent, Task, or thread spawn has no field for setting sources, "
    "a plugin directory, or an MCP config, so it cannot load the slim profile. "
    "Use one of two routes. Route 1: spawn subagent_type lean-worker with model haiku. The gate allows only that type to run here without the slim profile. "
    "Route 2: start Haiku as a headless run with the slim profile. Set "
    f"{SLIM_PROFILE_ENVIRONMENT_TEXT} in the environment, then run this from Bash or another POSIX shell, "
    "because PowerShell strips the double quotes inside the single-quoted JSON: "
    'python "$HOME/.claude/scripts/account_broker.py" run --product claude --report <report.json> -- '
    f"{SLIM_PROFILE_SHELL_COMMAND}. "
    "Send the task on standard input. In a cloud session, run the same claude -p command without the broker. "
    "Where the efficient-review skill is installed, its plan prints that claude -p command without the broker. "
    "To run any other agent in this session, spawn it on opus or sonnet."
)
