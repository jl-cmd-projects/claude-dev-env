"""Constants for the hardcoded-secret value judgment in security_checks."""

from __future__ import annotations

import re

MINIMUM_MESSAGE_WORD_COUNT: int = 2

MINIMUM_CREDENTIAL_WORD_LENGTH: int = 8

ALL_MESSAGE_CLOSING_MARKS: tuple[str, ...] = (".", "!", "?", ":")

WORD_EDGE_PUNCTUATION: str = ".,;:!?()[]\"'`"

VALUE_ASSIGNMENT_MARK: str = "="

FORMAT_PLACEHOLDER_PATTERN: re.Pattern[str] = re.compile(r"\{[^{}]*\}")

ALL_CREDENTIAL_WORD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[0-9a-fA-F]{16,}"),
    re.compile(r"[A-Z0-9]{12,}"),
    re.compile(r".*://[^/\s@]*:[^/\s@]*@.*"),
)

ALL_REFERENCE_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z][A-Z0-9]*)+"),
    re.compile(r"--[a-z][a-z0-9]*(?:-[a-z][a-z0-9]*)*"),
)
