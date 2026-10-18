"""Constants for the bare-like Claude review profile."""

from __future__ import annotations

CLAUDE_CONFIG_DIR_ENVIRONMENT = "CLAUDE_CONFIG_DIR"
DEFAULT_CLAUDE_HOME_NAME = ".claude"
TEXT_ENCODING = "utf-8"
JSON_READ_ENCODING = "utf-8-sig"
LINE_SEPARATOR = "\n"
STANDARDS_BLOCK_GAP = LINE_SEPARATOR * 2

ALL_INSTALLED_PLUGINS_RELATIVE_PATH = ("plugins", "installed_plugins.json")
INSTALLED_PLUGINS_KEY = "plugins"
INSTALL_PATH_KEY = "installPath"
PSTACK_PLUGIN_KEY = "pstack@pstack-claude"
ACCOUNT_PROFILES_DIRECTORY_NAME = ".claude-profiles"
ALL_PLUGIN_CACHE_RELATIVE_PATH = ("plugins", "cache")
PLUGIN_KEY_SEPARATOR = "@"
MISSING_PLUGIN_MESSAGE = (
    "No install record or cached copy of {plugin} in {homes}."
    " Repair it with: claude plugin install {plugin}"
)
PLUGIN_MANIFEST_DIRECTORY = ".claude-plugin"
PLUGIN_SKILLS_DIRECTORY = "skills"
PRINCIPLE_SKILL_PREFIX = "principle-"
ALL_KEPT_PSTACK_SKILLS = (
    "poteto-mode",
    "thermo-nuclear-code-quality-review",
    "blast-radius",
    "how",
    "unslop",
    "typescript-best-practices",
)
ALL_DISABLED_BUNDLED_SKILLS = (
    "artifact-capabilities",
    "artifact-design",
    "artifact-diagramming",
    "batch",
    "claude-api",
    "claude-code-docs",
    "commit",
    "dataviz",
    "debug",
    "deep-research",
    "design",
    "design-sync",
    "doctor",
    "explain-usage",
    "fewer-permission-prompts",
    "keybindings-help",
    "loop",
    "memory-types",
    "plugin-authoring",
    "pr",
    "run",
    "run-skill-generator",
    "schedule",
    "simplify",
    "slides",
    "update-config",
    "verify",
    "workflow-authoring",
)
SKILL_OFF = "off"
ALL_STANDARD_RELATIVE_PATHS = (
    ("docs", "CODE_RULES.md"),
    ("docs", "TEST_QUALITY.md"),
    ("rules", "code-standards.md"),
    ("rules", "testing.md"),
    ("rules", "anti-corollary-tests.md"),
    ("rules", "paired-test-coverage.md"),
    ("rules", "windows-filesystem-safe.md"),
    ("rules", "plain-illustrative-docstrings.md"),
    ("rules", "docstring-prose-matches-implementation.md"),
    ("rules", "failure-blast-radius.md"),
    ("rules", "orphan-css-class.md"),
    ("rules", "doc-inventory-integrity.md"),
)
STANDARDS_HEADING = "# Code standards for this review"
STANDARD_BLOCK_TEMPLATE = '<standard source="{name}">\n{text}\n</standard>'
COMPACT_INSTRUCTIONS = (
    "This summary continues a working session that uses its tools after the "
    "summary. Quote the user's original request word for word, and keep every "
    "instruction the user gave. End with the next tool call the task needs and "
    "its arguments."
)
COMPACT_HOOK_COMMAND_TEMPLATE = (
    '"{python}" -c "import pathlib,sys; '
    "sys.stdout.write(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))\" "
    '"{instructions}"'
)
PRE_COMPACT_EVENT = "PreCompact"
PLUGIN_DIRECTORY_NAME = "pstack-review"
SETTINGS_FILENAME = "settings.json"
STANDARDS_FILENAME = "standards.md"
COMPACT_INSTRUCTIONS_FILENAME = "compact-instructions.txt"
AUTOCOMPACT_WINDOW = "100k"
AUTOCOMPACT_WINDOW_TOKENS = 100000
EMPTY_MCP_CONFIG = '{"mcpServers": {}}'
LOCAL_SETTING_SOURCE = "local"
ALL_PROFILE_ENVIRONMENT = {
    "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW": str(AUTOCOMPACT_WINDOW_TOKENS),
}
ADVISOR_OFF = "none"
ALL_ADVISOR_OFF_ENVIRONMENT = {"CLAUDE_CODE_DISABLE_ADVISOR_TOOL": "1"}
JSON_INDENT = 2
HOME_LIST_SEPARATOR = ", "
