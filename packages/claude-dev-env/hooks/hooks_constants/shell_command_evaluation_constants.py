"""Names the programs that run a command held in their arguments rather than as a shell wrapper.

``eval`` and PowerShell's ``Invoke-Expression`` run their joined arguments,
``find -exec`` runs the tokens up to its terminator, and PowerShell's
``-EncodedCommand`` runs a base64 string of UTF-16LE text. PowerShell accepts
any prefix of ``-EncodedCommand`` from ``-e`` on, plus the ``-ec`` alias.
"""

from __future__ import annotations

__all__ = [
    "ALL_STRING_EVALUATING_PROGRAM_NAMES",
    "FIND_PROGRAM_NAME",
    "ALL_FIND_EXEC_ACTIONS",
    "ALL_FIND_EXEC_TERMINATORS",
    "FIND_EXEC_COMMAND_SEPARATOR",
    "ALL_POWERSHELL_PROGRAM_NAMES",
    "ENCODED_COMMAND_OPTION",
    "ENCODED_COMMAND_SHORT_ALIAS",
    "MINIMUM_ENCODED_COMMAND_PREFIX_LENGTH",
    "ENCODED_COMMAND_TEXT_ENCODING",
]

ALL_STRING_EVALUATING_PROGRAM_NAMES: frozenset[str] = frozenset(
    {"eval", "invoke-expression", "iex"}
)
FIND_PROGRAM_NAME: str = "find"
ALL_FIND_EXEC_ACTIONS: frozenset[str] = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
ALL_FIND_EXEC_TERMINATORS: frozenset[str] = frozenset({";", "\\;", "+"})
FIND_EXEC_COMMAND_SEPARATOR: str = " ; "
ALL_POWERSHELL_PROGRAM_NAMES: frozenset[str] = frozenset({"pwsh", "powershell"})
ENCODED_COMMAND_OPTION: str = "-encodedcommand"
ENCODED_COMMAND_SHORT_ALIAS: str = "-ec"
MINIMUM_ENCODED_COMMAND_PREFIX_LENGTH: int = 2
ENCODED_COMMAND_TEXT_ENCODING: str = "utf-16-le"
