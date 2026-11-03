"""Constants for the gate that stops a Bash command from removing or replacing a file under /dev.

Holds the hook name the block log records, the /dev directory and its prefix,
the leading-slash pattern that folds ``//dev`` into ``/dev``, the program names
that remove or replace a file, the redirection operator pattern that separates
a redirect target from a command operand, the target-directory option prefix
and pattern that carry a destination inside one token, and the deny message
that names the fix.
"""

from __future__ import annotations

import re

__all__ = [
    "GATE_HOOK_NAME",
    "DEV_DIRECTORY",
    "DEV_DIRECTORY_PREFIX",
    "LEADING_SLASH",
    "LEADING_SLASHES_PATTERN",
    "ALL_DEV_PATH_REMOVAL_PROGRAM_NAMES",
    "REDIRECTION_OPERATOR_PATTERN",
    "TARGET_DIRECTORY_LONG_OPTION_PREFIX",
    "SHORT_TARGET_DIRECTORY_OPTION_PATTERN",
    "DEV_PATH_REMOVAL_DENY_REASON",
]

GATE_HOOK_NAME = "dev_path_removal_gate"
DEV_DIRECTORY = "/dev"
DEV_DIRECTORY_PREFIX = DEV_DIRECTORY + "/"
LEADING_SLASH = "/"
LEADING_SLASHES_PATTERN = re.compile(r"^/{2,}")

ALL_DEV_PATH_REMOVAL_PROGRAM_NAMES: frozenset[str] = frozenset(
    {"rm", "unlink", "mv", "shred", "truncate"}
)

REDIRECTION_OPERATOR_PATTERN = re.compile(r"&?[0-9]*[<>][<>&|]*")

TARGET_DIRECTORY_LONG_OPTION_PREFIX = "--target-directory="
SHORT_TARGET_DIRECTORY_OPTION_PATTERN = re.compile(r"-[A-Za-z]*t(.+)")

DEV_PATH_REMOVAL_DENY_REASON = (
    "BLOCKED: this command removes or replaces a file under /dev, such as /dev/null, "
    "which other commands depend on. Drop the rm, unlink, mv, shred or truncate step. "
    "To discard output, redirect it with > /dev/null instead."
)
