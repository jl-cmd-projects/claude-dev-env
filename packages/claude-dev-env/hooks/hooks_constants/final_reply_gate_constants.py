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
WINDOWS_PATH_PATTERN = re.compile(r"(?<!\w)[A-Za-z]:\\\S*")
ESCAPED_PUNCTUATION_PATTERN = re.compile(r"\\[!-/:-@\[-`{-~]")
WINDOWS_PATH_MESSAGE = (
    'Windows path "{path}" sits outside a code span. The terminal renders'
    " markdown and drops a backslash before punctuation, so a copied path"
    " points nowhere. Wrap the path in backticks."
)
