"""Names a settings hook reads to tell whether a mod plugin holds its work.

A converted hook stays silent when the plugin that holds its mod is on in
``enabledPlugins``, so a session runs the hook or the mod and never both.
"""

from __future__ import annotations

__all__ = [
    "ALL_SETTINGS_FILE_NAMES_IN_PRECEDENCE_ORDER",
    "CLOUD_SESSION_ENV_TRUE_VALUE",
    "CLOUD_SESSION_ENV_VAR",
    "CLAUDE_CONFIG_DIR_ENV_VAR",
    "CLAUDE_PROJECT_DIR_ENV_VAR",
    "DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME",
    "ENABLED_PLUGINS_SETTINGS_KEY",
    "PLUGIN_MARKETPLACE_SEPARATOR",
    "PROJECT_SETTINGS_DIRECTORY_NAME",
    "SESSION_PROMPTS_PLUGIN_NAME",
    "SHELL_GUARDS_PLUGIN_NAME",
    "USER_SETTINGS_FILE_NAME",
]

ENABLED_PLUGINS_SETTINGS_KEY = "enabledPlugins"
CLOUD_SESSION_ENV_VAR = "CLAUDE_CODE_REMOTE"
CLOUD_SESSION_ENV_TRUE_VALUE = "true"
PLUGIN_MARKETPLACE_SEPARATOR = "@"
SHELL_GUARDS_PLUGIN_NAME = "shell-guards"
SESSION_PROMPTS_PLUGIN_NAME = "session-prompts"
CLAUDE_CONFIG_DIR_ENV_VAR = "CLAUDE_CONFIG_DIR"
CLAUDE_PROJECT_DIR_ENV_VAR = "CLAUDE_PROJECT_DIR"
DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME = ".claude"
PROJECT_SETTINGS_DIRECTORY_NAME = ".claude"
USER_SETTINGS_FILE_NAME = "settings.json"
ALL_SETTINGS_FILE_NAMES_IN_PRECEDENCE_ORDER: tuple[str, ...] = (
    "settings.json",
    "settings.local.json",
)
