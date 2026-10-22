"""Constants for the plugin session baseline and the plugin change warning hooks."""

from __future__ import annotations

__all__ = [
    "BASELINE_PLUGINS_KEY",
    "BASELINE_RECORD_FILE_TEMPLATE",
    "BASELINE_RECORD_TEMPORARY_PREFIX",
    "BASELINE_TEXT_ENCODING",
    "BASELINE_WARNED_KEY",
    "CLAUDE_CONFIG_DIR_ENV_VAR",
    "DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME",
    "INSTALLED_PLUGINS_FILE_NAME",
    "INSTALLED_PLUGINS_RECORD_KEY",
    "INSTALL_PATH_FIELD",
    "PLUGINS_DIRECTORY_NAME",
    "PLUGIN_CHANGE_WARNING_TEMPLATE",
    "PLUGIN_ID_SEPARATOR",
    "SESSION_ID_FIELD",
    "SESSION_SOURCE_FIELD",
    "STARTUP_SOURCE",
    "USER_PROMPT_SUBMIT_EVENT_NAME",
    "VERSION_FIELD",
]

CLAUDE_CONFIG_DIR_ENV_VAR = "CLAUDE_CONFIG_DIR"
DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME = ".claude"
PLUGINS_DIRECTORY_NAME = "plugins"
INSTALLED_PLUGINS_FILE_NAME = "installed_plugins.json"
INSTALLED_PLUGINS_RECORD_KEY = "plugins"
VERSION_FIELD = "version"
INSTALL_PATH_FIELD = "installPath"

SESSION_ID_FIELD = "session_id"
SESSION_SOURCE_FIELD = "source"
STARTUP_SOURCE = "startup"
USER_PROMPT_SUBMIT_EVENT_NAME = "UserPromptSubmit"

BASELINE_RECORD_FILE_TEMPLATE = "plugin-session-baseline-{session_file_id}.json"
BASELINE_RECORD_TEMPORARY_PREFIX = "plugin-session-baseline-"
BASELINE_TEXT_ENCODING = "utf-8"
BASELINE_PLUGINS_KEY = "plugins"
BASELINE_WARNED_KEY = "warned"

PLUGIN_ID_SEPARATOR = ", "
PLUGIN_CHANGE_WARNING_TEMPLATE = (
    "Plugin files changed after this session started: {plugin_ids}."
    " This session keeps the plugin versions it loaded at start, so their new skills,"
    " commands, and hooks stay unavailable here. Restart Claude Code to load them."
)
