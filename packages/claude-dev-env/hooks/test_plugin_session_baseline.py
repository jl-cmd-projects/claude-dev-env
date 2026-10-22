"""Behavior tests for the plugin session baseline record."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import plugin_session_baseline

PLUGIN_ID = "pstack@pstack-claude"


@pytest.fixture(autouse=True)
def isolated_temp_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        plugin_session_baseline.tempfile, "gettempdir", lambda: str(tmp_path)
    )


def test_installed_plugins_path_should_follow_the_config_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert plugin_session_baseline.installed_plugins_path() == (
        tmp_path / "plugins" / "installed_plugins.json"
    )


def test_baseline_record_path_should_name_the_session_in_the_temp_folder(
    tmp_path: Path,
) -> None:
    assert plugin_session_baseline.baseline_record_path("a/b c") == (
        tmp_path / "plugin-session-baseline-abc.json"
    )


def test_current_plugin_snapshot_should_keep_only_version_and_install_path(
    tmp_path: Path,
) -> None:
    record_path = tmp_path / "installed_plugins.json"
    record_path.write_text(
        json.dumps(
            {
                "plugins": {
                    PLUGIN_ID: [
                        {
                            "scope": "user",
                            "installPath": "/cache/pstack/1.0.0",
                            "version": "1.0.0",
                            "lastUpdated": "2026-10-21T21:26:12.000Z",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    assert plugin_session_baseline.current_plugin_snapshot(record_path) == {
        PLUGIN_ID: [{"version": "1.0.0", "installPath": "/cache/pstack/1.0.0"}]
    }


def test_current_plugin_snapshot_should_read_a_malformed_record_as_empty(
    tmp_path: Path,
) -> None:
    record_path = tmp_path / "installed_plugins.json"
    record_path.write_text("{not json", encoding="utf-8")
    assert plugin_session_baseline.current_plugin_snapshot(record_path) == {}


def test_read_baseline_record_should_return_what_the_writer_stored() -> None:
    snapshot = {PLUGIN_ID: [{"version": "1.0.0", "installPath": "/cache/pstack/1.0.0"}]}
    plugin_session_baseline.write_baseline_record("session", snapshot, [PLUGIN_ID])
    assert plugin_session_baseline.read_baseline_record("session") == {
        "plugins": snapshot,
        "warned": [PLUGIN_ID],
    }


def test_all_changed_plugin_ids_should_name_changed_and_new_plugins_only() -> None:
    unchanged_entries = [{"version": "1.0.0", "installPath": "/cache/a/1.0.0"}]
    baseline_snapshot = {
        "a@m": unchanged_entries,
        "b@m": [{"version": "1.0.0", "installPath": "/cache/b/1.0.0"}],
    }
    current_snapshot = {
        "a@m": unchanged_entries,
        "b@m": [{"version": "2.0.0", "installPath": "/cache/b/2.0.0"}],
        "c@m": [{"version": "1.0.0", "installPath": "/cache/c/1.0.0"}],
    }
    assert plugin_session_baseline.all_changed_plugin_ids(
        baseline_snapshot, current_snapshot
    ) == [
        "b@m",
        "c@m",
    ]
