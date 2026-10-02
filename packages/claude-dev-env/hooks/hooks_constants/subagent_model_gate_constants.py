"""Constants for the subagent model gate PreToolUse hook."""

ALL_CHECKED_TOOL_NAMES = frozenset({"Agent", "Task"})
ALL_DENIED_MODEL_ALIASES = frozenset({"sonnet", "fable"})
ALL_DENIED_MODEL_ID_PREFIXES = ("claude-sonnet", "claude-fable")
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
MODEL_KEY = "model"
HOOK_EVENT_NAME = "PreToolUse"
ALLOW_EXIT_CODE = 0
BLOCK_EXIT_CODE = 2
DENY_MESSAGE = (
    "Subagent model {model} is not allowed. "
    "Spawn subagents on opus and ask for medium effort in the brief."
)
