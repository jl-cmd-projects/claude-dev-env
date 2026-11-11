"""Patterns and note text for the pieces-per-level PreToolUse note.

Groups: the payload keys the hook reads, the commit and pull request option
names, the patterns that find verb-led clauses in a subject and topics in a
pull request body, and the note text. The note is context only.
"""

from __future__ import annotations

import re

TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
COMMAND_INPUT_KEY = "command"
WORKING_DIRECTORY_KEY = "cwd"
PRE_TOOL_USE_EVENT_NAME = "PreToolUse"
ADDITIONAL_CONTEXT_KEY = "additionalContext"
TITLE_INPUT_KEY = "title"
BODY_INPUT_KEY = "body"

EXECUTABLE_SUFFIX = ".exe"
GIT_PROGRAM_NAME = "git"
GIT_COMMIT_WORD = "commit"
GH_PROGRAM_NAME = "gh"
ALL_GH_CREATE_WORDS = ("pr", "create")
ALL_QUICK_SCAN_WORDS = ("commit", "create", "pull_request")
ALL_SHELL_CONTROL_TOKENS = frozenset({"&&", "||", ";", "|", "&", "|&"})
BACKSLASH = "\\"
DOUBLED_BACKSLASH = "\\\\"
LONG_OPTION_PREFIX = "--"
OPTION_VALUE_SEPARATOR = "="
SHORT_OPTION_PREFIX = "-"
ALL_MESSAGE_LONG_OPTIONS = frozenset({"--message"})
ALL_FILE_LONG_OPTIONS = frozenset({"--file"})
MESSAGE_SHORT_FLAG = "m"
MESSAGE_KIND = "message"
FILE_KIND = "file"
FILE_SHORT_OPTION = "-F"
STANDARD_INPUT_PATH = "-"
MESSAGE_PARAGRAPH_SEPARATOR = "\n\n"
SHORT_CLUSTER_MINIMUM_LENGTH = 2
MAXIMUM_COMMAND_CHARACTERS = 8_000
MAXIMUM_FILE_BYTES = 65_536
MAXIMUM_PROGRAM_MENTIONS = 16
MAXIMUM_WRAPPED_TEXTS = 8
MAXIMUM_SUBSTITUTION_MARKERS = 16
MAXIMUM_TITLE_CHARACTERS = 300
MAXIMUM_BODY_CHARACTERS = 20_000
MAXIMUM_LINE_CHARACTERS = 500
ANALYSIS_BUDGET_SECONDS = 0.6
STARTUP_ALLOWANCE_SECONDS = 5.0
ANALYZE_FLAG = "--analyze"
READY_LINE = b"ready\n"
CREATE_NO_WINDOW_ATTRIBUTE = "CREATE_NO_WINDOW"
PARSE_CACHE_SIZE = 2
ALL_SUBSTITUTION_MARKERS = ("$(", "`")

HEREDOC_MESSAGE_PATTERN = re.compile(
    r"^\s*\$\(\s*cat\s+<<-?\s*(?P<quote>['\"]?)(?P<tag>\w+)(?P=quote)[ \t]*\n(?P<text>.*?)\n[ \t]*(?P=tag)[ \t]*\n?\s*\)\s*$",
    re.DOTALL,
)
GIT_WORD_PATTERN = re.compile(r"\bgit\b")
COMMIT_WORD_PATTERN = re.compile(r"\bcommit\b")
HEREDOC_START_PATTERN = re.compile(
    r"(?:-\w*m|--message)[ =]+\"?\$\(\s*cat\s+<<-?\s*(?P<quote>['\"]?)(?P<tag>\w+)(?P=quote)[ \t]*$"
)
HEREDOC_TAG_GROUP = "tag"
HEREDOC_TEXT_GROUP = "text"
LINE_LEADING_WORD_PATTERN = re.compile(r"[ \t]*(\w*)")
LINE_SEPARATOR = "\n"
CARRIAGE_RETURN = "\r"
CARRIAGE_RETURN_LINE_FEED = "\r\n"
MINIMUM_HEREDOC_BODY_LINE_OFFSET = 2

CONVENTIONAL_SUBJECT_PATTERN = re.compile(
    r"^[a-z]+(?:\([^)\n]*\))?!?:[ \t]+(?P<description>\S.*)$", re.IGNORECASE
)
DESCRIPTION_GROUP = "description"
CODE_SPAN_PATTERN = re.compile(r"`[^`\n]*`")
PARENTHESIS_PATTERN = re.compile(r"\([^)\n]*\)")
QUOTED_TEXT_PATTERN = re.compile(r"\"[^\"\n]*\"|'[^'\n]*'")
MASKED_TEXT = "text"
REMOVED_TEXT = ""
MINIMUM_CLAUSE_WORD_COUNT = 1
CLAUSE_SEPARATOR_PATTERN = re.compile(r"\s*;\s*|\s*,\s*(?:and\s+)?|\s+and\s+", re.IGNORECASE)
WORD_EDGE_CHARACTERS = ".,;:!?\"'`*_()"
MINIMUM_PIECE_COUNT = 2
MAXIMUM_NAMED_PIECES = 6
MAXIMUM_PIECE_CHARACTERS = 80
PIECE_TRUNCATION_SUFFIX = "..."

ALL_ADJUNCT_WORDS = frozenset({"with", "using", "via", "without", "including", "plus"})
ALL_LEADING_ADVERBS = frozenset(
    {"always", "also", "now", "never", "then", "only", "just", "finally", "still"}
)
ALL_PIECE_VERBS = frozenset(
    {
        "accept",
        "add",
        "align",
        "allow",
        "apply",
        "ask",
        "bind",
        "block",
        "build",
        "bump",
        "cache",
        "center",
        "change",
        "check",
        "clean",
        "clear",
        "close",
        "collapse",
        "convert",
        "copy",
        "create",
        "darken",
        "delete",
        "detect",
        "disable",
        "draw",
        "drop",
        "emit",
        "enable",
        "end",
        "ensure",
        "expand",
        "extract",
        "fetch",
        "finish",
        "fix",
        "format",
        "handle",
        "hide",
        "ignore",
        "install",
        "keep",
        "lighten",
        "link",
        "list",
        "load",
        "log",
        "make",
        "mark",
        "merge",
        "move",
        "name",
        "open",
        "parse",
        "pass",
        "pin",
        "point",
        "prevent",
        "print",
        "publish",
        "put",
        "read",
        "record",
        "refactor",
        "register",
        "reject",
        "remove",
        "rename",
        "render",
        "replace",
        "require",
        "reset",
        "resize",
        "restore",
        "retry",
        "return",
        "rewrite",
        "route",
        "run",
        "save",
        "scale",
        "send",
        "set",
        "show",
        "simplify",
        "skip",
        "split",
        "start",
        "stop",
        "store",
        "support",
        "switch",
        "sync",
        "tell",
        "tidy",
        "track",
        "trim",
        "unpin",
        "update",
        "upgrade",
        "use",
        "validate",
        "verify",
        "wait",
        "wire",
        "wrap",
        "write",
    }
)

WHAT_THIS_DOES_SECTION_NAME = "What this does"
TOPIC_BULLET_PATTERN = re.compile(r"^[-*+][ \t]+(?:\*\*|__)(?P<topic>[^*_\n]+?)(?:\*\*|__)")
TOPIC_GROUP = "topic"
TOPIC_EDGE_CHARACTERS = " \t:.-"
ALL_LABEL_TOPICS = frozenset(
    {"before", "after", "why", "who notices", "now", "then", "today", "effect", "note", "context"}
)

PROOF_LEAD_CHARACTERS = " \t>-*+_`#"
PROOF_NUMBER_PATTERN = re.compile(r"^\d+[.)]\s*")
WITHOUT_LINE_PATTERN = re.compile(r"^without\b")
WITH_LINE_PATTERN = re.compile(r"^with\b(?!out)")
WITH_SAME_LINE_PATTERN = re.compile(r"[;,.]\s+[*_`]*with\b(?!out)")
MINIMUM_PROOF_PAIR_COUNT = 2

COMMIT_KIND = "commit"
PULL_REQUEST_KIND = "pull request"
PIECE_SEPARATOR = "; "
MORE_PIECES_TEMPLATE = "and {count} more"
PROOF_PAIRS_PIECE_TEMPLATE = "{count} without/with proof pairs under Proof in practice"
QUOTED_PIECE_TEMPLATE = '"{piece}"'

COMMIT_NEXT_COMMAND = (
    "The commit that is running holds every piece. To split it, run `git reset --soft HEAD~1`, "
    "then `git add <paths of the first piece>` and commit, then put the next piece on its own "
    "level with `gt create` (or `git switch -c <next-branch>` without Graphite)."
)
PULL_REQUEST_NEXT_COMMAND = (
    "Next command: `gt create` (or `git switch -c <next-branch>` from the previous level) for "
    "each further piece, then open one pull request per level with `gh pr create --base "
    "<previous-branch>`."
)
NOTE_TEMPLATE = (
    "Your own words name several pieces in this {kind}: {pieces}. Each piece gets its own "
    "commit and its own stack level, committed as its verifier passes, so a reviewer reads "
    "one purpose at a time. {next_command} This note is context only, and the {kind} runs."
)
ALL_NEXT_COMMAND_BY_KIND = {
    COMMIT_KIND: COMMIT_NEXT_COMMAND,
    PULL_REQUEST_KIND: PULL_REQUEST_NEXT_COMMAND,
}
