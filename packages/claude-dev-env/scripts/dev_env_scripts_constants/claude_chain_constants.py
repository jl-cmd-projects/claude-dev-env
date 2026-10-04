"""Named constants the account broker and the code review CLI share for Claude runs."""

from __future__ import annotations

ALL_USAGE_LIMIT_SIGNATURES: tuple[str, ...] = (
    "hit your session limit",
    "usage limit reached",
    "out of usage",
    "usage quota exceeded",
)
"""Case-insensitive substrings that mark a non-zero exit as a usage-limit refusal."""

CHAIN_CONFIG_ERROR_EXIT_CODE: int = 5
"""CLI exit code when the chain configuration is missing or invalid."""
