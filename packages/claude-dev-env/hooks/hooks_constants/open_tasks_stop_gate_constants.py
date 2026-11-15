"""Constants for the open tasks Stop gate."""

import re

HOOK_EVENT_NAME = "Stop"
TRANSCRIPT_PATH_KEY = "transcript_path"
ALLOW_EXIT_CODE = 0
STOP_HOOK_ACTIVE_KEY = "stop_hook_active"
UTF8_ENCODING = "utf-8"
WORD_SEPARATOR = " "
TASK_LIST_ID_ENVIRONMENT_VARIABLE = "CLAUDE_CODE_TASK_LIST_ID"
CLAUDE_CONFIG_DIRECTORY_ENVIRONMENT_VARIABLE = "CLAUDE_CONFIG_DIR"
CLAUDE_HOME_DIRECTORY_NAME = ".claude"
TASKS_DIRECTORY_NAME = "tasks"
TASK_FILE_GLOB = "*.json"
TASK_ID_KEY = "id"
TASK_SUBJECT_KEY = "subject"
TASK_STATUS_KEY = "status"
PENDING_STATUS = "pending"
INCOMPLETE_STATUSES = frozenset({PENDING_STATUS, "in_progress"})
RECORD_TYPE_KEY = "type"
MESSAGE_KEY = "message"
CONTENT_KEY = "content"
TEXT_KEY = "text"
TOOL_NAME_KEY = "name"
TOOL_INPUT_KEY = "input"
TOOL_USE_ID_KEY = "tool_use_id"
TODOS_KEY = "todos"
TODO_CONTENT_KEY = "content"
TODO_ID_KEY = "id"
TODO_MERGE_KEY = "merge"
ROLE_KEY = "role"
ASSISTANT_ROLE = "assistant"
CURSOR_CONVERSATION_ID_KEY = "conversation_id"
CURSOR_STATUS_KEY = "status"
CURSOR_COMPLETED_STATUS = "completed"
CURSOR_LOOP_COUNT_KEY = "loop_count"
TASK_UPDATE_ID_KEY = "taskId"
TODO_WRITE_TOOL_NAME = "TodoWrite"
DYNAMIC_TOOL_CALL_NAME = "CallDynamicTool"
DYNAMIC_TOOL_NAME_KEY = "toolName"
DYNAMIC_TOOL_ARGUMENTS_KEY = "arguments"
TASK_CREATE_TOOL_NAME = "TaskCreate"
TASK_UPDATE_TOOL_NAME = "TaskUpdate"
TOOL_USE_BLOCK_TYPE = "tool_use"
TOOL_RESULT_BLOCK_TYPE = "tool_result"
CODEX_RESPONSE_ITEM_TYPE = "response_item"
CODEX_FUNCTION_CALL_TYPE = "function_call"
CODEX_PAYLOAD_KEY = "payload"
CODEX_ARGUMENTS_KEY = "arguments"
CODEX_PLAN_TOOL_NAME = "update_plan"
CODEX_PLAN_KEY = "plan"
CODEX_STEP_KEY = "step"
FIRST_ITEM_NUMBER = 1
TASK_CREATED_PATTERN = r"Task #(\d+) created"
CREATED_TASK_ID_GROUP_INDEX = 1
TASK_NUMBER_REFERENCE_TEMPLATE = "#{task_id}"
ALL_SKIPPED_PROMPT_FLAGS = ("isMeta", "isSidechain", "isCompactSummary")
USER_ROLE = "user"
USER_RECORD_TYPE = "user"
CODEX_MESSAGE_TYPE = "message"
STOP_HOOK_FEEDBACK_PREFIX = "Stop hook feedback"
COMPLETED_STATUS = "completed"
IN_PROGRESS_STATUS = "in_progress"
ASSISTANT_RECORD_TYPE = "assistant"
CCD_PLAN_TOOL_NAME = "mcp__ccd_turn__update_plan"
CCD_PLAN_ITEMS_KEY = "items"
CCD_PLAN_CONTENT_KEY = "content"
CCD_PLAN_DONE_KEY = "done"
CCD_PLAN_START_KEY = "start"
CCD_PLAN_ADVANCE_KEY = "advance"
CCD_PLAN_ITEM_ID_TEMPLATE = "plan-{position}"
PROMPT_KEY = "prompt"
SENTENCE_SPLIT_PATTERN = r"(?<=[.!?])\s+|\n+"
QUESTION_END_PATTERN = r"\?\s*$"
YES_OR_NO_END_PATTERN = r"\byes\s+or\s+no\W*$"
INTERROGATIVE_START_PATTERN = (
    r"^\s*(?:\w+,\s*)?(?:are|is|am|was|were|do|does|did|have|has|had|can|could|will|would"
    r"|should|shall|may|what|why|how|when|where|which|who|whose)\b"
)
ALL_ASK_ONLY_ENVELOPE_MARKERS = ("<agent-message",)
SYSTEM_REMINDER_BLOCK_PATTERN = r"<system-reminder>.*?</system-reminder>"
ACKNOWLEDGEMENT_PATTERN = (
    r"^\s*(?:ok(?:ay)?|k|thanks?|thank\s+you|thx|ty|cool|great|nice|perfect|awesome|got\s+it"
    r"|sounds\s+good|looks\s+good|lgtm)(?:[\s,]+(?:thanks?|thank\s+you))?\W*$"
)
POLITE_REQUEST_START_PATTERN = r"^\s*(?:please\b|(?:can|could|would|will)\s+you\b)"
ALL_TRACKER_TOOL_NAMES = frozenset({TODO_WRITE_TOOL_NAME, TASK_CREATE_TOOL_NAME, TASK_UPDATE_TOOL_NAME})
ALL_NON_WORK_TOOL_NAMES = frozenset(
    {
        "AskUserQuestion",
        "mcp__hearthbot__ask_decision",
        "mcp__hearthbot__request_decision",
        "ToolSearch",
        "TaskList",
        "TaskGet",
        "request_user_input",
        "request_user_input_async",
    }
)
ALL_QUESTION_TOOL_NAMES = frozenset(
    {
        "AskUserQuestion",
        "mcp__hearthbot__ask_decision",
        "mcp__hearthbot__request_decision",
        "request_user_input",
        "request_user_input_async",
    }
)
SESSION_TITLE_TOOL_SUFFIX = "__set_session_title"
CODEX_LOCAL_SHELL_CALL_TYPE = "local_shell_call"
ALL_CODEX_TOOL_CALL_TYPES = frozenset({CODEX_FUNCTION_CALL_TYPE, "custom_tool_call", CODEX_LOCAL_SHELL_CALL_TYPE})
UNTRACKED_WORK_REASON = (
    "This turn worked on the user's ask and left the task list unchanged. The user follows your work"
    " there. Update it now: TaskCreate the ask if it has no item, and TaskUpdate each item to its"
    " current status (TodoWrite or update_plan where that is the tracker)."
)
COMPLETED_ITEMS_REASON_TEMPLATE = (
    "The task list shows completed work beside open items ({completed_count} of {item_count} items"
    " are completed). The user reads that list to see what is open. Remove each completed item now:"
    " TaskUpdate with status deleted (TodoWrite or update_plan: send the list without it)."
)
KEEP_REPLY_INSTRUCTION = "Then end the turn. Leave the reply as it stands."
USER_STEP_LEAD_TEMPLATE = (
    'This turn tells the user that something waits on them ("{phrase}"). An item can close while it'
    " sits on a list, so in this turn read the live state of each item you show as open: the pull"
    " request, the session, the setting, or the log. Drop each one that is done, and show the user"
    " only what still stands open."
)
UNREAD_STEP_REASON = "The turn ran no read call."
UNASKED_STEP_REASON = (
    "The turn sent no question through the native question tool. Hand over each step on its own"
    " through AskUserQuestion (Codex: request_user_input), one step per question: one short sentence"
    " on what the step does, with the command block to paste or the link to open inside the"
    " question. Keep long guides out of it. Where the host has no question tool, give each step its"
    " own short paragraph with its block or link."
)
NO_STEP_INSTRUCTION = "When the wording hands the user no step, end the turn and leave the reply as it stands."
WORKING_DIRECTORY_KEY = "cwd"
SENT_FILES_KEY = "files"
ALL_READ_TOOL_NAMES = frozenset(
    {
        "Bash",
        "PowerShell",
        "Shell",
        "shell",
        "shell_command",
        "exec_command",
        "Read",
        "Grep",
        "Glob",
        "WebFetch",
        "WebSearch",
        "Agent",
        "Task",
    }
)
ALL_READ_WORDS = frozenset(
    {"get", "list", "read", "view", "search", "fetch", "query", "describe", "status", "log", "logs", "diff", "show"}
)
ALL_WRITE_WORDS = frozenset(
    {
        "update", "set", "create", "delete", "write", "append", "add", "remove", "send", "post", "edit",
        "put", "patch", "save", "insert", "reset", "apply", "replace",
    }
)
TOOL_NAME_SERVER_SEPARATOR = "__"
RECORD_SEPARATOR = "\n"
TOOL_NAME_WORD_BREAK_PATTERN = r"[_\-]+|(?<=[a-z0-9])(?=[A-Z])"
PROMPT_SUBMIT_EVENT_NAME = "UserPromptSubmit"
TASK_LIST_NUDGE = (
    "The user follows your work in the task list. Give each ask an item in the session's task list"
    " tool and keep each item's status current as the work moves. Remove completed items before the"
    " turn ends, so the list shows only open work."
)
TASK_LIST_NUDGE_ONCE_MARKER_NAME = "tracking_nudge"
APOSTROPHE_CLASS = "['’]"
ALL_PROMISED_REPORT_PATTERNS = tuple(
    re.compile(each_pattern, re.IGNORECASE)
    for each_pattern in (
        rf"\bwhen you(?:{APOSTROPHE_CLASS}re| are| get| come) back\b",
        r"\b(?:report|summary|write-?up|recap|results?)\b[^.!?\n]{0,80}?"
        r"\bwill (?:be (?:here|waiting|ready|posted)|follow|land|arrive|come)\b",
        rf"\bI(?:{APOSTROPHE_CLASS}ll| will| am going to)\s+(?:report|post|send|share|update you|let you know"
        r"|follow up|circle back|check back|get back to you)\b[^.!?\n]{0,80}?"
        r"\b(?:when|once|after|later|tomorrow|in the morning)\b",
        rf"\bI(?:{APOSTROPHE_CLASS}ll| will| am going to)\s+report back\b",
    )
)
PROMISE_NEGATOR_PATTERN = re.compile(r"\b(?:no|not|never|none|nothing)\b", re.IGNORECASE)
REPLY_SENTENCE_END_PATTERN = re.compile(r"[.!?\n]")
REPORT_ASK_PATTERN = re.compile(
    r"\b(?:report|summary|summari[sz]e|recap|update me|let me know|tell me (?:when|once|how))\b", re.IGNORECASE
)
LIST_ASK_PATTERN = re.compile(
    r"\blist\s+(?:the|them|all|each|every|what|out)\b"
    r"|\b(?:as|in|into)\s+(?:a\s+)?(?:list|bullets?|table)\b"
    r"|\ba\s+list\s+of\b"
    r"|\bgive\s+me\s+(?:a|the)\s+(?:list|table|bullets?)\b"
    r"|\bbulleted\b",
    re.IGNORECASE,
)
ASK_NEGATOR_PATTERN = re.compile(
    rf"\b(?:no|not|never|none|nothing|without|don{APOSTROPHE_CLASS}t|do not|no need|never mind)\b", re.IGNORECASE
)
PROMPT_CLAUSE_SPLIT_PATTERN = re.compile(r"[.!?;,\n]|\bthen\b", re.IGNORECASE)
QUOTED_PROMPT_LINE_PATTERN = re.compile(r"^[ \t]*>.*$", re.MULTILINE)
BACKTICK_TEXT_PATTERN = re.compile(r"`[^`]*`")
SPACED_QUOTE_PATTERN = re.compile(r'"[^"]*\s[^"]*"|“[^”]*\s[^”]*”')
REMOVED_PROMPT_TEXT = " "
OPEN_ITEM_LEAD_PATTERN = re.compile(
    r"\b(?:deferred|defer|sidestepped|not (?:yet )?done|left open|still open|remaining|outstanding|open items?"
    r"|unfinished|unresolved|pending|parked|postponed|follow-?ups?|next steps|to-?dos?|loose ends)\b",
    re.IGNORECASE,
)
LEAD_NEGATOR_PATTERN = re.compile(r"\b(?:no|none|nothing|nobody|zero)\b", re.IGNORECASE)
QUOTED_REPLY_LINE_PATTERN = re.compile(r"^\s*>")
ALL_INDENTED_LINE_PREFIXES = (" ", "\t")
OPEN_ITEM_LIST_MINIMUM = 3
USER_WORDS_ESCAPE_SENTENCE = (
    "If the user's own words in this turn asked for this, leave the reply as it is and end the turn."
)
PROMISED_REPORT_REASON_TEMPLATE = (
    'The closing reply promises the user a later report ("{phrase}"), and no typed prompt in this turn asked'
    " for one. Drop the promise and carry the work to completion. If work is still open, do it now. If the"
    " turn waits on a run or a wake you armed, say in one sentence what runs and what you do when it ends. "
    + USER_WORDS_ESCAPE_SENTENCE
)
OPEN_ITEM_LIST_REASON_TEMPLATE = (
    'The closing reply lists {count} open items under "{lead}", and this turn sent no question through the'
    " native question tool. Read the live state of each item and drop the ones that are done. Act now on each"
    " item you can settle yourself. Put each item that needs the user's judgment in its own AskUserQuestion"
    " call (Codex: request_user_input), with the context in the question text and two or three options whose"
    " effects sit in their descriptions. The first question call after this hold can be refused once for the"
    " length of the held reply; send the same call again. Then end the turn with a short reply that names what"
    " you did. " + USER_WORDS_ESCAPE_SENTENCE
)
REWORKED_REPLY_INSTRUCTION = "Then send the reworked closing reply and end the turn."
