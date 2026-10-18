"""Broker state written during a test lands in the per-test home directory."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import account_broker
from dev_env_scripts_constants.account_broker_constants import (
    Account,
    Meters,
    Product,
    ProductAdapter,
)


def test_meter_cache_write_lands_in_the_isolated_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_home: Path,
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

    isolated_broker_state_path = account_broker.broker_state_path()
    assert Path.home() == isolated_home
    assert isolated_broker_state_path.is_relative_to(isolated_home)
    assert not isolated_broker_state_path.exists()
    with account_broker.override_subprocess_runner(runner):
        account_broker.run_job(Product.CLAUDE, ["claude"])

    state = json.loads(isolated_broker_state_path.read_text(encoding="utf-8"))
    assert f"claude:only:{account.home}" in state["meters"]
