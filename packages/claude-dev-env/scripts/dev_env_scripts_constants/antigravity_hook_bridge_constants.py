"""Constants for the Antigravity-to-Claude/Codex lifecycle hook bridge."""

from __future__ import annotations

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 60
STATE_DIRECTORY_NAME = "antigravity-hook-bridge"
CONTEXT_SEPARATOR = "\n\n"
CLAUDE_DIRECTORY_NAME = ".claude"
SETTINGS_FILE_NAME = "settings.json"
CLAUDE_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
CLAUDE_CODE_REMOTE_ENV = "CLAUDE_CODE_REMOTE"
CLAUDE_PROJECT_DIR_ENV = "CLAUDE_PROJECT_DIR"
SCOPE_GLOBAL = "global"
SCOPE_WORKSPACE = "workspace"
SCOPE_ALL = "all"
EXIT_CODE_BLOCK = 2
DECISION_ALLOW = "allow"
DECISION_DENY = "deny"
DECISION_ASK = "ask"

ALL_ANTIGRAVITY_TO_CLAUDE_TOOLS: dict[str, str] = {
    "run_command": "Bash",
    "write_to_file": "Write",
    "replace_file_content": "Edit",
    "multi_replace_file_content": "MultiEdit",
    "view_file": "Read",
    "read_url_content": "WebFetch",
    "invoke_subagent": "Agent",
    "ask_question": "AskUserQuestion",
    "grep_search": "Grep",
    "find_by_name": "Glob",
    "list_dir": "Glob",
}
