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
    "CLAUDE_HOST_ENV_VAR",
    "CLAUDE_HOST_TRUE_VALUE",
    "DEEPEN_AGENT_MARKER",
    "DEEPEN_COMMAND_ENV_VAR",
    "DEEPEN_COMMAND_TIMEOUT_SECONDS",
    "DEEPEN_FIRST_PROMPT_PLUGIN_NAME",
    "DEEPEN_MARKER",
    "DEEPEN_OUTPUT_ENV_VAR",
    "DEEPEN_OUTPUT_JSON",
    "DEEPEN_OUTPUT_REWRITE",
    "DEEPEN_REWRITE_ENV_VAR",
    "ALL_EXAMPLE_NOUN_STOPWORDS",
    "ALL_FOUR_QUESTION_STEMS",
    "EXAMPLE_NOUN_PATTERN",
    "HARD_CONSTRAINTS_LABEL",
    "REFUSAL_DROPPED_HARD_CONSTRAINT",
    "REFUSAL_EXAMPLE_NOUN_IN_SCOPE",
    "REFUSAL_MISSING_ROLE_LINES",
    "REFUSAL_RESTATES_FOUR_QUESTIONS",
    "ROLE_BLOCKER_LABEL",
    "ROLE_BLOCKER_NONE",
    "ROLE_EXAMPLES_LABEL",
    "BULLET_PREFIX",
    "QUESTION_LINE_SEPARATOR",
    "SCORE_ACCEPT",
    "SCORE_REFUSE",
    "ROLE_SCOPE_LABEL",
    "DEEPEN_SLASH_COMMAND",
    "DEEPEN_TIMEOUT_SECONDS",
    "DEEPEN_TURN_MARKER_SUFFIX",
    "DEEPEN_SESSION_MARKER_PREFIX",
    "ALL_FIRST_PROMPT_EVENT_NAMES",
    "CURSOR_BEFORE_SUBMIT_PROMPT_EVENT_NAME",
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
DEEPEN_SESSION_MARKER_PREFIX: str = "cde-deepen-"
DEEPEN_TIMEOUT_SECONDS: int = 10
DEEPEN_COMMAND_TIMEOUT_MARGIN_SECONDS: int = 2
DEEPEN_COMMAND_TIMEOUT_SECONDS: int = DEEPEN_TIMEOUT_SECONDS - DEEPEN_COMMAND_TIMEOUT_MARGIN_SECONDS
USER_PROMPT_SUBMIT_EVENT_NAME: str = "UserPromptSubmit"
CURSOR_BEFORE_SUBMIT_PROMPT_EVENT_NAME: str = "beforeSubmitPrompt"
ALL_FIRST_PROMPT_EVENT_NAMES: frozenset[str] = frozenset(
    {USER_PROMPT_SUBMIT_EVENT_NAME, CURSOR_BEFORE_SUBMIT_PROMPT_EVENT_NAME}
)
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
CLAUDE_HOST_ENV_VAR: str = "CLAUDECODE"
CLAUDE_HOST_TRUE_VALUE: str = "1"
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

ROLE_SCOPE_LABEL: str = "SCOPE (role):"
ROLE_EXAMPLES_LABEL: str = "EXAMPLES (illustration only):"
ROLE_BLOCKER_LABEL: str = "ZOOM-IN BLOCKER:"
ROLE_BLOCKER_NONE: str = "none"
HARD_CONSTRAINTS_LABEL: str = "HARD CONSTRAINTS"
REFUSAL_RESTATES_FOUR_QUESTIONS: str = "restates-four-questions"
REFUSAL_MISSING_ROLE_LINES: str = "missing-role-lines"
REFUSAL_EXAMPLE_NOUN_IN_SCOPE: str = "example-noun-in-scope"
REFUSAL_DROPPED_HARD_CONSTRAINT: str = "dropped-hard-constraint"
BULLET_PREFIX: str = "- "
QUESTION_LINE_SEPARATOR: str = "\n"
SCORE_ACCEPT: str = "accept"
SCORE_REFUSE: str = "refuse"
EXAMPLE_NOUN_PATTERN: str = r"[A-Za-z][A-Za-z0-9_+-]{3,}"
ALL_FOUR_QUESTION_STEMS: tuple[str, ...] = (
    "What a top person in that field would do that this prompt omitted.",
    "The raw source to start from.",
    "The methods and tools they would use.",
    "What besides the agent or Jon would show the result is right.",
)
ALL_EXAMPLE_NOUN_STOPWORDS: frozenset[str] = frozenset(
    {
        "none",
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "only",
        "illustration",
        "example",
        "into",
        "when",
        "your",
        "their",
        "about",
        "such",
        "like",
        "say",
    }
)
