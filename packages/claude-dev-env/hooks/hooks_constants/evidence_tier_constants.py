"""Constants for the evidence tier a pull request's changed paths give it."""

ALL_DOCS_EXTENSIONS = frozenset(
    {
        ".md",
        ".mdx",
        ".txt",
        ".rst",
        ".adoc",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".ico",
    }
)
ALL_DOCS_DIRECTORY_NAMES = frozenset({"docs"})
ALL_DOCS_DATA_EXTENSIONS = frozenset({".json", ".jsonl", ".yaml", ".yml", ".csv"})
ALL_TEST_DIRECTORY_NAMES = frozenset({"tests", "test", "__tests__"})
ALL_TEST_FILE_PREFIXES = ("test_",)
ALL_TEST_FILE_SUFFIXES = ("_test.py",)
ALL_TEST_FILE_INFIXES = (".test.", ".spec.")
ALL_TEST_FILE_NAMES = frozenset({"conftest.py"})
ALL_AGENT_SURFACE_FILE_NAMES = frozenset({"SKILL.md", "AGENTS.md", "CLAUDE.md", "hooks.json"})
ALL_AGENT_SURFACE_FILE_NAME_GLOBS = ("settings*.json",)
ALL_AGENT_SURFACE_DIRECTORY_NAMES = frozenset(
    {"skills", "rules", "agents", "commands", "system-prompts", "system_prompts", "output-styles"}
)
ALL_WORKFLOW_DIRECTORY_PARTS = (".github", "workflows")
LIVE_SURFACES_FILE_PATH = ".claude/live-surfaces.txt"
LIVE_SURFACES_COMMENT_MARKER = "#"
FOLDER_GLOB_SUFFIX = "/"
ALL_GLOB_CHARACTERS = ("*", "?", "[")
BYTE_ORDER_MARK = "\ufeff"
UNDECODABLE_BYTE_MARK = "\ufffd"
