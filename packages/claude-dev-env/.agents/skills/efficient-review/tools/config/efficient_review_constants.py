"""Constants for the /efficient-review skill runner."""

from __future__ import annotations

import re
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
DEFAULTS_PATH = SKILL_ROOT / "defaults.json"
SETTINGS_PATH = SKILL_ROOT / "settings.json"
SETTINGS_ENVIRONMENT = "EFFICIENT_REVIEW_SETTINGS"
TEXT_ENCODING = "utf-8"
JSON_READ_ENCODING = "utf-8-sig"
LINE_SEPARATOR = "\n"
LIST_SEPARATOR = ", "
JSON_INDENT = 2
STDERR_TAIL_CHARACTERS = 4000
CLAUDE_CONFIG_DIR_ENVIRONMENT = "CLAUDE_CONFIG_DIR"
CODEX_HOME_ENVIRONMENT = "CODEX_HOME"
CODEX_EXECUTABLE_ENVIRONMENT = "CODEX_EXECUTABLE"
NESTED_SESSION_ENVIRONMENT = "CLAUDECODE"
PATH_ENVIRONMENT = "PATH"

ALL_DEFAULT_KEYS = (
    "model",
    "effort",
    "level",
    "prompt",
    "base",
    "profile",
    "advisor",
    "validator",
    "mode",
    "timeout_minutes",
)
ALL_OVERRIDE_KEYS = ("model", "effort", "level", "base")
OVERRIDE_SEPARATOR = "="
LEVEL_KEY = "level"

MODE_HEADLESS = "headless"
MODE_AUTO = "auto"
ALL_MODE_WORDS = (MODE_HEADLESS, MODE_AUTO)
ACCOUNT_NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")

ALL_CLAUDE_FAMILIES = ("haiku", "sonnet", "opus")
ALL_CODEX_FAMILIES = ("sol", "luna")
HARNESS_CLAUDE = "claude"
HARNESS_CODEX = "codex"

ACCOUNT_SOURCE_LAUNCHERS = "launchers"
ACCOUNT_SOURCE_ROSTER = "roster"
BROKER_WAIT_EXIT_CODE = 3

PROFILE_DIRECTORY_NAME = "profile"
MCP_CONFIG_FLAG = "--mcp-config"
MCP_CONFIG_FILENAME = "mcp.json"
ALL_DIFF_ARGUMENTS = ("diff", "--no-ext-diff", "--no-textconv", "--no-color")
ALL_HEAD_ARGUMENTS = ("rev-parse", "HEAD")
CODEX_ACCOUNT_LABEL = "codex-home"
CODEX_EXECUTABLE_NAME = "codex"
CODEX_RUN_HOME_NAME = "codex-home"
CODEX_LOGIN_FILENAME = "auth.json"
CODEX_DISCOVERY_TIMEOUT_SECONDS = 120.0
SECONDS_PER_MINUTE = 60
REVIEW_FILENAME = "review.md"
SYSTEM_PROMPT_FILENAME = "system-prompt.md"
CONFIRMED_FINDINGS_INSTRUCTION = (
    "Report every finding you confirmed against the code, and only those. "
    "This review has no minimum finding count: ignore any target number of "
    "findings in the review recipe. An empty findings list is a valid review. "
    "End the review with a ```json block holding a list of findings, each with "
    "file, line, priority, summary and failure_scenario, and an empty list "
    "when there are none. Priority is 0 for a defect that blocks the merge, 1 "
    "for a defect to fix before the merge, 2 for a fix that can follow the "
    "merge, and 3 for a style nit."
)
SAVE_DIRECTORY_PREFIX = "efficient-review-"
WORK_DIRECTORY_PREFIX = "efficient-review-work-"
RECORD_FILENAME = "review.json"
PLAN_COMMAND = "plan"
PARENT_WALK_LIMIT = 12
