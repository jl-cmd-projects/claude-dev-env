"""Texts and names for the skill_loaded_reminder hook."""

from __future__ import annotations

__all__ = [
    "COMPACTION_REMINDER",
    "COMPACTION_SOURCE",
    "NOT_LOADED_REMINDER",
    "ALL_POTETO_MODE_SKILL_NAMES",
    "SESSION_START_EVENT_NAME",
    "ALL_SLASH_COMMAND_MARKERS",
    "SUBAGENT_START_EVENT_NAME",
    "USER_PROMPT_SUBMIT_EVENT_NAME",
    "WORKFLOW_SUBAGENT_TYPE",
]

SESSION_START_EVENT_NAME = "SessionStart"
USER_PROMPT_SUBMIT_EVENT_NAME = "UserPromptSubmit"
COMPACTION_SOURCE = "compact"
SUBAGENT_START_EVENT_NAME = "SubagentStart"
WORKFLOW_SUBAGENT_TYPE = "workflow-subagent"

ALL_POTETO_MODE_SKILL_NAMES = ("poteto-mode", "pstack:poteto-mode")
SKILL_TOOL_NAME = "Skill"
ALL_SLASH_COMMAND_MARKERS = (
    "<command-name>/poteto-mode</command-name>",
    "<command-name>/pstack:poteto-mode</command-name>",
)

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
