"""Constants for the hardcoded-secret value judgment in security_checks."""

from __future__ import annotations

import re

MINIMUM_MESSAGE_WORD_COUNT: int = 4

MAXIMUM_ORDINARY_WORD_LENGTH: int = 14

MAXIMUM_CAPITALS_WORD_LENGTH: int = 5

MAXIMUM_CAPITALS_WORD_COUNT: int = 1

MINIMUM_GROUP_WORD_LENGTH: int = 4

MAXIMUM_SHORT_WORD_LENGTH: int = 2

MINIMUM_GROUP_RUN_LENGTH: int = 3

MINIMUM_VARIABLE_SEGMENT_COUNT: int = 2

MINIMUM_FLAG_SEGMENT_COUNT: int = 1

WORD_SEPARATOR: str = " "

WORD_EDGE_PUNCTUATION: str = ".,;:!?()"

LABEL_CLOSING_MARK: str = ":"

NAME_SEGMENT_SEPARATOR: str = "_"

FLAG_SEGMENT_SEPARATOR: str = "-"

FLAG_LEAD: str = "--"

FORMAT_PLACEHOLDER_PATTERN: re.Pattern[str] = re.compile(
    r"\{(?:[a-z]+(?:_[a-z]+)*)?(?:![rsa])?(?::[<>^]?[0-9,.]*[a-z%]?)?\}"
)

UNPRONOUNCEABLE_RUN_PATTERN: re.Pattern[str] = re.compile(
    r"[b-df-hj-np-tv-xz]{5,}", re.IGNORECASE
)

ALL_PASSWORD_NAME_WORDS: frozenset[str] = frozenset(
    {"password", "passwd", "pwd", "passphrase", "passcode", "phrase", "answer"}
)

ALL_PASSWORD_NAME_SEGMENTS: frozenset[str] = frozenset({"pass"})

ALL_AUTH_SCHEME_LEAD_WORDS: frozenset[str] = frozenset(
    {"bearer", "basic", "digest", "negotiate", "token", "key", "apikey", "bot"}
)

ALL_AUTH_SCHEME_WORDS: frozenset[str] = frozenset(
    {"bearer", "basic", "digest", "negotiate"}
)

ALL_SENTENCE_FUNCTION_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "no", "not",
        "to", "of", "in", "on", "for", "with", "from", "by", "at", "and", "or",
        "this", "that", "it", "before", "after", "has", "have", "can", "cannot",
        "will", "when", "if", "as", "do", "so", "up",
    }
)

ALL_POINTER_VALUE_WORDS: tuple[str, ...] = (
    "token",
    "key",
    "secret",
    "auth",
    "password",
    "credential",
)

ALL_VARIABLE_NAME_SUFFIXES: tuple[str, ...] = (
    "_env",
    "_env_var",
    "_env_name",
    "_variable_name",
)

ALL_FLAG_NAME_SUFFIXES: tuple[str, ...] = ("_flag", "_option")

VARIABLE_NAME_SEGMENT_PATTERN: re.Pattern[str] = re.compile(r"[A-Z]{1,12}")

FLAG_SEGMENT_PATTERN: re.Pattern[str] = re.compile(r"[a-z]{1,12}")
