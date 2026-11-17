"""Entry fields used by transcript skill scans."""

ASSISTANT_ENTRY_TYPE = "assistant"
COMPACT_BOUNDARY_SUBTYPE = "compact_boundary"
SKILL_TOOL_NAME = "Skill"
TOOL_USE_BLOCK_TYPE = "tool_use"
USER_ENTRY_TYPE = "user"
META_ENTRY_FIELD = "isMeta"
TOOL_RESULT_BLOCK_TYPE = "tool_result"
IS_ERROR_FIELD = "is_error"
TOOL_USE_ID_FIELD = "tool_use_id"
ORIGIN_FIELD = "origin"
ORIGIN_KIND_FIELD = "kind"
TASK_NOTIFICATION_ORIGIN_KIND = "task-notification"
RUN_IN_BACKGROUND_INPUT_KEY = "run_in_background"
MOVED_TO_BACKGROUND_RESULT_PATTERN = (
    r"(?m)^Command (?:running in background with ID: |was manually backgrounded by user with ID: "
    r"|did not complete within [^\n]*\bmoved to the background\b)"
)
ALL_BACKGROUND_SHELL_TOOL_NAMES = frozenset({"Bash", "PowerShell"})
ATTACHMENT_ENTRY_TYPE = "attachment"
ATTACHMENT_FIELD = "attachment"
QUEUED_COMMAND_ATTACHMENT_TYPE = "queued_command"
QUEUED_COMMAND_PROMPT_FIELD = "prompt"
RESULT_TEXT_FIELD = "text"
RESULT_TEXT_SEPARATOR = "\n"
TASK_NOTIFICATION_OPENING_TAG = "<task-notification>"
TASK_NOTIFICATION_CLOSING_TAG = "</task-notification>"
TASK_NOTIFICATION_SUMMARY_OPENING_TAG = "<summary>"
TASK_NOTIFICATION_TOOL_USE_ID_PATTERN = r"<tool-use-id>\s*([^<\s]+)\s*</tool-use-id>"
TASK_NOTIFICATION_COMPLETED_STATUS_PATTERN = r"<status>\s*completed\s*</status>"
TASK_NOTIFICATION_ANY_STATUS_PATTERN = r"<status>"
TASK_NOTIFICATION_EXIT_ZERO_ENDING_PATTERN = r" completed \(exit code 0\)\s*</summary>\s*</task-notification>\s*\Z"
NEWLINE_BYTE = b"\n"
CARRIAGE_RETURN_BYTE = b"\r"
ALL_LINE_BREAK_BYTES = (NEWLINE_BYTE, CARRIAGE_RETURN_BYTE)
TRANSCRIPT_BLOCK_BYTES = 1 << 20
TRANSCRIPT_LINE_BYTE_CAP = 16 * 1024 * 1024
FORWARD_COPY_BYTE_CAP = 64 * 1024 * 1024
