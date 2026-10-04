"""Texts and names for the skill_loaded_reminder hook."""

from __future__ import annotations

__all__ = [
    "ALL_SELF_LOADING_SUBAGENT_TYPES",
    "COMPACTION_REMINDER",
    "COMPACTION_SOURCE",
    "NOT_LOADED_REMINDER",
    "ALL_POTETO_MODE_SKILL_NAMES",
    "PRE_TOOL_USE_EVENT_NAME",
    "PROMPT_SEPARATOR",
    "SESSION_START_EVENT_NAME",
    "ALL_SLASH_COMMAND_MARKERS",
    "SUBAGENT_START_EVENT_NAME",
    "CLAUDE_SUBAGENT_PROMPT_PREFIX",
    "CODEX_SUBAGENT_PROMPT_PREFIX",
    "ALL_SPAWN_PROMPT_FIELDS_AND_PREFIXES_BY_TOOL_NAME",
    "USER_PROMPT_SUBMIT_EVENT_NAME",
    "WORKFLOW_SUBAGENT_TYPE",
]

PRE_TOOL_USE_EVENT_NAME = "PreToolUse"
SESSION_START_EVENT_NAME = "SessionStart"
USER_PROMPT_SUBMIT_EVENT_NAME = "UserPromptSubmit"
COMPACTION_SOURCE = "compact"
SUBAGENT_START_EVENT_NAME = "SubagentStart"
WORKFLOW_SUBAGENT_TYPE = "workflow-subagent"

ALL_SELF_LOADING_SUBAGENT_TYPES = frozenset({"pstack:poteto-agent", "poteto-agent"})

ALL_POTETO_MODE_SKILL_NAMES = ("poteto-mode", "pstack:poteto-mode")
SKILL_TOOL_NAME = "Skill"
ALL_SLASH_COMMAND_MARKERS = (
    "<command-name>/poteto-mode</command-name>",
    "<command-name>/pstack:poteto-mode</command-name>",
)
PROMPT_SEPARATOR = "\n\n"

CLAUDE_SUBAGENT_PROMPT_PREFIX = (
    "Before any other work, invoke the poteto-mode skill with the Skill tool. "
    "Every prompt you write for a subagent opens with the same instruction."
)

CODEX_SUBAGENT_PROMPT_PREFIX = "$poteto-mode"

ALL_SPAWN_PROMPT_FIELDS_AND_PREFIXES_BY_TOOL_NAME = {
    "Agent": ("prompt", CLAUDE_SUBAGENT_PROMPT_PREFIX),
    "Task": ("prompt", CLAUDE_SUBAGENT_PROMPT_PREFIX),
    "spawn_agent": ("message", CODEX_SUBAGENT_PROMPT_PREFIX),
}

NOT_LOADED_REMINDER = (
    "The poteto-mode skill is not loaded in this context. "
    "Your next tool call is the Skill tool with skill poteto-mode, before any other "
    "tool call."
)

COMPACTION_REMINDER = (
    "The context was just compacted and the poteto-mode skill rules may have been dropped. "
    "Your next tool call is the Skill tool with skill poteto-mode, before any other "
    "tool call. Then re-read the request that started this session and continue."
)
