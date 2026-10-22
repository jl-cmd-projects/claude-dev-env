"""Tests for plugin_change_warning: the UserPromptSubmit plugin restart warning."""

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

import plugin_change_warning
import plugin_session_baseline
import plugin_session_baseline_writer

SESSION_ID = "session-two"
DEEPSTACK_ID = "deepstack@deepstack"
PSTACK_ID = "pstack@pstack-claude"


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


def _run_main(main_function: object, payload: dict[str, str]) -> str:
    payload_bytes = json.dumps(payload).encode("utf-8")
    captured_stdout = io.StringIO()
    with (
        patch("sys.stdin", io.TextIOWrapper(io.BytesIO(payload_bytes))),
        patch("sys.stdout", captured_stdout),
    ):
        main_function()
    return captured_stdout.getvalue()


def start_session(source: str) -> None:
    _run_main(
        plugin_session_baseline_writer.main,
        {"session_id": SESSION_ID, "hook_event_name": "SessionStart", "source": source},
    )


def submit_prompt() -> dict[str, object] | None:
    hook_output = _run_main(
        plugin_change_warning.main,
        {
            "session_id": SESSION_ID,
            "hook_event_name": "UserPromptSubmit",
            "prompt": "run /deepstack-mode",
        },
    )
    return json.loads(hook_output) if hook_output else None


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


def _warning_text(hook_output: dict[str, object] | None) -> str:
    assert hook_output is not None
    system_message = hook_output["systemMessage"]
    assert isinstance(system_message, str)
    hook_specific_output = hook_output["hookSpecificOutput"]
    assert isinstance(hook_specific_output, dict)
    assert hook_specific_output["hookEventName"] == "UserPromptSubmit"
    assert hook_specific_output["additionalContext"] == system_message
    return system_message


def test_a_changed_version_should_warn_once(config_directory: Path) -> None:
    write_installed_plugins(
        config_directory,
        {PSTACK_ID: [_plugin_entry("1.0.0", "/cache/pstack/1.0.0", "a")]},
    )
    start_session("startup")
    write_installed_plugins(
        config_directory,
        {PSTACK_ID: [_plugin_entry("1.1.0", "/cache/pstack/1.1.0", "b")]},
    )
    warning_text = _warning_text(submit_prompt())
    assert PSTACK_ID in warning_text
    assert "Restart Claude Code" in warning_text
    assert submit_prompt() is None


def test_a_plugin_new_since_start_should_warn(config_directory: Path) -> None:
    write_installed_plugins(
        config_directory,
        {PSTACK_ID: [_plugin_entry("1.0.0", "/cache/pstack/1.0.0", "a")]},
    )
    start_session("startup")
    write_installed_plugins(
        config_directory,
        {
            PSTACK_ID: [_plugin_entry("1.0.0", "/cache/pstack/1.0.0", "a")],
            DEEPSTACK_ID: [_plugin_entry("3.0.0", "/cache/deepstack/3.0.0", "b")],
        },
    )
    warning_text = _warning_text(submit_prompt())
    assert DEEPSTACK_ID in warning_text
    assert PSTACK_ID not in warning_text


def test_a_changed_install_path_should_warn(config_directory: Path) -> None:
    write_installed_plugins(
        config_directory,
        {PSTACK_ID: [_plugin_entry("1.0.0", "/cache/pstack/old", "a")]},
    )
    start_session("startup")
    write_installed_plugins(
        config_directory,
        {PSTACK_ID: [_plugin_entry("1.0.0", "/cache/pstack/new", "a")]},
    )
    assert PSTACK_ID in _warning_text(submit_prompt())


def test_a_bare_last_updated_refresh_should_stay_quiet(config_directory: Path) -> None:
    write_installed_plugins(
        config_directory,
        {PSTACK_ID: [_plugin_entry("1.0.0", "/cache/pstack/1.0.0", "a")]},
    )
    start_session("startup")
    write_installed_plugins(
        config_directory,
        {PSTACK_ID: [_plugin_entry("1.0.0", "/cache/pstack/1.0.0", "later")]},
    )
    assert submit_prompt() is None


def test_an_install_then_compact_then_prompt_should_still_warn(
    config_directory: Path,
) -> None:
    write_installed_plugins(
        config_directory,
        {PSTACK_ID: [_plugin_entry("1.0.0", "/cache/pstack/1.0.0", "a")]},
    )
    start_session("startup")
    write_installed_plugins(
        config_directory,
        {
            PSTACK_ID: [_plugin_entry("1.0.0", "/cache/pstack/1.0.0", "a")],
            DEEPSTACK_ID: [_plugin_entry("3.0.0", "/cache/deepstack/3.0.0", "b")],
        },
    )
    start_session("compact")
    assert DEEPSTACK_ID in _warning_text(submit_prompt())


def test_a_second_plugin_change_should_warn_only_for_that_plugin(
    config_directory: Path,
) -> None:
    write_installed_plugins(
        config_directory,
        {
            PSTACK_ID: [_plugin_entry("1.0.0", "/cache/pstack/1.0.0", "a")],
            DEEPSTACK_ID: [_plugin_entry("3.0.0", "/cache/deepstack/3.0.0", "a")],
        },
    )
    start_session("startup")
    write_installed_plugins(
        config_directory,
        {
            PSTACK_ID: [_plugin_entry("1.1.0", "/cache/pstack/1.1.0", "b")],
            DEEPSTACK_ID: [_plugin_entry("3.0.0", "/cache/deepstack/3.0.0", "a")],
        },
    )
    assert PSTACK_ID in _warning_text(submit_prompt())
    write_installed_plugins(
        config_directory,
        {
            PSTACK_ID: [_plugin_entry("1.2.0", "/cache/pstack/1.2.0", "c")],
            DEEPSTACK_ID: [_plugin_entry("3.1.0", "/cache/deepstack/3.1.0", "c")],
        },
    )
    second_warning_text = _warning_text(submit_prompt())
    assert DEEPSTACK_ID in second_warning_text
    assert PSTACK_ID not in second_warning_text


def test_a_session_without_a_baseline_should_stay_quiet(config_directory: Path) -> None:
    write_installed_plugins(
        config_directory,
        {PSTACK_ID: [_plugin_entry("1.0.0", "/cache/pstack/1.0.0", "a")]},
    )
    assert submit_prompt() is None
