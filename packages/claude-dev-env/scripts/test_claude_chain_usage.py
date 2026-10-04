"""Tests for Claude meter probes used by the account broker."""

from __future__ import annotations

import subprocess
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

import claude_chain_usage as usage
from dev_env_scripts_constants.claude_chain_usage_constants import RESOLVE_USAGE_WINDOW_MODULE_NAME


def test_probe_reads_both_meters_and_resets(monkeypatch: pytest.MonkeyPatch) -> None:
    session_reset = datetime(2026, 10, 4, tzinfo=timezone.utc)
    weekly_reset = datetime(2026, 10, 7, tzinfo=timezone.utc)

    class Windows:
        session_utilization = 12.0
        session_resets_at = session_reset
        weekly_utilization = 64.0
        weekly_resets_at = weekly_reset

    class Resolver:
        def read_oauth_access_token(self, credentials_path: Path, now: datetime) -> str:
            assert credentials_path == Path("account.json")
            return "fixture-token"

        def _fetch_usage_payload(self, access_token: str) -> dict[str, object]:
            assert access_token == "fixture-token"
            return {"usage": 64.0}

        def extract_usage_windows(self, payload: dict[str, object]) -> Windows:
            assert payload == {"usage": 64.0}
            return Windows()

    monkeypatch.setattr(usage, "_load_resolve_usage_window_module", lambda: Resolver())

    assert usage.probe_account_meters(Path("account.json")) == usage.AccountUsageMeters(
        12.0, session_reset, 64.0, weekly_reset
    )


def test_probe_rejects_missing_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    class Resolver:
        def read_oauth_access_token(self, credentials_path: Path, now: datetime) -> None:
            return None

        def _fetch_usage_payload(self, access_token: str) -> dict[str, object]:
            pytest.fail("meter request must not run")

    monkeypatch.setattr(usage, "_load_resolve_usage_window_module", lambda: Resolver())

    with pytest.raises(usage.WeeklyUtilizationProbeError, match="bearer token"):
        usage.probe_account_meters(Path("account.json"))


def test_probe_wraps_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class Resolver:
        def read_oauth_access_token(self, credentials_path: Path, now: datetime) -> str:
            return "fixture-token"

        def _fetch_usage_payload(self, access_token: str) -> dict[str, object]:
            raise urllib.error.URLError("unavailable")

    monkeypatch.setattr(usage, "_load_resolve_usage_window_module", lambda: Resolver())

    with pytest.raises(usage.WeeklyUtilizationProbeError, match="unavailable"):
        usage.probe_account_meters(Path("account.json"))


def test_failed_module_load_does_not_poison_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delitem(sys.modules, RESOLVE_USAGE_WINDOW_MODULE_NAME, raising=False)
    (tmp_path / "resolve_usage_window.py").write_text(
        "raise ImportError('intentional load failure')\n", encoding="utf-8"
    )
    monkeypatch.setattr(usage, "_usage_pause_scripts_directory", lambda: tmp_path)

    with pytest.raises(ImportError, match="intentional load failure"):
        usage._load_resolve_usage_window_module()

    assert RESOLVE_USAGE_WINDOW_MODULE_NAME not in sys.modules


def test_loader_reuses_cached_probe_module() -> None:
    first = usage._load_resolve_usage_window_module()

    assert callable(first.read_oauth_access_token)
    assert callable(first.extract_usage_windows)
    assert usage._load_resolve_usage_window_module() is first


def test_usage_module_imports_without_picker() -> None:
    scripts_directory = str(Path(__file__).resolve().parent)
    import_probe = (
        "import sys; "
        f"sys.path.insert(0, {scripts_directory!r}); "
        "import claude_chain_usage; "
        "assert callable(claude_chain_usage.probe_account_meters)"
    )
    completed = subprocess.run(
        [sys.executable, "-S", "-E", "-c", import_probe],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
