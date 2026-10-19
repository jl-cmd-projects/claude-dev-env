"""Named values for the role-shaped default rewrite of a first task."""

from __future__ import annotations

__all__ = [
    "ALL_EXAMPLE_SENTENCE_MARKERS",
    "DEFAULT_BLOCKER_TEMPLATE",
    "DEFAULT_CLOSING_LINE",
    "DEFAULT_SCOPE_MAX_CHARACTERS",
    "DEFAULT_TASK_HEADING",
    "ALL_EXAMPLE_END_MARKERS",
    "EXAMPLE_LEAD_PUNCTUATION",
    "EXAMPLE_LIST_SEPARATOR",
    "EXAMPLE_MARKER_ALTERNATION_SEPARATOR",
    "EXAMPLE_MARKER_PATTERN_TEMPLATE",
    "SCOPE_CLIPPED_SUFFIX",
    "SENTENCE_BREAK_PATTERN",
    "WORD_SEPARATOR",
]

ALL_EXAMPLE_SENTENCE_MARKERS: tuple[str, ...] = ("for example", "for instance", "e.g.", "such as")
EXAMPLE_LEAD_PUNCTUATION: str = " ,:;-"
EXAMPLE_MARKER_ALTERNATION_SEPARATOR: str = "|"
EXAMPLE_MARKER_PATTERN_TEMPLATE: str = r"(?<!\w)(?:{alternatives})(?!\w)"
EXAMPLE_LIST_SEPARATOR: str = "; "
WORD_SEPARATOR: str = " "
ALL_EXAMPLE_END_MARKERS: tuple[str, ...] = (", and ", ", but ", ", then ", ", so ", ";", ")")
SENTENCE_BREAK_PATTERN: str = r"(?<=[.!?])\s+(?=[A-Z0-9\"'`(\[])"
DEFAULT_SCOPE_MAX_CHARACTERS: int = 240
SCOPE_CLIPPED_SUFFIX: str = "(the rest is in the task below)"
DEFAULT_TASK_HEADING: str = "Task as given:"
DEFAULT_BLOCKER_TEMPLATE: str = (
    "the scope names something the task also gives as an example ({examples}); "
    "confirm the job is only that case before narrowing to it"
)
DEFAULT_CLOSING_LINE: str = (
    "Work the whole scope as a leading practitioner in this field would, "
    "keep every hard constraint, and then do exactly that job."
)
