"""Constants for the hardcoded-secret value judgment in security_checks."""

from __future__ import annotations

import re

MINIMUM_MESSAGE_WORD_COUNT: int = 3

MAXIMUM_ORDINARY_WORD_LENGTH: int = 14

MAXIMUM_CAPITALS_WORD_LENGTH: int = 5

MAXIMUM_NUMBER_WORD_LENGTH: int = 3

WORD_EDGE_PUNCTUATION: str = ".,;:!?()\"'"

LABEL_CLOSING_MARK: str = ":"

FORMAT_PLACEHOLDER_PATTERN: re.Pattern[str] = re.compile(r"\{[^{}]*\}")

ALL_PASSWORD_NAME_WORDS: frozenset[str] = frozenset({"password", "passwd", "pwd"})

ALL_AUTH_SCHEME_LEAD_WORDS: frozenset[str] = frozenset(
    {"bearer", "basic", "digest", "negotiate", "token", "key", "apikey", "bot"}
)

ALL_SENSITIVE_LABEL_WORDS: frozenset[str] = frozenset(
    {"password", "passwd", "pwd", "passphrase", "pass", "secret", "token", "key"}
)

ALL_SENTENCE_FUNCTION_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "no", "not",
        "to", "of", "in", "on", "for", "with", "from", "by", "at", "and", "or",
        "this", "that", "it", "before", "after", "has", "have", "can", "cannot",
        "will", "when", "if", "as",
    }
)

ALL_VARIABLE_NAME_SUFFIXES: tuple[str, ...] = (
    "_env",
    "_env_var",
    "_env_name",
    "_variable_name",
)

ALL_FLAG_NAME_SUFFIXES: tuple[str, ...] = ("_flag", "_option")

VARIABLE_NAME_VALUE_PATTERN: re.Pattern[str] = re.compile(
    r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*"
)

FLAG_VALUE_PATTERN: re.Pattern[str] = re.compile(
    r"-[a-zA-Z]|--[a-z][a-z0-9]*(?:-[a-z][a-z0-9]*)*"
)
