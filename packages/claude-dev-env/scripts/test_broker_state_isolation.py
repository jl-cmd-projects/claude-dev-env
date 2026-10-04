"""Broker state written during a test stays out of the home directory."""

from __future__ import annotations

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


def test_meter_cache_write_lands_outside_the_home_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_broker_state_path: Path,
) -> None:
    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
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

    with account_broker.override_subprocess_runner(runner):
        account_broker.run_job(Product.CLAUDE, ["claude"])

    home_state_path = fake_home / ".claude" / "account-broker" / "state.json"
    assert not home_state_path.exists()
    assert f"claude:only:{account.home}" in isolated_broker_state_path.read_text(
        encoding="utf-8"
    )
