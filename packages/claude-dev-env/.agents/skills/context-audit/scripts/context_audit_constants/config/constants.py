"""Constants for the context audit.

The enums name each trigger, depth mode, row kind, and cap.
The plain constants hold the caps, file names, patterns, and labels.
The report constants hold the headings and row templates.
"""

from __future__ import annotations

from enum import StrEnum


class Trigger(StrEnum):
    """When an agent loads a file into its context."""

    SESSION_START = "session-start"
    FOLDER_ENTER = "folder-enter"
    PATH_MATCH = "path-match"
    SKILL_INVOKE = "skill-invoke"
    ON_LINK = "on-link"
    FILE_OPEN = "file-open"


class DepthMode(StrEnum):
    """How much depth a file carries against its cap."""

    EMPTY = "empty"
    CARRIES = "carries"
    POINTS = "points"
    LEAN = "lean"
    REFERENCE = "reference"


class RowKind(StrEnum):
    """What role a loaded file plays."""

    INSTRUCTIONS = "instructions"
    IMPORT = "import"
    RULE = "rule"
    SKILL_DESCRIPTION = "skill-description"
    SKILL_BODY = "skill-body"
    SKILL_REFERENCE = "skill-reference"
    HOOK_TEXT = "hook-text"
    LINKED_DOC = "linked-doc"
    DOCSTRING = "docstring"


class CapKey(StrEnum):
    """Which line cap applies to a row."""

    ROOT_INSTRUCTIONS = "root-instructions"
    NESTED_INSTRUCTIONS = "nested-instructions"
    RULE = "rule"
    SKILL_BODY = "skill-body"
    DOCSTRING = "docstring"


ALL_LINE_CAP_BY_KEY = {
    CapKey.ROOT_INSTRUCTIONS: 20,
    CapKey.NESTED_INSTRUCTIONS: 12,
    CapKey.RULE: 20,
    CapKey.SKILL_BODY: 200,
    CapKey.DOCSTRING: 15,
}
DESCRIPTION_CHARACTER_CAP = 500
DESCRIPTION_LISTING_CHARACTER_LIMIT = 1536
CHARACTERS_PER_CAPPED_LINE = 120
BYTES_PER_ESTIMATED_TOKEN = 4
EMPTY_FILE_BYTE_LIMIT = 1
FIRST_LINK_DEPTH = 1
DESCRIPTION_LINE_COUNT = 1

ALL_SKIPPED_PATH_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
    }
)
ALL_TEXT_SUFFIXES = frozenset({".md", ".mdc", ".txt"})
PYTHON_SUFFIX = ".py"
MARKDOWN_SUFFIX = ".md"
ALL_INSTRUCTION_FILE_NAMES = frozenset({"CLAUDE.md", "AGENTS.md", "CLAUDE.local.md"})
AGENTS_FILE_NAME = "AGENTS.md"
CLAUDE_FILE_NAME = "CLAUDE.md"
AGENTS_IMPORT_LINE = "@AGENTS.md"
SKILL_FILE_NAME = "SKILL.md"
GIT_FOLDER_NAME = ".git"
CLAUDE_FOLDER_NAME = ".claude"
SKILLS_FOLDER_NAME = "skills"
PLUGINS_FOLDER_NAME = "plugins"
ALL_PROJECT_RULES_PATH_PARTS = (CLAUDE_FOLDER_NAME, "rules")
ALL_SKILL_HOME_FOLDER_NAMES = frozenset({CLAUDE_FOLDER_NAME, ".agents"})
ARCHIVE_FOLDER_MARKER = "archive"
ALL_FIXTURE_FOLDER_NAMES = frozenset({"tests", "fixtures"})
MINIMUM_SKILL_PATH_PARTS = 3

ALL_GIT_LIST_FILES_ARGUMENTS = ("git", "ls-files", "-z")
GIT_LIST_FILES_SEPARATOR = b"\0"
TEXT_ENCODING = "utf-8"
TEXT_DECODE_ERRORS = "replace"
LINE_BREAK = "\n"
NOTE_SEPARATOR = "; "

LINK_PATTERN = r"\[[^\]]*\]\(([^)\s#]+)(?:#[^)]*)?\)"
IMPORT_PATTERN = r"(?m)^\s*@([^\s]+)"
URL_SCHEME_PATTERN = r"^[a-z]+:"
FRONTMATTER_FENCE = "---"
FRONTMATTER_CLOSING_FENCE = "\n---"
FRONTMATTER_FIELD_PATTERN = r"^([A-Za-z_-]+):\s*(.*)$"
ALL_FRONTMATTER_CONTINUATION_PREFIXES = (" ", "\t", "-")
PATHS_FIELD = "paths"
DESCRIPTION_FIELD = "description"
WHEN_TO_USE_FIELD = "when_to_use"
DISABLE_MODEL_INVOCATION_FIELD = "disable-model-invocation"
TRUE_TEXT = "true"
DESCRIPTION_JOIN_TEMPLATE = "{description} {when_to_use}"

LOADER_HARNESS = "Claude Code harness"
LOADER_AGENTS_IMPORTED = "@import from CLAUDE.md"
LOADER_AGENTS_SHADOWED = (
    "not read by Claude Code (sibling CLAUDE.md, no import); Codex reads it"
)
LOADER_AGENTS_NATIVE = "Claude Code native AGENTS.md read; Codex reads it"
LOADER_IMPORT_TEMPLATE = "@import from {source}"
LOADER_RULE_PROJECT = "Claude Code harness, .claude/rules"
LOADER_RULE_INSTALLED = "Claude Code harness, installed rules folder"
LOADER_SKILL_LISTING_TEMPLATE = "skill listing, {location}"
LOADER_SKILL_INVOCATION = "skill invocation"
LOADER_SKILL_REFERENCE_TEMPLATE = "read on demand from {source}"
LOADER_LINK_TEMPLATE = "markdown link from {source}"
LOADER_DOCSTRING = "module docstring, read when an agent opens the file"
LOADER_LINKED_DOCSTRING_TEMPLATE = "module docstring linked from {source}"
LOADER_HOOK_TEXT = "SessionStart hook text"
LOCATION_PROJECT_SKILLS = "project skills folder"
LOCATION_NESTED_SKILLS = "nested .claude/skills folder"
LOCATION_INSTALLED_SKILLS = "installed skills folder"
LOCATION_PLUGIN_SKILLS = "plugin skills folder"
NOTE_CODEX_AGENTS = (
    "Codex: loaded when the working directory is at or below this folder"
)
NOTE_IMPORT = "imports load in full with the importing file"
NOTE_INSTALLED_RULE = "installed rule: loads in every project"
NOTE_DESCRIPTION_TRUNCATED = "listing truncates at 1,536 characters"
NOTE_LINK_DEPTH_TEMPLATE = "link depth {depth}"
NOTE_HOOK_TEXT = "measured from the saved hook text file"
NOTE_PLUGIN_SKILL = "loads when the plugin is installed"

REPORT_TITLE_TEMPLATE = "# Context audit: {name}"
REPORT_SUMMARY_TEMPLATE = (
    "{row_count} loaded files. Startup loads {lines} lines, about "
    "{tokens} tokens, from {files} files."
)
REPORT_TRIGGER_HEADING = "## Load by trigger"
REPORT_TRIGGER_HEADER = "| trigger | files | lines | est tokens |"
REPORT_FOUR_COLUMN_RULE = "|---|---|---|---|"
REPORT_TRIGGER_ROW_TEMPLATE = "| {trigger} | {files} | {lines} | {tokens} |"
REPORT_CARRIES_HEADING = "## Carries depth over cap"
REPORT_CARRIES_HEADER = "| path | kind | trigger | lines | cap | est tokens |"
REPORT_SIX_COLUMN_RULE = "|---|---|---|---|---|---|"
REPORT_CARRIES_ROW_TEMPLATE = (
    "| {path} | {kind} | {trigger} | {lines} | {cap} | {tokens} |"
)
REPORT_EMPTY_HEADING = "## Empty instruction stubs"
REPORT_EMPTY_ROW_TEMPLATE = "- {path} ({kind})"
REPORT_SPLIT_HEADING = "## Long skills to split"
REPORT_SPLIT_HEADER = "| path | lines | cap | est tokens |"
REPORT_SPLIT_ROW_TEMPLATE = "| {path} | {lines} | {cap} | {tokens} |"
REPORT_NONE_LINE = "None."
REPORT_ROWS_WRITTEN_TEMPLATE = "Rows written to {path}."
ALL_STUB_KINDS = frozenset({RowKind.INSTRUCTIONS, RowKind.IMPORT, RowKind.RULE})

ERROR_NOT_A_CHECKOUT_TEMPLATE = "not a git checkout: {path}"
ERROR_MISSING_FILE_TEMPLATE = "file not found: {path}"
EXIT_CODE_AUDITED = 0
EXIT_CODE_INPUT_ERROR = 2
