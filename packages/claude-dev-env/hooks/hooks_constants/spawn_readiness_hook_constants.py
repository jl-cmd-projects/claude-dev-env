"""Constants for the spawn readiness PreToolUse hook.

Groups: the spawn tools it checks and their brief fields, the transcript entry
shapes it reads, the tool names that count as a read or a question, the
scope-settled line, and the deny messages and log fields.
"""

from __future__ import annotations

TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
TOOL_USE_ID_KEY = "tool_use_id"
TRANSCRIPT_PATH_KEY = "transcript_path"
AGENT_ID_KEY = "agent_id"
SUBAGENT_TYPE_INPUT_KEY = "subagent_type"

THREAD_SPAWN_TOOL_NAME = "mcp__hearthbot__start_thread_session"
ALL_BRIEF_FIELDS_BY_SPAWN_TOOL_NAME = {
    "Agent": "prompt",
    "Task": "prompt",
    THREAD_SPAWN_TOOL_NAME: "instructions",
}
ALL_READ_ONLY_SUBAGENT_TYPES = frozenset({"Explore", "Plan", "claude-code-guide"})

ENTRY_TYPE_KEY = "type"
USER_ENTRY_TYPE = "user"
ASSISTANT_ENTRY_TYPE = "assistant"
ATTACHMENT_ENTRY_TYPE = "attachment"
QUEUED_COMMAND_ATTACHMENT_TYPE = "queued_command"
ATTACHMENT_KEY = "attachment"
QUEUED_PROMPT_KEY = "prompt"
MESSAGE_KEY = "message"
CONTENT_KEY = "content"
IS_META_KEY = "isMeta"
IS_COMPACT_SUMMARY_KEY = "isCompactSummary"
BLOCK_TYPE_KEY = "type"
TEXT_BLOCK_TYPE = "text"
TEXT_KEY = "text"
TOOL_USE_BLOCK_TYPE = "tool_use"
TOOL_RESULT_BLOCK_TYPE = "tool_result"
BLOCK_ID_KEY = "id"
BLOCK_NAME_KEY = "name"
BLOCK_INPUT_KEY = "input"
RESULT_TOOL_USE_ID_KEY = "tool_use_id"
RESULT_IS_ERROR_KEY = "is_error"

ALL_HARNESS_ENVELOPE_MARKERS = (
    "<wake",
    "<relay",
    "<task-notification",
    "<cross-session-message",
    "<system-note",
    "<local-command",
)
HUMAN_SENDER_MARKER = 'from="human"'

ALL_READ_TOOL_NAMES = frozenset(
    {
        "Read",
        "Grep",
        "Glob",
        "Bash",
        "PowerShell",
        "LS",
        "NotebookRead",
        "WebFetch",
        "WebSearch",
    }
)
MCP_TOOL_NAME_PREFIX = "mcp__"
MCP_TOOL_NAME_SEPARATOR = "__"
ALL_MCP_READ_VERB_PREFIXES = ("fetch", "read", "get", "list", "search", "query")
ALL_INTERACTIVE_QUESTION_TOOL_NAMES = frozenset(
    {"AskUserQuestion", "request_user_input", "request_user_input_async"}
)
ALL_INTERACTIVE_MCP_ACTIONS = frozenset({"ask_decision", "post_widget"})

SCOPE_SETTLED_PREFIX = "Scope settled:"

PRE_TOOL_USE_EVENT_NAME = "PreToolUse"
HOOK_SPECIFIC_OUTPUT_KEY = "hookSpecificOutput"
HOOK_EVENT_NAME_KEY = "hookEventName"
PERMISSION_DECISION_KEY = "permissionDecision"
PERMISSION_DECISION_REASON_KEY = "permissionDecisionReason"
PERMISSION_DENY = "deny"
MISSING_INVESTIGATION_REASON = (
    "Investigate the request before this spawn. Read the files, threads, or "
    "sources it names, so the brief and the agent count fit the task. Run the "
    "reads in a message before the spawn."
)
MISSING_INTERVIEW_REASON = (
    "Interview the user before this spawn. Ask your scope, requirements, and "
    "goals questions through AskUserQuestion, a decision card, or an "
    "interactive widget, and spawn after the answer. When the request "
    "already settles scope, add a brief line that starts with "
    f'"{SCOPE_SETTLED_PREFIX}" and names the reason.'
)
REASON_SEPARATOR = " "

TRANSCRIPT_ENCODING = "utf-8"
TRANSCRIPT_DECODE_ERRORS = "replace"
DECISION_LOG_RELATIVE_PATH = ".claude/logs/spawn-readiness.jsonl"
LOG_APPEND_MODE = "a"
LOG_LINE_END = "\n"
LOG_TIMESTAMP_KEY = "timestamp"
LOG_TOOL_NAME_KEY = "tool_name"
LOG_TOOL_USE_ID_KEY = "tool_use_id"
LOG_OUTCOME_KEY = "outcome"
LOG_SCOPE_SETTLED_LINE_KEY = "scope_settled_line"
OUTCOME_SCOPE_SETTLED = "scope_settled"
OUTCOME_TRANSCRIPT_UNREADABLE = "transcript_unreadable"
