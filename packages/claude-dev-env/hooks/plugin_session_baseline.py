"""Per-session baseline of the installed plugins, read against the live plugin record.

The SessionStart baseline writer records each plugin's ``version`` and
``installPath`` from ``installed_plugins.json`` into one JSON file per session
in the system temp folder. The UserPromptSubmit warning hook reads the same
file back, compares it with the live record, and lists the plugin ids it has
already warned about under ``warned``::

    plugin-session-baseline-<session id>.json
    {"plugins": {"pstack@pstack-claude": [{"version": "1.0.0",
      "installPath": "/cache/pstack/1.0.0"}]}, "warned": []}

Fields such as ``lastUpdated`` stay out of the snapshot, so a refresh that
changes nothing a session loads reads as unchanged.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from atomic_file_writer import write_text_atomically
from hooks_constants.atomic_file_writer_constants import ATOMIC_WRITE_TEMPORARY_SUFFIX
from hooks_constants.plugin_session_baseline_constants import (
    BASELINE_PLUGINS_KEY,
    BASELINE_RECORD_FILE_TEMPLATE,
    BASELINE_RECORD_TEMPORARY_PREFIX,
    BASELINE_TEXT_ENCODING,
    BASELINE_WARNED_KEY,
    CLAUDE_CONFIG_DIR_ENV_VAR,
    DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME,
    INSTALLED_PLUGINS_FILE_NAME,
    INSTALLED_PLUGINS_RECORD_KEY,
    INSTALL_PATH_FIELD,
    PLUGINS_DIRECTORY_NAME,
    VERSION_FIELD,
)
from hooks_constants.session_file_id import session_file_id
from json_file_reader import read_json_object

__all__ = [
    "all_changed_plugin_ids",
    "baseline_record_path",
    "current_plugin_snapshot",
    "installed_plugins_path",
    "read_baseline_record",
    "write_baseline_record",
]

PluginSnapshot = dict[str, list[dict[str, str]]]


def installed_plugins_path() -> Path:
    """Return the installed plugin record under the active Claude config directory."""
    configured_directory = os.environ.get(CLAUDE_CONFIG_DIR_ENV_VAR, "").strip()
    config_directory = (
        Path(configured_directory)
        if configured_directory
        else Path.home() / DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME
    )
    return config_directory / PLUGINS_DIRECTORY_NAME / INSTALLED_PLUGINS_FILE_NAME


def _loaded_fields(each_entry: object) -> dict[str, str] | None:
    if not isinstance(each_entry, dict):
        return None
    version = each_entry.get(VERSION_FIELD)
    install_path = each_entry.get(INSTALL_PATH_FIELD)
    if not isinstance(version, str) or not isinstance(install_path, str):
        return None
    return {VERSION_FIELD: version, INSTALL_PATH_FIELD: install_path}


def _sorted_entries(all_entries: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        all_entries,
        key=lambda each_entry: (
            each_entry[INSTALL_PATH_FIELD],
            each_entry[VERSION_FIELD],
        ),
    )


def current_plugin_snapshot(record_path: Path) -> PluginSnapshot:
    """Return each plugin id with the version and install path of each of its installs.

    A missing, unreadable, or malformed record reads as no plugins.

    Args:
        record_path: The ``installed_plugins.json`` path.
    """
    installed_record = read_json_object(record_path, BASELINE_TEXT_ENCODING)
    if installed_record is None:
        return {}
    all_plugins = installed_record.get(INSTALLED_PLUGINS_RECORD_KEY)
    if not isinstance(all_plugins, dict):
        return {}
    snapshot: PluginSnapshot = {}
    for each_plugin_id, each_plugin_entries in all_plugins.items():
        if not isinstance(each_plugin_entries, list):
            continue
        all_loaded_entries = [
            loaded_entry
            for loaded_entry in (
                _loaded_fields(each_entry) for each_entry in each_plugin_entries
            )
            if loaded_entry is not None
        ]
        snapshot[str(each_plugin_id)] = _sorted_entries(all_loaded_entries)
    return snapshot


def baseline_record_path(session_id: object) -> Path:
    """Return the baseline file path for one session.

    Args:
        session_id: The ``session_id`` field of the hook payload.
    """
    file_name = BASELINE_RECORD_FILE_TEMPLATE.format(
        session_file_id=session_file_id(session_id)
    )
    return Path(tempfile.gettempdir()) / file_name


def read_baseline_record(session_id: object) -> dict[str, object] | None:
    """Return the session's baseline record, or None when none is readable.

    Args:
        session_id: The ``session_id`` field of the hook payload.
    """
    baseline_record = read_json_object(
        baseline_record_path(session_id), BASELINE_TEXT_ENCODING
    )
    if baseline_record is None:
        return None
    if not isinstance(baseline_record.get(BASELINE_PLUGINS_KEY), dict):
        return None
    if not isinstance(baseline_record.get(BASELINE_WARNED_KEY), list):
        return None
    return baseline_record


def write_baseline_record(
    session_id: object, snapshot: PluginSnapshot, all_warned_plugin_ids: list[str]
) -> None:
    """Replace the session's baseline record.

    A write that fails leaves the file as it was, so the hook never fails the session.

    Args:
        session_id: The ``session_id`` field of the hook payload.
        snapshot: The plugin snapshot the session loaded at start.
        all_warned_plugin_ids: The plugin ids already named in a warning.
    """
    serialized_record = json.dumps(
        {
            BASELINE_PLUGINS_KEY: snapshot,
            BASELINE_WARNED_KEY: sorted(all_warned_plugin_ids),
        }
    )
    try:
        write_text_atomically(
            baseline_record_path(session_id),
            serialized_record,
            BASELINE_TEXT_ENCODING,
            BASELINE_RECORD_TEMPORARY_PREFIX,
            ATOMIC_WRITE_TEMPORARY_SUFFIX,
            False,
        )
    except (OSError, UnicodeError):
        return


def all_changed_plugin_ids(
    baseline_snapshot: object, current_snapshot: PluginSnapshot
) -> list[str]:
    """Return each plugin id whose installs differ from the baseline, or that the baseline lacks.

    Args:
        baseline_snapshot: The ``plugins`` value of the baseline record.
        current_snapshot: The live snapshot from ``current_plugin_snapshot``.
    """
    known_snapshot = baseline_snapshot if isinstance(baseline_snapshot, dict) else {}
    return sorted(
        each_plugin_id
        for each_plugin_id, each_plugin_entries in current_snapshot.items()
        if known_snapshot.get(each_plugin_id) != each_plugin_entries
    )
