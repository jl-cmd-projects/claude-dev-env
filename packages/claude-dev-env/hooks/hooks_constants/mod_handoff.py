"""Tell a settings hook whether the mod plugin that holds its work is on.

Claude Code reads ``enabledPlugins`` from the user settings file, then the
project's ``.claude/settings.json``, then its ``.claude/settings.local.json``,
and a later file overrides an earlier one. A key names a plugin as
``<plugin>@<marketplace>``, so a match on the plugin name holds wherever the
plugin ships.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from hooks_constants.mod_handoff_constants import (
    ALL_SETTINGS_FILE_NAMES_IN_PRECEDENCE_ORDER,
    CLAUDE_CONFIG_DIR_ENV_VAR,
    CLAUDE_PROJECT_DIR_ENV_VAR,
    DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME,
    ENABLED_PLUGINS_SETTINGS_KEY,
    PLUGIN_MARKETPLACE_SEPARATOR,
    PROJECT_SETTINGS_DIRECTORY_NAME,
    USER_SETTINGS_FILE_NAME,
)


def all_settings_paths_in_precedence_order() -> list[Path]:
    """Return the user, project and local settings files, lowest precedence first."""
    configured_directory = os.environ.get(CLAUDE_CONFIG_DIR_ENV_VAR, "").strip()
    user_directory = (
        Path(configured_directory)
        if configured_directory
        else Path.home() / DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME
    )
    all_paths = [user_directory / USER_SETTINGS_FILE_NAME]
    project_directory = os.environ.get(CLAUDE_PROJECT_DIR_ENV_VAR, "").strip() or os.getcwd()
    project_settings_directory = Path(project_directory) / PROJECT_SETTINGS_DIRECTORY_NAME
    all_paths.extend(
        project_settings_directory / each_file_name
        for each_file_name in ALL_SETTINGS_FILE_NAMES_IN_PRECEDENCE_ORDER
    )
    return all_paths


def plugin_state_in_settings_file(settings_path: Path, plugin_name: str) -> bool | None:
    """Return the file's on or off setting for plugin_name, or None when it names none.

    Args:
        settings_path: A Claude Code settings file.
        plugin_name: The plugin name before the ``@marketplace`` part of the key.
    """
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(settings, dict):
        return None
    enabled_plugins = settings.get(ENABLED_PLUGINS_SETTINGS_KEY)
    if not isinstance(enabled_plugins, dict):
        return None
    all_states = [
        each_state
        for each_key, each_state in enabled_plugins.items()
        if isinstance(each_key, str)
        and isinstance(each_state, bool)
        and each_key.split(PLUGIN_MARKETPLACE_SEPARATOR, 1)[0] == plugin_name
    ]
    if not all_states:
        return None
    return any(all_states)


def is_mod_plugin_enabled(plugin_name: str) -> bool:
    """Return True when the settings files leave plugin_name on.

    Args:
        plugin_name: The plugin that holds the mod replacing the calling hook.
    """
    is_enabled = False
    for each_path in all_settings_paths_in_precedence_order():
        state = plugin_state_in_settings_file(each_path, plugin_name)
        if state is not None:
            is_enabled = state
    return is_enabled
