"""Constants for the UserPromptSubmit hook that keeps a background event turn silent."""

from __future__ import annotations

import re

ORIGIN_KEY = "origin"
ORIGIN_KIND_KEY = "kind"
HUMAN_ORIGIN_KIND = "human"
TASK_NOTIFICATION_MARKER = "<task-notification"
BACKGROUND_EVENT_MARKER = "[SYSTEM NOTIFICATION - NOT USER INPUT]"
ALL_SET_PATTERNS = (
    re.compile(r"\b(?:silent|quiet)\s+unless\b", re.IGNORECASE),
    re.compile(r"\b(?:stay|go)\s+(?:silent|quiet)\b", re.IGNORECASE),
    re.compile(r"\bsilent\s+on\s+updates\b", re.IGNORECASE),
    re.compile(r"\bno\s+updates\s+unless\b", re.IGNORECASE),
)
ALL_LIFT_PATTERNS = (
    re.compile(r"\byou\s+can\s+talk\s+again\b", re.IGNORECASE),
    re.compile(r"\bupdates\s+are\s+(?:fine|ok(?:ay)?)\b", re.IGNORECASE),
    re.compile(r"\bstop\s+being\s+(?:silent|quiet)\b", re.IGNORECASE),
    re.compile(r"\b(?:don['’]?t|do\s+not)\s+(?:stay|be|go)\s+(?:silent|quiet)\b", re.IGNORECASE),
)
EXCEPTION_CLAUSE_PATTERN = re.compile(r"\b(?:unless|except)\b[^.!?\n]*", re.IGNORECASE)
QUOTED_LINE_PATTERN = re.compile(r"^[ \t]*>.*$", re.MULTILINE)
MAXIMUM_EXCEPTION_CHARACTERS = 300
SILENCE_NOTE_TEMPLATE = (
    'The user asked you to stay silent "{exception_clause}".'
    " This prompt is a background event, not a message from the user."
    " End this turn with no text at all unless that exception applies now."
    ' Tool calls are fine, and a status line such as "No change." counts as text.'
)
SILENCE_NOTE_WITHOUT_EXCEPTION = (
    "The user asked you to stay silent."
    " This prompt is a background event, not a message from the user."
    " End this turn with no text at all."
    ' Tool calls are fine, and a status line such as "No change." counts as text.'
)
