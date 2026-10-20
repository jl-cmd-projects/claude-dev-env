"""Constants for the final reply gate Stop hook."""

import re

HOOK_EVENT_NAME = "Stop"
LAST_ASSISTANT_MESSAGE_KEY = "last_assistant_message"
TRANSCRIPT_PATH_KEY = "transcript_path"
DECISION_KEY = "decision"
BLOCK_DECISION = "block"
REASON_KEY = "reason"
ALLOW_EXIT_CODE = 0
REWRITE_INSTRUCTION = " Rewrite the reply without it."
BROKEN_FILE_URL_PATTERN = re.compile(r"file://[A-Za-z]:\S*")
BROKEN_FILE_URL_MESSAGE = (
    'Broken file URL "{url}". A browser opens a Windows file only as'
    " file:///C:/ with three slashes and forward slashes."
)
WINDOWS_PATH_PATTERN = re.compile(r"(?<![\w/])[A-Za-z]:\\\S*")
WINDOWS_PATH_MESSAGE = (
    'Windows path "{path}" sits outside a code span, and markdown drops a'
    " backslash before punctuation. Wrap the path in backticks."
)
