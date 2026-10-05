"""Floors, outcome shape, and time helpers for the account broker."""

from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import os
import shutil
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dev_env_scripts_constants import account_broker_constants as broker_constants
from dev_env_scripts_constants.account_broker_constants import (
    ALL_BATCH_FILE_EXTENSIONS,
    ALL_CLAUDE_FLOORS,
    ALL_CODEX_FLOORS,
    ALL_PARENT_CLAUDE_SESSION_VARIABLES,
    CMD_SHELL_METACHARACTERS,
    JobOutcome,
)
from dev_env_scripts_constants.claude_account_constants import (
    MAIN_SESSION_USED_CEILING_PERCENT,
    MAIN_WEEKLY_USED_CEILING_PERCENT,
    SECOND_SESSION_USED_CEILING_PERCENT,
    SECOND_WEEKLY_USED_CEILING_PERCENT,
)
from dev_env_scripts_constants.codex_account_constants import (
    LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT,
    LUNA_TIER_STOP_PERCENT_LEFT,
    NORMAL_TIER_MINIMUM_PERCENT_LEFT,
)

TEMP_TREE_MARKER = "marker-only-in-the-temp-install-tree"


def test_should_keep_claude_floors_tied_to_the_account_ceilings() -> None:
    assert ALL_CLAUDE_FLOORS == {
        "main_weekly_used_ceiling": MAIN_WEEKLY_USED_CEILING_PERCENT,
        "main_session_used_ceiling": MAIN_SESSION_USED_CEILING_PERCENT,
        "extra_weekly_used_ceiling": SECOND_WEEKLY_USED_CEILING_PERCENT,
        "extra_session_used_ceiling": SECOND_SESSION_USED_CEILING_PERCENT,
    }


def test_should_keep_codex_floors_tied_to_the_tier_limits() -> None:
    assert ALL_CODEX_FLOORS == {
        "normal_minimum_left": NORMAL_TIER_MINIMUM_PERCENT_LEFT,
        "luna_stop_left": LUNA_TIER_STOP_PERCENT_LEFT,
        "luna_short_minimum_left": LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT,
    }


def test_batch_command_boundaries_include_shell_metacharacters() -> None:
    assert ALL_BATCH_FILE_EXTENSIONS == frozenset({".bat", ".cmd"})
    assert set(CMD_SHELL_METACHARACTERS) == set('&|<>^%!"\r\n')


def test_should_freeze_job_outcome() -> None:
    outcome = JobOutcome(0, "", "", None, (), "served", None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.status = "wait"


def test_codex_usage_limit_signatures_loads_classifier_markers() -> None:
    signatures = broker_constants.codex_usage_limit_signatures()

    assert "rate limit" in signatures
    assert "http 429" in signatures


def test_codex_usage_limit_signatures_raises_import_error_when_markers_are_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(broker_constants, "__file__", str(tmp_path / "scripts" / "constants" / "module.py"))

    with pytest.raises(ImportError, match="cannot load usage markers from") as raised:
        broker_constants.codex_usage_limit_signatures()

    assert str(tmp_path) in str(raised.value)
    assert isinstance(raised.value.__cause__, FileNotFoundError)


def test_utc_time_text_converts_an_offset_timestamp() -> None:
    moment = datetime(2026, 10, 3, 7, 30, tzinfo=timezone(timedelta(hours=-4)))

    assert broker_constants.utc_time_text(moment) == "2026-10-03T11:30:00+00:00"
    assert broker_constants.utc_time_text(None) is None


@pytest.mark.parametrize("timestamp", (None, 123, "not a timestamp", "2026-10-03T11:30:00"))
def test_parse_utc_time_rejects_values_without_a_timezone(timestamp: object) -> None:
    assert broker_constants.parse_utc_time(timestamp) is None


def test_parse_utc_time_converts_an_offset_timestamp() -> None:
    parsed = broker_constants.parse_utc_time("2026-10-03T07:30:00-04:00")

    assert parsed is not None
    assert parsed.isoformat() == "2026-10-03T11:30:00+00:00"

def _create_directory_link(*, from_link: Path, to_target: Path) -> None:
    if sys.platform.startswith("win32"):
        importlib.import_module("_winapi").CreateJunction(
            str(to_target), str(from_link)
        )
        return
    os.symlink(to_target, from_link, target_is_directory=True)


def _build_install_layout(home: Path) -> tuple[Path, Path]:
    agents_constants_directory = (
        home / ".agents" / "scripts" / "dev_env_scripts_constants"
    )
    agents_constants_directory.mkdir(parents=True)
    shutil.copy(
        Path(broker_constants.__file__),
        agents_constants_directory / "account_broker_constants.py",
    )
    classifier_directory = (
        home
        / ".claude"
        / "_shared"
        / "pr-loop"
        / "scripts"
        / "codex_review_scripts_constants"
    )
    classifier_directory.mkdir(parents=True)
    (classifier_directory / "classifier_constants.py").write_text(
        f"ALL_USAGE_LIMIT_MARKERS = ({TEMP_TREE_MARKER!r},)\n", encoding="utf-8"
    )
    _create_directory_link(
        from_link=home / ".claude" / "scripts", to_target=home / ".agents" / "scripts"
    )
    linked_module = (
        home
        / ".claude"
        / "scripts"
        / "dev_env_scripts_constants"
        / "account_broker_constants.py"
    )
    agents_module = agents_constants_directory / "account_broker_constants.py"
    return linked_module, agents_module


def _load_module_from(
    module_file: Path, module_name: str, monkeypatch: pytest.MonkeyPatch
) -> types.ModuleType:
    specification = importlib.util.spec_from_file_location(module_name, module_file)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    monkeypatch.setitem(sys.modules, module_name, module)
    specification.loader.exec_module(module)
    return module


@pytest.mark.parametrize("entry_point", ("through_scripts_link", "through_agents_path"))
def test_codex_usage_limit_signatures_finds_shared_tree_beside_the_scripts_link(
    entry_point: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    linked_module, agents_module = _build_install_layout(tmp_path / "home")
    module_file = (
        linked_module if entry_point == "through_scripts_link" else agents_module
    )
    installed_constants = _load_module_from(
        module_file, f"installed_account_broker_constants_{entry_point}", monkeypatch
    )

    assert installed_constants.codex_usage_limit_signatures() == (TEMP_TREE_MARKER,)


def test_parent_session_variables_name_the_session_link_and_leave_the_account_home() -> None:
    assert "CLAUDE_CODE_SESSION_ID" in ALL_PARENT_CLAUDE_SESSION_VARIABLES
    assert "CLAUDECODE" in ALL_PARENT_CLAUDE_SESSION_VARIABLES
    assert "CLAUDE_CONFIG_DIR" not in ALL_PARENT_CLAUDE_SESSION_VARIABLES
