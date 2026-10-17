"""Named values for first-task deepening."""

from __future__ import annotations

from hooks_constants.mod_handoff_constants import DEEPEN_FIRST_PROMPT_PLUGIN_NAME
from hooks_constants.skill_loaded_reminder_constants import (
    CLAUDE_SUBAGENT_PROMPT_PREFIX,
    CODEX_SUBAGENT_PROMPT_PREFIX,
)

__all__ = [
    "ADDITIONAL_CONTEXT_KEY",
    "ALL_HELPER_REPORT_MARKERS",
    "ALL_LOOP_PROMPT_PREFIXES",
    "ALL_NONINTERACTIVE_ENV_TRUE_VALUES",
    "ALL_SPAWN_REWRITE_PREFIXES",
    "ALL_TRIVIAL_PROMPTS",
    "DEEPEN_AGENT_MARKER",
    "DEEPEN_COMMAND_ENV_VAR",
    "DEEPEN_FIRST_PROMPT_PLUGIN_NAME",
    "DEEPEN_MARKER",
    "DEEPEN_OUTPUT_ENV_VAR",
    "DEEPEN_OUTPUT_JSON",
    "DEEPEN_OUTPUT_REWRITE",
    "DEEPEN_REWRITE_ENV_VAR",
    "DEEPEN_SLASH_COMMAND",
    "DEEPEN_TIMEOUT_SECONDS",
    "DEEPEN_TURN_MARKER_SUFFIX",
    "HOOK_EVENT_NAME_KEY",
    "HOOK_SPECIFIC_OUTPUT_KEY",
    "JSONL_ROLE_KEY",
    "JSONL_TYPE_KEY",
    "NONINTERACTIVE_CODEX_ENV_VAR",
    "NONINTERACTIVE_PRINT_ENV_VAR",
    "PROMPT_FIELD_NAME",
    "SESSION_ID_FIELD_NAME",
    "SKIP_DEEPEN_ENV_VAR",
    "SKIP_DEEPEN_TRUE_VALUE",
    "TRANSCRIPT_PATH_FIELD_NAME",
    "USER_PROMPT_SUBMIT_EVENT_NAME",
    "USER_ROLE_NAME",
    "USER_TYPE_NAME",
    "UTF8_ENCODING",
]

DEEPEN_MARKER: str = "CDE_DEEPEN:v1"
DEEPEN_AGENT_MARKER: str = "CDE_DEEPEN_AGENT"
DEEPEN_SLASH_COMMAND: str = "/deepen"
DEEPEN_TURN_MARKER_SUFFIX: str = ".cde-deepen-turn1"
DEEPEN_TIMEOUT_SECONDS: int = 10
USER_PROMPT_SUBMIT_EVENT_NAME: str = "UserPromptSubmit"
PROMPT_FIELD_NAME: str = "prompt"
TRANSCRIPT_PATH_FIELD_NAME: str = "transcript_path"
SESSION_ID_FIELD_NAME: str = "session_id"
HOOK_SPECIFIC_OUTPUT_KEY: str = "hookSpecificOutput"
HOOK_EVENT_NAME_KEY: str = "hookEventName"
ADDITIONAL_CONTEXT_KEY: str = "additionalContext"
SKIP_DEEPEN_ENV_VAR: str = "CDE_SKIP_DEEPEN"
SKIP_DEEPEN_TRUE_VALUE: str = "1"
DEEPEN_REWRITE_ENV_VAR: str = "CDE_DEEPEN_REWRITE"
DEEPEN_COMMAND_ENV_VAR: str = "CDE_DEEPEN_COMMAND"
DEEPEN_OUTPUT_ENV_VAR: str = "CDE_DEEPEN_OUTPUT"
DEEPEN_OUTPUT_REWRITE: str = "rewrite"
DEEPEN_OUTPUT_JSON: str = "json"
NONINTERACTIVE_PRINT_ENV_VAR: str = "CLAUDE_CODE_NONINTERACTIVE"
NONINTERACTIVE_CODEX_ENV_VAR: str = "CODEX_EXEC"
ALL_NONINTERACTIVE_ENV_TRUE_VALUES: frozenset[str] = frozenset({"1", "true", "yes"})
UTF8_ENCODING: str = "utf-8"
JSONL_TYPE_KEY: str = "type"
JSONL_ROLE_KEY: str = "role"
USER_TYPE_NAME: str = "user"
USER_ROLE_NAME: str = "user"

ALL_TRIVIAL_PROMPTS: frozenset[str] = frozenset(
    {
        "yes",
        "y",
        "no",
        "n",
        "ok",
        "okay",
        "thanks",
        "thank you",
        "thx",
        "status",
        "hello",
        "hi",
        "hey",
        "k",
        "sure",
        "continue",
        "go",
        "?",
    }
)

ALL_LOOP_PROMPT_PREFIXES: tuple[str, ...] = (
    "/loop",
    "<scheduled-task",
    "scheduled task firing",
)

ALL_HELPER_REPORT_MARKERS: tuple[str, ...] = (
    "<task-notification",
    "background subagent reporting",
    "a message another session sends",
)

ALL_SPAWN_REWRITE_PREFIXES: tuple[str, ...] = (
    CLAUDE_SUBAGENT_PROMPT_PREFIX,
    CODEX_SUBAGENT_PROMPT_PREFIX,
)
