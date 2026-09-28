"""Advisor consult guidance for the SessionStart advisor_rules_prompt hook.

Each sentence in ``ALL_ADVISOR_RULE_SENTENCES`` is copied word for word from
``docs/references/advisor-tool.md``, which stays the one source. A
synchronization test fails when a sentence drifts from that document.
"""

from __future__ import annotations

__all__ = [
    "ADVISOR_DISABLE_ENV_VAR",
    "ADVISOR_MODEL_SETTINGS_KEY",
    "ADVISOR_RULES_HEADER",
    "ADVISOR_RULES_PROMPT",
    "ALL_ADVISOR_RULE_SENTENCES",
    "ALL_ADVISOR_DISABLE_ENV_TRUE_VALUES",
    "CLAUDE_CONFIG_DIR_ENV_VAR",
    "DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME",
    "USER_SETTINGS_FILE_NAME",
]

ADVISOR_MODEL_SETTINGS_KEY = "advisorModel"
ADVISOR_DISABLE_ENV_VAR = "CLAUDE_CODE_DISABLE_ADVISOR_TOOL"
ALL_ADVISOR_DISABLE_ENV_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
CLAUDE_CONFIG_DIR_ENV_VAR = "CLAUDE_CONFIG_DIR"
DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME = ".claude"
USER_SETTINGS_FILE_NAME = "settings.json"

ADVISOR_RULES_HEADER = (
    "ADVISOR, when `advisor` is in your tool list. Use your own judgment on when a"
    " consult helps. Starting points from ~/.claude/docs/references/advisor-tool.md:"
)

ALL_ADVISOR_RULE_SENTENCES = (
    "Call for design, architecture, and risk questions where you will not touch a file.",
    "On tasks longer than a few steps, aim for an early approach consult and a completion review.",
    "This cadence guides planning and leaves the task free to follow its evidence.",
    "Short reactive tasks may use the single consult that best fits the live decision.",
    "Ask the advisor to hunt for missing requirements, untested behavior, wrong assumptions, unhandled edge cases, evidence gaps, and early completion claims.",
    "Give the advice serious weight.",
)

ADVISOR_RULES_PROMPT = " ".join((ADVISOR_RULES_HEADER, *ALL_ADVISOR_RULE_SENTENCES))
