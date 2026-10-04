"""Tests for Claude meter probes used by the account broker."""

from __future__ import annotations

import importlib
import os
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


def test_probe_reads_the_session_token_for_the_session_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_credentials = Path("home") / ".claude" / ".credentials.json"
    all_fetched_tokens: list[str] = []

    class Windows:
        session_utilization = 15.0
        session_resets_at = None
        weekly_utilization = 70.0
        weekly_resets_at = None

    class Resolver:
        def read_oauth_access_token(self, credentials_path: Path, now: datetime) -> None:
            return None

        def default_credentials_path(self) -> Path:
            return session_credentials

        def read_session_ingress_token(self) -> str:
            return "session-token"

        def _fetch_usage_payload(self, access_token: str) -> dict[str, object]:
            all_fetched_tokens.append(access_token)
            return {"usage": 70.0}

        def extract_usage_windows(self, payload: dict[str, object]) -> Windows:
            return Windows()

    monkeypatch.setattr(usage, "_load_resolve_usage_window_module", lambda: Resolver())

    assert usage.probe_account_meters(session_credentials) == usage.AccountUsageMeters(
        15.0, None, 70.0, None
    )
    assert all_fetched_tokens == ["session-token"]


def test_probe_rejects_missing_access_token_for_another_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Resolver:
        def read_oauth_access_token(self, credentials_path: Path, now: datetime) -> None:
            return None

        def default_credentials_path(self) -> Path:
            return Path("home") / ".claude" / ".credentials.json"

        def read_session_ingress_token(self) -> str:
            return "session-token"

        def _fetch_usage_payload(self, access_token: str) -> dict[str, object]:
            pytest.fail("meter request must not run")

    monkeypatch.setattr(usage, "_load_resolve_usage_window_module", lambda: Resolver())

    with pytest.raises(usage.WeeklyUtilizationProbeError, match="bearer token"):
        usage.probe_account_meters(Path("home") / ".claude-profiles" / "ev" / ".credentials.json")


def _create_directory_link(*, from_link: Path, to_target: Path) -> None:
    if sys.platform.startswith("win32"):
        importlib.import_module("_winapi").CreateJunction(str(to_target), str(from_link))
        return
    os.symlink(to_target, from_link, target_is_directory=True)


def test_scripts_directory_follows_the_installed_scripts_link(tmp_path: Path) -> None:
    home = tmp_path.resolve()
    (home / ".agents" / "scripts").mkdir(parents=True)
    (home / ".claude").mkdir()
    _create_directory_link(
        from_link=home / ".claude" / "scripts", to_target=home / ".agents" / "scripts"
    )

    scripts_directory = usage._usage_pause_scripts_directory(
        home / ".claude" / "scripts" / "claude_chain_usage.py"
    )

    assert scripts_directory == home / ".agents" / "skills" / "usage-pause" / "scripts"


def test_scripts_directory_in_the_package_tree(tmp_path: Path) -> None:
    package_root = tmp_path.resolve() / "claude-dev-env"

    scripts_directory = usage._usage_pause_scripts_directory(
        package_root / "scripts" / "claude_chain_usage.py"
    )

    assert scripts_directory == package_root / ".agents" / "skills" / "usage-pause" / "scripts"


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
    monkeypatch.setattr(usage, "_usage_pause_scripts_directory", lambda _module_file: tmp_path)

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
