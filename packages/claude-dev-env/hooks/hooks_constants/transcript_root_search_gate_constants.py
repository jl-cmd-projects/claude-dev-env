"""Constants for the gate that stops walks and content searches over a Claude transcript root.

Holds the transcript root pattern and the marker word every root path holds,
the path parts the gate joins and splits on, the shell assignment and variable
reference patterns, the directory-change programs, the option grammar of each
POSIX search program and the PowerShell switches, the Grep and Glob tool names
and input keys, the hook name the block log records, and the deny message that
names the list-then-read fix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "TRANSCRIPT_ROOT_PATTERN",
    "TRANSCRIPT_ROOT_MARKER",
    "PATH_SEPARATOR",
    "WINDOWS_PATH_SEPARATOR",
    "CURRENT_DIRECTORY",
    "POWERSHELL_PATH_LIST_SEPARATOR",
    "WILDCARD_ONLY_SEGMENT_PATTERN",
    "RECURSIVE_GLOB_SEGMENT",
    "ABSOLUTE_PATH_PATTERN",
    "SHELL_ASSIGNMENT_PATTERN",
    "SPACED_ASSIGNMENT_NAME_PATTERN",
    "SPACED_ASSIGNMENT_OPERATOR",
    "SPACED_ASSIGNMENT_TOKEN_COUNT",
    "ALL_ASSIGNMENT_PREFIX_WORDS",
    "SHELL_VARIABLE_SIGIL",
    "SHELL_VARIABLE_REFERENCE_TEMPLATE",
    "ALL_CHANGE_DIRECTORY_PROGRAM_NAMES",
    "ALL_HOME_DEFAULT_CHANGE_DIRECTORY_PROGRAM_NAMES",
    "ALL_PUSH_DIRECTORY_PROGRAM_NAMES",
    "ALL_POP_DIRECTORY_PROGRAM_NAMES",
    "HOME_DIRECTORY",
    "FIND_MAXIMUM_DEPTH_OPTION",
    "ALL_SHALLOW_DEPTH_VALUES",
    "OPTION_PREFIX",
    "LONG_OPTION_PREFIX",
    "END_OF_OPTIONS_TOKEN",
    "GLUED_OPTION_VALUE_SEPARATOR",
    "RECURSE_DIRECTORIES_ACTION",
    "PosixSearchGrammar",
    "ALL_GREP_PROGRAM_NAMES",
    "GREP_GRAMMAR",
    "ALL_INDEXED_SEARCH_PROGRAM_NAMES",
    "INDEXED_SEARCH_GRAMMAR",
    "UNIX_LS_GRAMMAR",
    "TREE_PROGRAM_NAME",
    "TREE_GRAMMAR",
    "POWERSHELL_TOOL_NAME",
    "POWERSHELL_DEPTH_OPTION",
    "POWERSHELL_NON_RECURSIVE_DEPTH",
    "ALL_POWERSHELL_SWITCH_OPTIONS",
    "POWERSHELL_GLUED_VALUE_SEPARATOR",
    "POWERSHELL_MINIMUM_ABBREVIATION_LENGTH",
    "ALL_POWERSHELL_ABBREVIABLE_OPTIONS",
    "ALL_SELECT_STRING_PROGRAM_NAMES",
    "GLOB_TOOL_NAME",
    "ALL_FILE_SEARCH_TOOL_NAMES",
    "TOOL_INPUT_PATH_KEY",
    "TOOL_INPUT_PATTERN_KEY",
    "TOOL_INPUT_COMMAND_KEY",
    "PAYLOAD_TOOL_NAME_KEY",
    "PAYLOAD_TOOL_INPUT_KEY",
    "PAYLOAD_CWD_KEY",
    "GATE_HOOK_NAME",
    "TRANSCRIPT_ROOT_DENY_REASON_TEMPLATE",
]

TRANSCRIPT_ROOT_PATTERN = re.compile(
    r"(?:^|/)(?:\.claude|\.claude-profiles/[^/]+|\.claude-[^/]+)/projects(?=/|$)",
    re.IGNORECASE,
)
TRANSCRIPT_ROOT_MARKER = "projects"
PATH_SEPARATOR = "/"
WINDOWS_PATH_SEPARATOR = "\\"
CURRENT_DIRECTORY = "."
POWERSHELL_PATH_LIST_SEPARATOR = ","
WILDCARD_ONLY_SEGMENT_PATTERN = re.compile(r"[*?.]*\*[*?.]*")
RECURSIVE_GLOB_SEGMENT = "**"
ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:[A-Za-z]:|/|\\|~|\$)")

SHELL_ASSIGNMENT_PATTERN = re.compile(
    r"^\$?(?:env:)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.+)$"
)
SPACED_ASSIGNMENT_NAME_PATTERN = re.compile(r"^\$(?:env:)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)$")
SPACED_ASSIGNMENT_OPERATOR = "="
SPACED_ASSIGNMENT_TOKEN_COUNT = 3
ALL_ASSIGNMENT_PREFIX_WORDS: frozenset[str] = frozenset({"export", "local", "declare", "set"})
SHELL_VARIABLE_SIGIL = "$"
SHELL_VARIABLE_REFERENCE_TEMPLATE = r"\$(?:\{{{name}\}}|(?:env:)?{name}(?![A-Za-z0-9_]))"
ALL_CHANGE_DIRECTORY_PROGRAM_NAMES: frozenset[str] = frozenset(
    {"cd", "chdir", "pushd", "set-location", "sl", "push-location"}
)
ALL_HOME_DEFAULT_CHANGE_DIRECTORY_PROGRAM_NAMES: frozenset[str] = frozenset(
    {"cd", "chdir", "set-location", "sl"}
)
ALL_PUSH_DIRECTORY_PROGRAM_NAMES: frozenset[str] = frozenset({"pushd", "push-location"})
ALL_POP_DIRECTORY_PROGRAM_NAMES: frozenset[str] = frozenset({"popd", "pop-location"})
HOME_DIRECTORY = "~"

FIND_MAXIMUM_DEPTH_OPTION = "-maxdepth"
ALL_SHALLOW_DEPTH_VALUES: frozenset[str] = frozenset({"0", "1"})
OPTION_PREFIX = "-"
LONG_OPTION_PREFIX = "--"
END_OF_OPTIONS_TOKEN = "--"
GLUED_OPTION_VALUE_SEPARATOR = "="
RECURSE_DIRECTORIES_ACTION = "recurse"


@dataclass(frozen=True)
class PosixSearchGrammar:
    """How one POSIX search program reads its options and paths.

    Attributes:
        is_recursive_by_default: True when the program walks below its paths with no option.
        all_recurse_options: Options that turn on recursion, such as ``-r`` or ``--recursive``.
        all_value_letters: Short option letters that take a value, glued or as the next token.
        all_value_options: Long options that take the next token as their value.
        all_depth_options: Options whose value limits the depth; a shallow value stops recursion.
        all_recurse_value_options: Options whose value ``recurse`` turns on recursion.
        all_pattern_options: Options that supply the pattern or list files with no pattern,
            so no positional pattern comes first.
        takes_pattern_positional: True when the first positional is the pattern.
    """

    is_recursive_by_default: bool
    all_recurse_options: frozenset[str] = frozenset()
    all_value_letters: frozenset[str] = frozenset()
    all_value_options: frozenset[str] = frozenset()
    all_depth_options: frozenset[str] = frozenset()
    all_recurse_value_options: frozenset[str] = frozenset()
    all_pattern_options: frozenset[str] = frozenset()
    takes_pattern_positional: bool = False


ALL_GREP_PROGRAM_NAMES: frozenset[str] = frozenset({"grep", "egrep", "fgrep"})
GREP_GRAMMAR = PosixSearchGrammar(
    is_recursive_by_default=False,
    all_recurse_options=frozenset({"-r", "-R", "--recursive", "--dereference-recursive"}),
    all_value_letters=frozenset({"e", "f", "m", "A", "B", "C", "d", "D"}),
    all_value_options=frozenset(
        {
            "--regexp",
            "--file",
            "--max-count",
            "--after-context",
            "--before-context",
            "--context",
            "--directories",
            "--devices",
            "--include",
            "--exclude",
            "--exclude-dir",
            "--exclude-from",
            "--label",
            "--group-separator",
        }
    ),
    all_recurse_value_options=frozenset({"-d", "--directories"}),
    all_pattern_options=frozenset({"-e", "-f", "--regexp", "--file"}),
    takes_pattern_positional=True,
)
ALL_INDEXED_SEARCH_PROGRAM_NAMES: frozenset[str] = frozenset({"rg", "ag", "ack", "fd", "fdfind"})
INDEXED_SEARCH_GRAMMAR = PosixSearchGrammar(
    is_recursive_by_default=True,
    all_value_letters=frozenset(
        {"e", "f", "g", "t", "T", "m", "A", "B", "C", "d", "j", "M", "r", "E", "x", "X", "S", "G"}
    ),
    all_value_options=frozenset(
        {
            "--regexp",
            "--file",
            "--glob",
            "--iglob",
            "--type",
            "--type-not",
            "--type-add",
            "--max-count",
            "--after-context",
            "--before-context",
            "--context",
            "--max-depth",
            "--maxdepth",
            "--depth",
            "--threads",
            "--max-columns",
            "--max-filesize",
            "--sort",
            "--sortr",
            "--encoding",
            "--pre",
            "--pre-glob",
            "--engine",
            "--path-separator",
            "--replace",
            "--color",
            "--colors",
            "--ignore",
            "--file-search-regex",
            "--extension",
            "--exclude",
            "--exec",
            "--exec-batch",
            "--size",
            "--changed-within",
            "--changed-before",
        }
    ),
    all_depth_options=frozenset({"-d", "--max-depth", "--maxdepth", "--depth"}),
    all_pattern_options=frozenset({"-e", "-f", "--regexp", "--file", "--files"}),
    takes_pattern_positional=True,
)
UNIX_LS_GRAMMAR = PosixSearchGrammar(
    is_recursive_by_default=False,
    all_recurse_options=frozenset({"-R", "--recursive"}),
    all_value_letters=frozenset({"I", "w", "T"}),
    all_value_options=frozenset(
        {"--ignore", "--hide", "--width", "--tabsize", "--sort", "--format", "--time-style"}
    ),
)
TREE_PROGRAM_NAME = "tree"
TREE_GRAMMAR = PosixSearchGrammar(
    is_recursive_by_default=True,
    all_value_letters=frozenset({"L", "P", "I", "o", "H", "T"}),
    all_value_options=frozenset({"--filelimit", "--charset", "--sort", "--timefmt"}),
    all_depth_options=frozenset({"-L"}),
)

POWERSHELL_TOOL_NAME = "PowerShell"
POWERSHELL_DEPTH_OPTION = "-depth"
POWERSHELL_NON_RECURSIVE_DEPTH = "0"
ALL_POWERSHELL_SWITCH_OPTIONS: frozenset[str] = frozenset(
    {
        "-recurse",
        "-r",
        "-rec",
        "-file",
        "-directory",
        "-ad",
        "-af",
        "-ah",
        "-ar",
        "-as",
        "-force",
        "-name",
        "-hidden",
        "-system",
        "-readonly",
        "-followsymlink",
        "-list",
        "-simplematch",
        "-casesensitive",
        "-notmatch",
        "-allmatches",
        "-quiet",
        "-raw",
        "-noemphasis",
        "-wait",
        "-verbose",
        "-vb",
        "-debug",
        "-db",
        "-whatif",
        "-wi",
        "-confirm",
        "-cf",
        "-usetransaction",
        "-usetx",
    }
)
POWERSHELL_GLUED_VALUE_SEPARATOR = ":"
POWERSHELL_MINIMUM_ABBREVIATION_LENGTH = 4
ALL_POWERSHELL_ABBREVIABLE_OPTIONS: frozenset[str] = ALL_POWERSHELL_SWITCH_OPTIONS | frozenset(
    {POWERSHELL_DEPTH_OPTION, "-path", "-literalpath", "-filter", "-include", "-exclude"}
)
ALL_SELECT_STRING_PROGRAM_NAMES: frozenset[str] = frozenset({"select-string", "sls"})

GLOB_TOOL_NAME = "Glob"
ALL_FILE_SEARCH_TOOL_NAMES: frozenset[str] = frozenset({"Grep", GLOB_TOOL_NAME})
TOOL_INPUT_PATH_KEY = "path"
TOOL_INPUT_PATTERN_KEY = "pattern"
TOOL_INPUT_COMMAND_KEY = "command"
PAYLOAD_TOOL_NAME_KEY = "tool_name"
PAYLOAD_TOOL_INPUT_KEY = "tool_input"
PAYLOAD_CWD_KEY = "cwd"

GATE_HOOK_NAME = "transcript_root_search_gate.py"

TRANSCRIPT_ROOT_DENY_REASON_TEMPLATE = (
    "BLOCKED: this call walks or searches every transcript under `{root}`. "
    "A Claude transcript root holds thousands of JSONL session files, so a "
    "recursive walk or content search there runs for minutes and times out. "
    "Scope the search: list the project folders by name first, for example "
    '`Get-ChildItem "{root}" -Directory -Filter "*<session id fragment>*"` or '
    '`Glob(pattern="*<session id fragment>*", path="{root}")`, then read the one '
    "transcript in the matching folder, or search inside that one folder."
)
