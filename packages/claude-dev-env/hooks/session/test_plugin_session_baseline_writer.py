"""Tests for plugin_session_baseline_writer: the SessionStart plugin baseline hook."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import plugin_session_baseline
import plugin_session_baseline_writer

SESSION_ID = "session-one"
PLUGIN_ID = "deepstack@deepstack"


def _plugin_entry(version: str, install_path: str, last_updated: str) -> dict[str, str]:
    return {
        "scope": "user",
        "installPath": install_path,
        "version": version,
        "installedAt": "2026-10-21T19:00:00.000Z",
        "lastUpdated": last_updated,
    }


def write_installed_plugins(
    config_directory: Path, all_plugins: dict[str, list[dict[str, str]]]
) -> None:
    plugins_directory = config_directory / "plugins"
    plugins_directory.mkdir(parents=True, exist_ok=True)
    (plugins_directory / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": all_plugins}), encoding="utf-8"
    )


def run_writer(session_id: str, source: str) -> str:
    payload_text = json.dumps(
        {"session_id": session_id, "hook_event_name": "SessionStart", "source": source}
    )
    captured_stdout = io.StringIO()
    with (
        patch("sys.stdin", io.TextIOWrapper(io.BytesIO(payload_text.encode("utf-8")))),
        patch("sys.stdout", captured_stdout),
    ):
        plugin_session_baseline_writer.main()
    return captured_stdout.getvalue()


@pytest.fixture
def config_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    claude_config_directory = tmp_path / "config"
    state_directory = tmp_path / "state"
    state_directory.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_config_directory))
    monkeypatch.setattr(
        plugin_session_baseline.tempfile, "gettempdir", lambda: str(state_directory)
    )
    return claude_config_directory


def test_startup_should_record_each_plugin_version_and_install_path(
    config_directory: Path,
) -> None:
    write_installed_plugins(
        config_directory,
        {PLUGIN_ID: [_plugin_entry("1.0.0", "/cache/deepstack/1.0.0", "a")]},
    )
    assert run_writer(SESSION_ID, "startup") == ""
    baseline_record = plugin_session_baseline.read_baseline_record(SESSION_ID)
    assert baseline_record == {
        "plugins": {
            PLUGIN_ID: [{"version": "1.0.0", "installPath": "/cache/deepstack/1.0.0"}]
        },
        "warned": [],
    }


@pytest.mark.parametrize("source", ["resume", "clear", "compact"])
def test_a_later_source_should_leave_an_existing_baseline_alone(
    config_directory: Path, source: str
) -> None:
    write_installed_plugins(
        config_directory,
        {PLUGIN_ID: [_plugin_entry("1.0.0", "/cache/deepstack/1.0.0", "a")]},
    )
    run_writer(SESSION_ID, "startup")
    baseline_path = plugin_session_baseline.baseline_record_path(SESSION_ID)
    baseline_text = baseline_path.read_text(encoding="utf-8")
    write_installed_plugins(
        config_directory,
        {PLUGIN_ID: [_plugin_entry("2.0.0", "/cache/deepstack/2.0.0", "b")]},
    )
    run_writer(SESSION_ID, source)
    assert baseline_path.read_text(encoding="utf-8") == baseline_text


def test_resume_without_a_baseline_should_write_one(config_directory: Path) -> None:
    write_installed_plugins(
        config_directory,
        {PLUGIN_ID: [_plugin_entry("1.0.0", "/cache/deepstack/1.0.0", "a")]},
    )
    run_writer(SESSION_ID, "resume")
    baseline_record = plugin_session_baseline.read_baseline_record(SESSION_ID)
    assert baseline_record is not None
    assert PLUGIN_ID in baseline_record["plugins"]


def test_a_payload_without_a_session_id_should_write_nothing(
    config_directory: Path, tmp_path: Path
) -> None:
    write_installed_plugins(
        config_directory,
        {PLUGIN_ID: [_plugin_entry("1.0.0", "/cache/deepstack/1.0.0", "a")]},
    )
    run_writer("", "startup")
    assert list((tmp_path / "state").iterdir()) == []


def test_a_missing_installed_plugins_file_should_record_an_empty_baseline(
    config_directory: Path,
) -> None:
    run_writer(SESSION_ID, "startup")
    assert plugin_session_baseline.read_baseline_record(SESSION_ID) == {
        "plugins": {},
        "warned": [],
    }
