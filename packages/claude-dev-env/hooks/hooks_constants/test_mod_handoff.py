"""Behavioral tests for the mod handoff check that silences a converted hook."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HOOKS_ROOT = Path(__file__).resolve().parent.parent
if str(_HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOOKS_ROOT))

from hooks_constants.mod_handoff import (
    all_settings_paths_in_precedence_order,
    is_mod_plugin_enabled,
    plugin_state_in_settings_file,
)


@pytest.fixture
def settings_homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Point the user config and project directories at empty temp folders."""
    user_directory = tmp_path / "user-config"
    project_directory = tmp_path / "project"
    (project_directory / ".claude").mkdir(parents=True)
    user_directory.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(user_directory))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project_directory))
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    return user_directory, project_directory


def _write_enabled_plugins(settings_path: Path, enabled_plugins: object) -> None:
    settings_path.write_text(json.dumps({"enabledPlugins": enabled_plugins}), encoding="utf-8")


def test_should_list_user_then_project_then_local_settings(
    settings_homes: tuple[Path, Path],
) -> None:
    user_directory, project_directory = settings_homes
    assert all_settings_paths_in_precedence_order() == [
        user_directory / "settings.json",
        project_directory / ".claude" / "settings.json",
        project_directory / ".claude" / "settings.local.json",
    ]


def test_should_match_the_plugin_under_any_marketplace(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    _write_enabled_plugins(settings_path, {"shell-guards@any-marketplace": True})
    assert plugin_state_in_settings_file(settings_path, "shell-guards") is True


def test_should_report_no_state_for_a_plugin_the_file_never_names(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    _write_enabled_plugins(settings_path, {"shell-guards-extra@market": True})
    assert plugin_state_in_settings_file(settings_path, "shell-guards") is None


def test_should_report_no_state_for_a_missing_or_broken_file(tmp_path: Path) -> None:
    broken_path = tmp_path / "broken.json"
    broken_path.write_text("{not json", encoding="utf-8")
    assert plugin_state_in_settings_file(tmp_path / "missing.json", "shell-guards") is None
    assert plugin_state_in_settings_file(broken_path, "shell-guards") is None


def test_should_stay_off_when_no_settings_file_names_the_plugin(
    settings_homes: tuple[Path, Path],
) -> None:
    assert is_mod_plugin_enabled("session-prompts") is False


def test_should_turn_on_from_the_user_settings(settings_homes: tuple[Path, Path]) -> None:
    user_directory, _ = settings_homes
    _write_enabled_plugins(user_directory / "settings.json", {"session-prompts@market": True})
    assert is_mod_plugin_enabled("session-prompts") is True


def test_should_let_local_project_settings_turn_a_user_plugin_off(
    settings_homes: tuple[Path, Path],
) -> None:
    user_directory, project_directory = settings_homes
    _write_enabled_plugins(user_directory / "settings.json", {"session-prompts@market": True})
    _write_enabled_plugins(
        project_directory / ".claude" / "settings.local.json", {"session-prompts@market": False}
    )
    assert is_mod_plugin_enabled("session-prompts") is False


def test_should_keep_the_hook_in_a_cloud_session_with_the_plugin_on(
    settings_homes: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, project_directory = settings_homes
    _write_enabled_plugins(
        project_directory / ".claude" / "settings.json", {"session-prompts@market": True}
    )
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    assert is_mod_plugin_enabled("session-prompts") is False
