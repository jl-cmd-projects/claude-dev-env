"""Broker state written during a test stays out of the home directory."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import account_broker
from dev_env_scripts_constants.account_broker_constants import (
    BROKER_STATE_DIRECTORY_NAME,
    BROKER_STATE_FILE_NAME,
    Account,
    Meters,
    Product,
    ProductAdapter,
)
from dev_env_scripts_constants.claude_account_constants import MAIN_CLAUDE_HOME_DIRECTORY_NAME

_user_claude_directory = Path.home() / MAIN_CLAUDE_HOME_DIRECTORY_NAME
_user_broker_state_path = _user_claude_directory / BROKER_STATE_DIRECTORY_NAME / BROKER_STATE_FILE_NAME


def _user_broker_state_modified_at() -> int | None:
    if not _user_broker_state_path.exists():
        return None
    return _user_broker_state_path.stat().st_mtime_ns


def test_meter_cache_write_lands_outside_the_home_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_broker_state_path: Path,
) -> None:
    account = Account(Product.CLAUDE, "only", tmp_path / "only")
    reset_at = datetime(2026, 10, 5, tzinfo=timezone.utc)
    adapter = ProductAdapter(
        lambda: (account,),
        lambda each_account: Meters(80, reset_at, 80, reset_at),
        "CLAUDE_CONFIG_DIR",
        ("usage limit",),
    )
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CLAUDE, adapter)

    def runner(argv: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, "", "")

    user_broker_state_modified_before = _user_broker_state_modified_at()
    with account_broker.override_subprocess_runner(runner):
        account_broker.run_job(Product.CLAUDE, ["claude"])

    assert _user_broker_state_modified_at() == user_broker_state_modified_before
    assert not isolated_broker_state_path.is_relative_to(_user_claude_directory)
    state = json.loads(isolated_broker_state_path.read_text(encoding="utf-8"))
    assert f"claude:only:{account.home}" in state["meters"]
