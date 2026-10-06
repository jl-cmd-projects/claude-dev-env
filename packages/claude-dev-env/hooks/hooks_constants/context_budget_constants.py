"""Configuration for the context budget check shared by the write hook and the lint."""

from __future__ import annotations

import re

POLICY_RELATIVE_PATH = ".claude/context-budget.json"
ALL_POLICY_PATH_PARTS: tuple[str, ...] = (".claude", "context-budget.json")
GIT_MARKER_NAME = ".git"
UTF8_ENCODING = "utf-8"

SECTION_DETAIL_LINE_LIMIT_KEY = "section_detail_line_limit"
KINDS_KEY = "kinds"
HOOKS_KEY = "hooks"
BASELINE_KEY = "baseline"
BASELINE_FILES_KEY = "files"
BASELINE_HOOKS_KEY = "hooks"
NAME_KEY = "name"
PATTERNS_KEY = "patterns"
LINE_LIMIT_KEY = "line_limit"
SECTION_RULE_KEY = "section_rule"
COMMAND_KEY = "command"
STDIN_KEY = "stdin"
CHAR_LIMIT_KEY = "char_limit"
LINES_KEY = "lines"
SECTIONS_KEY = "sections"

DEFAULT_SECTION_DETAIL_LINE_LIMIT = 6
ALL_DEFAULT_KIND_SPECS: tuple[tuple[str, tuple[str, ...], int, bool], ...] = (
    ("skill entry", ("**/SKILL.md",), 200, True),
    ("agent instructions", ("**/AGENTS.md", "**/CLAUDE.md"), 60, True),
    ("rule", ("**/rules/*.md",), 30, True),
)

TOP_SECTION_HEADING = "(top)"
FILE_SCOPE = "file"
FRONTMATTER_DELIMITER = "---"
TABLE_ROW_PREFIX = "|"
PATH_SEPARATOR = "/"
RECURSIVE_GLOB_SEGMENT = "**"
KEBAB_SEPARATOR = "-"
ATX_HEADING_PATTERN = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+(?P<text>.*?))?(?:[ \t]+#+)?[ \t]*$")
FENCE_OPEN_PATTERN = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})")
PURE_LINK_LIST_ITEM_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\[[^\]]*\]\([^)]*\)\s*$")
LINK_TARGET_PATTERN = re.compile(r"\[[^\]]*\]\(\s*<?(?P<target>[^)\s>]+)")
ALL_NON_RELATIVE_TARGET_PREFIXES: tuple[str, ...] = (
    "http:",
    "https:",
    "mailto:",
    "#",
    "//",
)
NON_KEBAB_CHARACTER_PATTERN = re.compile(r"[^a-z0-9]+")

ENV_COMMAND_NAME = "env"
ENV_ASSIGNMENT_SEPARATOR = "="
ALL_PYTHON_COMMAND_NAMES: frozenset[str] = frozenset({"python", "python3"})
ALL_INHERITED_ENVIRONMENT_NAMES: tuple[str, ...] = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "COMSPEC",
    "TEMP",
    "TMP",
)
ALL_HOME_ENVIRONMENT_NAMES: tuple[str, ...] = ("HOME", "USERPROFILE")
HOOK_TIMEOUT_SECONDS = 30
HOOK_SPECIFIC_OUTPUT_KEY = "hookSpecificOutput"
ADDITIONAL_CONTEXT_KEY = "additionalContext"
SYSTEM_MESSAGE_KEY = "systemMessage"

MESSAGE_PREFIX = "{path}: context-budget: "
SECTION_FINDING_TEMPLATE = (
    MESSAGE_PREFIX + 'section "{heading}" has {count} detail lines and no pointer (limit {limit}). '
    "Move it to a reference file, for example reference/{kebab}.md, "
    "and leave a one-line pointer to it."
)
FILE_FINDING_TEMPLATE = (
    MESSAGE_PREFIX + "file has {count} lines ({kind} limit {limit}). "
    "Move detail sections to reference files and leave one-line pointers."
)
GROWN_FINDING_TEMPLATE = (
    MESSAGE_PREFIX + "file grew from {recorded} to {count} lines; this file is on the over-budget "
    "list and may only shrink. Move detail sections to reference files until it "
    "has {recorded} lines or fewer."
)
RATCHET_LOWER_TEMPLATE = (
    MESSAGE_PREFIX + "file is below its over-budget entry ({recorded_lines} lines, sections "
    "{recorded_sections}); it now has {count} lines and sections {sections}. "
    "Set its entry in " + POLICY_RELATIVE_PATH + " to {entry_json} so the list "
    "keeps shrinking."
)
RATCHET_REMOVE_TEMPLATE = (
    MESSAGE_PREFIX + "file is within budget now ({count} lines, no over-limit section). "
    "Remove its entry from " + POLICY_RELATIVE_PATH + " so the list keeps shrinking."
)
SHRINK_ONLY_TEMPLATE = (
    MESSAGE_PREFIX + "{change}; the over-budget list may only shrink. Restore the prior value "
    "and shrink the context instead."
)
HOOK_FINDING_TEMPLATE = (
    'context-budget: hook "{name}" injects {count} characters (limit {limit}). '
    "Move the detail to a skill or reference file the agent opens on demand and "
    "inject only a pointer to it."
)
HOOK_GROWN_TEMPLATE = (
    'context-budget: hook "{name}" injects {count} characters, over its baseline '
    "of {recorded}; the over-budget list may only shrink. Move the detail to a "
    "skill or reference file the agent opens on demand."
)
CHANGE_ADDS_FILE = 'baseline adds file "{subject}"'
CHANGE_RAISES_FILE = 'baseline raises "{subject}" from {prior} to {current} lines'
CHANGE_ADDS_SECTION = 'baseline adds section "{heading}" to "{subject}"'
CHANGE_ADDS_HOOK = 'baseline adds hook "{subject}"'
CHANGE_RAISES_HOOK = 'baseline raises hook "{subject}" from {prior} to {current} characters'
CHANGE_RAISES_SECTION_LIMIT = SECTION_DETAIL_LINE_LIMIT_KEY + " rises from {prior} to {current}"
CHANGE_RAISES_LINE_LIMIT = 'kind "{subject}" line_limit rises from {prior} to {current}'
CHANGE_DISABLES_SECTION_RULE = 'kind "{subject}" turns its section rule off'
CHANGE_DELETES_KIND = 'kind "{subject}" is deleted'
CHANGE_RAISES_CHAR_LIMIT = 'hook "{subject}" char_limit rises from {prior} to {current}'
NO_LINE_LIMIT_TEXT = "none"

POLICY_ERROR_NOT_OBJECT = "policy must be a JSON object"
POLICY_ERROR_BAD_FIELD = "field {field} has the wrong type"

JSON_INDENT = 2

TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
FILE_PATH_KEY = "file_path"
CONTENT_KEY = "content"
CWD_KEY = "cwd"
CONTEXT_BUDGET_BLOCK_PREFIX = "BLOCKED: [CONTEXT_BUDGET] "
CONTEXT_BUDGET_REASON_SEPARATOR = " "
CONTEXT_BUDGET_NOTICE = (
    "Context budget check: keep entry files a short map and move detail to "
    "reference files the agent opens on demand."
)
CONTEXT_BUDGET_HOOK_NAME = "context_budget_blocker.py"
