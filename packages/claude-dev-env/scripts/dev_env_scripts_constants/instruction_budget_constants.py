"""Constants for the instruction-file budget, personal-name, and link-nesting checks."""

from __future__ import annotations

import re

from dev_env_scripts_constants.private_term_constants import PrivateTermDigest

INSTRUCTION_BUDGET_CONFIG_FILE_NAME: str = "instruction-budget.json"
MAX_LAUNCH_BYTES_KEY: str = "max_launch_bytes"
MAX_LINK_HOPS_KEY: str = "max_link_hops"
RULES_DIRS_KEY: str = "rules_dirs"
DEFAULT_MAX_LINK_HOPS: int = 2
DEFAULT_RULES_DIR_RELATIVE_PATH: str = ".claude/rules"

CLAUDE_FOLDER_NAME: str = ".claude"
CLAUDE_INSTRUCTION_FILE_NAME: str = "CLAUDE.md"
AGENTS_INSTRUCTION_FILE_NAME: str = "AGENTS.md"
SKILL_FILE_NAME: str = "SKILL.md"
ALL_ENTRY_INSTRUCTION_FILE_NAMES: tuple[str, ...] = (
    CLAUDE_INSTRUCTION_FILE_NAME,
    AGENTS_INSTRUCTION_FILE_NAME,
)
ALL_INSTRUCTION_FILE_NAMES: frozenset[str] = frozenset(
    {*ALL_ENTRY_INSTRUCTION_FILE_NAMES, SKILL_FILE_NAME}
)
MARKDOWN_SUFFIX: str = ".md"
FRONTMATTER_DELIMITER: str = "---"
PATHS_FRONTMATTER_PREFIX: str = "paths:"
TEXT_ENCODING: str = "utf-8"
INSTRUCTION_TEXT_ENCODING: str = "utf-8-sig"
ALL_SKIPPED_DIRECTORY_NAMES: frozenset[str] = frozenset(
    {".git", "node_modules", ".venv", "__pycache__"}
)

IMPORT_LINE_PATTERN: re.Pattern[str] = re.compile(r"^@(\S+)\s*$", re.MULTILINE)
MARKDOWN_LINK_PATTERN: re.Pattern[str] = re.compile(
    r'\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)'
)
FENCED_BLOCK_PATTERN: re.Pattern[str] = re.compile(
    r"^ {0,3}(`{3,}|~{3,}).*?(?:^ {0,3}\1[`~]*[ \t\r]*$|\Z)", re.MULTILINE | re.DOTALL
)
EXTERNAL_TARGET_PATTERN: re.Pattern[str] = re.compile(r"^(https?:|mailto:|#)")
ANCHOR_SEPARATOR: str = "#"
LINE_NUMBER_SEPARATOR: str = ", "
PERSONAL_NAME_TOKEN_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z0-9_]+")
ALL_NAMED_PEOPLE_DIGESTS: frozenset[PrivateTermDigest] = frozenset(
    {
        PrivateTermDigest(
            length=3,
            sha256="bb472edb86809a761936d90c70aeb4346618aa71da7a00c16e334863499108fd",
        ),
        PrivateTermDigest(
            length=7,
            sha256="dfef5e53f9848472560a3e680a310d097ecc75919740646df38d31cab7aa07ac",
        ),
    }
)

BUDGET_FINDING_MESSAGE_TEMPLATE: str = (
    "always-loaded instruction bytes are {total}, over the cap of {cap}. "
    "Move detail into a linked reference page."
)
PERSONAL_NAME_FINDING_MESSAGE_TEMPLATE: str = (
    "names a person on line(s) {lines}. Write 'the user' or name no one."
)
NESTING_FINDING_MESSAGE_TEMPLATE: str = (
    "is {hops} link hops from an entry file, over the cap of {cap}. "
    "Link it from an entry file directly."
)
MISSING_CONFIG_MESSAGE_TEMPLATE: str = (
    "no {config} at the repository root, so there is no budget to check."
)
MALFORMED_CONFIG_MESSAGE_TEMPLATE: str = "does not hold valid limits: {error}"
FINDING_LINE_TEMPLATE: str = "{file_path}: [{rule_id}] {message}"
PASSED_MESSAGE: str = "instruction-budget: passed"
