"""Constants for the gate that stops two Windows Python invocation failures.

Holds the interpreter option letters the option scan reads, the ``-X`` values
that turn UTF-8 mode on, the Windows ``os.name`` value, the pattern that finds
a backslash quote inside a ``python -c "..."`` argument, the hook name the
block log records, and the two deny messages that name the command to run
instead.
"""

from __future__ import annotations

import re

__all__ = [
    "GATE_HOOK_NAME",
    "WINDOWS_OS_NAME",
    "OPTION_PREFIX",
    "END_OF_OPTIONS_MARKER",
    "ISOLATED_MODE_OPTION_LETTER",
    "IMPLEMENTATION_OPTION_LETTER",
    "ALL_VALUE_OPTION_LETTERS",
    "ALL_VALUE_LONG_OPTIONS",
    "ALL_COMMAND_ENDING_OPTION_LETTERS",
    "ALL_UTF8_MODE_OPTION_VALUES",
    "PYTHON_CODE_ARGUMENT_BACKSLASH_QUOTE_PATTERN",
    "ISOLATED_PYTHON_DENY_REASON",
    "POWERSHELL_BACKSLASH_QUOTE_DENY_REASON",
]

GATE_HOOK_NAME = "python_windows_invocation_gate"
WINDOWS_OS_NAME = "nt"

OPTION_PREFIX = "-"
END_OF_OPTIONS_MARKER = "--"
ISOLATED_MODE_OPTION_LETTER = "I"
IMPLEMENTATION_OPTION_LETTER = "X"
ALL_VALUE_OPTION_LETTERS: frozenset[str] = frozenset({"X", "W", "c", "m"})
ALL_VALUE_LONG_OPTIONS: frozenset[str] = frozenset({"--check-hash-based-pycs"})
ALL_COMMAND_ENDING_OPTION_LETTERS: frozenset[str] = frozenset({"c", "m"})
ALL_UTF8_MODE_OPTION_VALUES: frozenset[str] = frozenset({"utf8", "utf8=1"})

PYTHON_CODE_ARGUMENT_BACKSLASH_QUOTE_PATTERN = re.compile(
    r"(?<![\w.\-])(?:(?:python|pypy)w?[0-9._]*t?|pyw?)(?:\.exe)?"
    r"(?:\s+[^\s\"';|&]+)*?"
    r"\s+-[A-Za-z]*c\s+\"[^\"\n]*\\\"",
    re.IGNORECASE,
)

ISOLATED_PYTHON_DENY_REASON = (
    "BLOCKED: python -I ignores PYTHONUTF8, so on Windows the interpreter writes "
    "with the console code page and non-ASCII output stops with UnicodeEncodeError: "
    "'charmap'. Add -X utf8 after -I, as in python -I -X utf8 script.py."
)
POWERSHELL_BACKSLASH_QUOTE_DENY_REASON = (
    'BLOCKED: PowerShell reads a backslash as a plain character, so \\" inside '
    'python -c "..." ends the string at that quote and Python gets cut code. '
    "Put the code in a .py file and run the file, or pass it in a single-quoted "
    "here-string: python -c @' on one line, the code on the next lines, and '@ "
    "at the start of its own line."
)
