"""Names the programs that run a command held in their arguments rather than as a shell wrapper.

``eval`` and PowerShell's ``Invoke-Expression`` run their joined arguments,
``find -exec`` runs the tokens up to its terminator, and PowerShell's
``-EncodedCommand`` runs a base64 string of UTF-16LE text. PowerShell accepts
any prefix of ``-EncodedCommand`` from ``-e`` on, plus the ``-ec`` alias.
``Start-Process`` runs its file path with its argument list, which may be
comma-separated, and a parameter may carry its value after a colon, as in
``-ArgumentList:'pr list'``; the values of its other parameters are not part
of the command. Unwrapping stops past ``MAXIMUM_UNWRAP_DEPTH`` nested levels, so a
deeply nested command cannot exhaust the parser.
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
    "ALL_START_PROCESS_PROGRAM_NAMES",
    "ALL_START_PROCESS_NON_COMMAND_PARAMETERS",
    "START_PROCESS_PARAMETER_PREFIX",
    "START_PROCESS_ARGUMENT_SEPARATOR",
    "START_PROCESS_PARAMETER_VALUE_SEPARATOR",
    "MAXIMUM_UNWRAP_DEPTH",
    "ALL_LINE_BREAK_CHARACTERS",
    "QUOTED_LINE_BREAK_REPLACEMENT",
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
ALL_START_PROCESS_PROGRAM_NAMES: frozenset[str] = frozenset({"start-process", "saps", "start"})
ALL_START_PROCESS_NON_COMMAND_PARAMETERS: frozenset[str] = frozenset(
    {
        "-workingdirectory",
        "-verb",
        "-windowstyle",
        "-credential",
        "-redirectstandardinput",
        "-redirectstandardoutput",
        "-redirectstandarderror",
        "-environment",
    }
)
START_PROCESS_PARAMETER_PREFIX: str = "-"
START_PROCESS_ARGUMENT_SEPARATOR: str = ","
START_PROCESS_PARAMETER_VALUE_SEPARATOR: str = ":"
MAXIMUM_UNWRAP_DEPTH: int = 16
ALL_LINE_BREAK_CHARACTERS: frozenset[str] = frozenset({"\n", "\r"})
QUOTED_LINE_BREAK_REPLACEMENT: str = " "
