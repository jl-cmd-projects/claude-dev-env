"""Tests for the repository-gated issue-tracker SessionStart starter."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HOOKS_ROOT = Path(__file__).resolve().parent.parent
if str(_HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOOKS_ROOT))

from hooks_constants.issue_tracker_session_starter_constants import (
    ISSUE_TRACKER_SESSION_START_DIRECTIVE,
    ISSUE_TRACKER_SESSION_STARTER_ENABLED_ENV_VAR,
    ISSUE_TRACKER_STARTER_TIMEOUT_MILLISECONDS,
)
from session.issue_tracker_session_starter import (
    issue_tracker_session_starter_enabled_in_environment,
    repository_is_registered,
    run_issue_tracker_session_starter,
)

STARTER_SCRIPT = Path(__file__).resolve().parent / "issue_tracker_session_starter.py"
DEFAULT_TIMEOUT = ISSUE_TRACKER_STARTER_TIMEOUT_MILLISECONDS


def test_default_environment_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ISSUE_TRACKER_SESSION_STARTER_ENABLED_ENV_VAR, raising=False)
    assert issue_tracker_session_starter_enabled_in_environment() is False


def test_enabled_env_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ISSUE_TRACKER_SESSION_STARTER_ENABLED_ENV_VAR, "1")
    assert issue_tracker_session_starter_enabled_in_environment() is True
    monkeypatch.setenv(ISSUE_TRACKER_SESSION_STARTER_ENABLED_ENV_VAR, "true")
    assert issue_tracker_session_starter_enabled_in_environment() is True


def test_disabled_or_ineligible_emits_nothing() -> None:
    assert (
        run_issue_tracker_session_starter(
            {"source": "startup"}, False, True, DEFAULT_TIMEOUT
        )
        == {}
    )
    assert (
        run_issue_tracker_session_starter(
            {"source": "startup"}, True, False, DEFAULT_TIMEOUT
        )
        == {}
    )


def test_enabled_eligible_startup_emits_directive() -> None:
    payload = run_issue_tracker_session_starter(
        {"source": "startup"}, True, True, DEFAULT_TIMEOUT
    )
    hook_output = payload["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "SessionStart"
    assert hook_output["additionalContext"] == ISSUE_TRACKER_SESSION_START_DIRECTIVE


def test_timeout_zero_emits_nothing() -> None:
    assert (
        run_issue_tracker_session_starter({"source": "startup"}, True, True, 0) == {}
    )


def test_unknown_source_emits_nothing() -> None:
    assert (
        run_issue_tracker_session_starter({"source": "weird"}, True, True, DEFAULT_TIMEOUT)
        == {}
    )


def test_repository_is_registered_fail_closed_empty_registry() -> None:
    assert repository_is_registered("/any/path", {}) is False  # empty registry fails closed


def test_repository_is_registered_matches_git_root(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    child = tmp_path / "pkg"
    child.mkdir()
    registry = {"demo": str(tmp_path)}
    assert repository_is_registered(str(child), registry) is True
    assert repository_is_registered(str(tmp_path / "other"), {"demo": str(tmp_path / "nope")}) is False


def test_main_disabled_prints_nothing() -> None:
    environment_by_key = os.environ.copy()
    environment_by_key.pop(ISSUE_TRACKER_SESSION_STARTER_ENABLED_ENV_VAR, None)
    completed = subprocess.run(
        [sys.executable, str(STARTER_SCRIPT)],
        input=json.dumps({"source": "startup"}),
        capture_output=True,
        text=True,
        check=False,
        env=environment_by_key,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == ""


def _run_main_in_registered_repository(tmp_path: Path, is_mod_on: bool) -> str:
    """Run main() from a registered repository with the session-prompts plugin on or off."""
    repository_root = Path(__file__).resolve().parents[4]
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "project-paths.json").write_text(
        json.dumps({"this-repository": str(repository_root)}), encoding="utf-8"
    )
    (tmp_path / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"session-prompts@mods-marketplace": is_mod_on}}), encoding="utf-8"
    )
    completed = subprocess.run(
        [sys.executable, str(STARTER_SCRIPT)],
        input=json.dumps({"source": "startup"}),
        capture_output=True,
        text=True,
        check=False,
        cwd=repository_root,
        env={
            **os.environ,
            ISSUE_TRACKER_SESSION_STARTER_ENABLED_ENV_VAR: "1",
            "HOME": str(tmp_path),
            "USERPROFILE": str(tmp_path),
            "CLAUDE_CONFIG_DIR": str(tmp_path),
            "CLAUDE_PROJECT_DIR": str(tmp_path),
        },
    )
    assert completed.returncode == 0
    return completed.stdout.strip()


def test_main_prints_the_directive_while_the_session_prompts_mod_is_off(tmp_path: Path) -> None:
    emitted = json.loads(_run_main_in_registered_repository(tmp_path, is_mod_on=False))
    assert emitted["hookSpecificOutput"]["additionalContext"] == ISSUE_TRACKER_SESSION_START_DIRECTIVE


def test_main_prints_nothing_while_the_session_prompts_mod_is_on(tmp_path: Path) -> None:
    assert _run_main_in_registered_repository(tmp_path, is_mod_on=True) == ""
