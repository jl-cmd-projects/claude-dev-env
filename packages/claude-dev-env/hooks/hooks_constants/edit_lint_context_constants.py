"""Constants for the PostToolUse hook that lints each edited file."""

from __future__ import annotations

__all__ = [
    "REPOSITORIES_ENVIRONMENT_VARIABLE",
    "REPOSITORY_SEPARATOR",
    "CONFIG_RELATIVE_PATH",
    "FILE_SUFFIXES_KEY",
    "COMMAND_KEY",
    "FILE_PLACEHOLDER",
    "ALL_EDIT_TOOL_NAMES",
    "ALL_GIT_TOPLEVEL_COMMAND",
    "GIT_COMMAND_TIMEOUT_SECONDS",
    "LINT_COMMAND_TIMEOUT_SECONDS",
    "MAXIMUM_FINDINGS_CHARACTERS",
    "TRUNCATION_NOTICE",
    "FINDINGS_CONTEXT_TEMPLATE",
    "LINT_FAILURE_DIAGNOSTIC_TEMPLATE",
]

REPOSITORIES_ENVIRONMENT_VARIABLE = "CLAUDE_EDIT_LINT_REPOSITORIES"
REPOSITORY_SEPARATOR = ","
CONFIG_RELATIVE_PATH = ".claude/edit-lint.json"
FILE_SUFFIXES_KEY = "file_suffixes"
COMMAND_KEY = "command"
FILE_PLACEHOLDER = "{file}"
ALL_EDIT_TOOL_NAMES = frozenset({"Write", "Edit", "MultiEdit"})
ALL_GIT_TOPLEVEL_COMMAND = ("git", "rev-parse", "--show-toplevel")
GIT_COMMAND_TIMEOUT_SECONDS = 10
LINT_COMMAND_TIMEOUT_SECONDS = 60
MAXIMUM_FINDINGS_CHARACTERS = 4000
TRUNCATION_NOTICE = "\n[edit lint output cut at {limit} characters]"
FINDINGS_CONTEXT_TEMPLATE = (
    "The repository's lint found these problems in {file} after this edit. "
    "Fix them in this turn:\n{findings}"
)
LINT_FAILURE_DIAGNOSTIC_TEMPLATE = "[edit_lint_context] lint command for %s did not finish: %s\n"
