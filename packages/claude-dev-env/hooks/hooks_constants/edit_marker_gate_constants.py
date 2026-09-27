"""Constants for the edit marker gate PreToolUse hook."""

import re

MESSAGE_EDIT_TOOL_SUFFIX = "update_message"
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
HOOK_EVENT_NAME = "PreToolUse"
ALLOW_EXIT_CODE = 0
BLOCK_EXIT_CODE = 2
STRIKETHROUGH_PATTERN = re.compile(r"~~[^~]+~~")
EDIT_NOTE_PATTERN = re.compile(r"\[\s*edit\s*:", re.IGNORECASE)
STRIKETHROUGH_MESSAGE = "Edited message holds strikethrough (~~text~~)."
EDIT_NOTE_MESSAGE = 'Edited message holds an "[Edit:" note.'
RETRY_INSTRUCTION = (
    " An edit replaces the whole message. Resend the clean new text,"
    " with nothing kept from the old version."
)
