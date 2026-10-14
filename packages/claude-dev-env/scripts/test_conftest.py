import os
from pathlib import Path

import pytest

import account_broker_support


def test_isolated_broker_state_path_follows_the_redirected_home(
    isolated_broker_state_path: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert Path.home().is_relative_to(tmp_path)
    assert isolated_broker_state_path.is_relative_to(Path.home())
    moved_home = tmp_path / "moved-home"
    monkeypatch.setenv("HOME", str(moved_home))
    monkeypatch.setenv("USERPROFILE", str(moved_home))
    assert account_broker_support.broker_state_path().is_relative_to(moved_home)


def test_isolated_home_clears_the_variables_that_override_the_home(isolated_home: Path) -> None:
    for each_home_override in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "CODEX_ACCOUNT_PROFILES", "LLM_SETTINGS_PROFILES_ROOT"):
        assert each_home_override not in os.environ
