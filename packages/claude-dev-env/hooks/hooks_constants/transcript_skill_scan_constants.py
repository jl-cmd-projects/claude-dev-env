"""Entry fields used by transcript skill scans."""

ASSISTANT_ENTRY_TYPE = "assistant"
COMPACT_BOUNDARY_SUBTYPE = "compact_boundary"
SKILL_TOOL_NAME = "Skill"
TOOL_USE_BLOCK_TYPE = "tool_use"
USER_ENTRY_TYPE = "user"
COMMAND_ARGUMENTS_PATTERN = r"<command-args>(.*?)</command-args>"
META_ENTRY_FIELD = "isMeta"
TOOL_RESULT_BLOCK_TYPE = "tool_result"
IS_ERROR_FIELD = "is_error"
TOOL_USE_ID_FIELD = "tool_use_id"
ORIGIN_FIELD = "origin"
ORIGIN_KIND_FIELD = "kind"
TASK_NOTIFICATION_ORIGIN_KIND = "task-notification"
RUN_IN_BACKGROUND_INPUT_KEY = "run_in_background"
TASK_NOTIFICATION_TOOL_USE_ID_PATTERN = r"<tool-use-id>\s*([^<\s]+)\s*</tool-use-id>"
TASK_NOTIFICATION_SUCCESS_PATTERN = r"<status>\s*completed\s*</status>[\s\S]*\(exit code 0\)"
NEWLINE_BYTE = b"\n"
CARRIAGE_RETURN_BYTE = b"\r"
ALL_LINE_BREAK_BYTES = (NEWLINE_BYTE, CARRIAGE_RETURN_BYTE)
TRANSCRIPT_BLOCK_BYTES = 1 << 20
TRANSCRIPT_LINE_BYTE_CAP = 16 * 1024 * 1024
FORWARD_COPY_BYTE_CAP = 64 * 1024 * 1024
