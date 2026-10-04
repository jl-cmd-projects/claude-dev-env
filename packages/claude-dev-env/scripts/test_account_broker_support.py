from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import account_broker_support as support
from account_broker_support import Account, Meters, Product, ProductAdapter


def test_should_load_claude_roster_from_both_lists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(support, "default_profile_home", lambda name="extra": tmp_path / "profiles" / name)
    main_home = tmp_path / ".claude"
    main_home.mkdir()
    (main_home / "claude-chain.json").write_text(
        json.dumps({"chain": [{"command": "claude"}, {"command": "alternate", "credentials_path": str(tmp_path / "alternate" / ".credentials.json") }]}),
        encoding="utf-8",
    )
    (main_home / "extra-profiles.json").write_text('["extra"]', encoding="utf-8")

    accounts = support.load_claude_accounts()

    assert [each_account.name for each_account in accounts] == ["main", "alternate", "extra"]
    assert accounts[1].home == (tmp_path / "alternate").resolve()


def test_should_load_codex_roster_without_meter_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(support.codex_account_choice, "default_profiles_root", lambda: tmp_path)
    monkeypatch.setattr(support.codex_account_choice, "codex_account_names", lambda _: ("one",))
    monkeypatch.delenv("CODEX_ACCOUNT_PROFILES", raising=False)
    (tmp_path / "account-launchers.json").write_text('["one"]', encoding="utf-8")

    assert [each_account.name for each_account in support.load_codex_accounts()] == ["one"]


def test_should_read_claude_meters_through_injected_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    usage = SimpleNamespace(
        session_utilization=20.0,
        session_resets_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
        weekly_utilization=30.0,
        weekly_resets_at=None,
    )
    monkeypatch.setattr(support, "probe_account_meters", lambda _: usage)

    meters = support.read_claude_meters(Account(Product.CLAUDE, "one", tmp_path))

    assert meters.session_percent_left == 80.0
    assert meters.weekly_percent_left == 70.0


def test_should_read_codex_meters_through_injected_reader(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    short = SimpleNamespace(duration_minutes=300, used_percent=20.0, resets_at=None)
    weekly = SimpleNamespace(duration_minutes=10080, used_percent=30.0, resets_at=None)
    usage = SimpleNamespace(all_windows=(short, weekly), short_window_percent_left=80.0)
    monkeypatch.setattr(support.codex_account_meters, "resolve_codex_path", lambda _: tmp_path / "codex")
    monkeypatch.setattr(support.codex_account_meters, "read_codex_meters", lambda *_: usage)

    meters = support.read_codex_account_meters(Account(Product.CODEX, "one", tmp_path))

    assert meters.session_percent_left == 80.0
    assert meters.weekly_percent_left == 70.0


def test_should_cache_account_reading_under_injected_state_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(support, "broker_state_path", lambda: tmp_path / "broker" / "state.json")
    account = Account(Product.CODEX, "one", tmp_path / "one")
    seen: list[str] = []

    def reader(selected: Account) -> Meters:
        seen.append(selected.name)
        return Meters(80.0, None, 80.0, None)

    adapter = ProductAdapter(lambda: (account,), reader, "CODEX_HOME", (), False)
    state = support._load_state(support.broker_state_path())
    now = datetime(2026, 10, 3, tzinfo=timezone.utc)

    assert support.read_accounts(Product.CODEX, adapter, all_state=state, now=now)[0].meters is not None
    assert support.read_accounts(Product.CODEX, adapter, all_state=state, now=now)[0].meters is not None
    assert seen == ["one"]
    assert support.broker_state_path().is_file()


def test_should_extract_session_id_and_restore_runner() -> None:
    original = support.subprocess_runner

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, "", "")

    with support.override_subprocess_runner(runner):
        assert support.subprocess_runner is runner
    assert support.subprocess_runner is original
    assert support.extract_session_id_from_stdout('{"session_id":"one"}') == "one"


def test_should_keep_every_concurrent_spent_mark_and_newest_meter_reading(tmp_path: Path) -> None:
    state_path = tmp_path / "broker" / "state.json"
    first_worker = support._load_state(state_path)
    second_worker = support._load_state(state_path)
    first_worker["spent"]["codex:one"] = 2000.0
    first_worker["meters"]["codex:one"] = {"read_at": 500.0, "meters": None}
    support._save_state(state_path, first_worker)
    second_worker["spent"]["codex:two"] = 3000.0
    second_worker["meters"]["codex:one"] = {"read_at": 100.0, "meters": None}
    support._save_state(state_path, second_worker)
    stale_worker = {"meters": {}, "spent": {"codex:one": 1000.0}, "affinity": {"session": "one"}}
    support._save_state(state_path, stale_worker)

    saved = support._load_state(state_path)

    assert saved["spent"] == {"codex:one": 2000.0, "codex:two": 3000.0}
    assert saved["meters"]["codex:one"]["read_at"] == 500.0
    assert saved["affinity"] == {"session": "one"}


def test_should_retry_windows_lock_until_contention_clears(tmp_path: Path) -> None:
    lock_descriptor = os.open(tmp_path / "state.json.lock", os.O_CREAT | os.O_RDWR)
    all_calls: list[tuple[int, int, int]] = []

    def locking(descriptor: int, mode: int, byte_count: int) -> None:
        all_calls.append((descriptor, mode, byte_count))
        if len(all_calls) < 3:
            raise OSError(errno.EDEADLOCK, "Resource deadlock avoided")

    try:
        support._acquire_windows_lock(lock_descriptor, locking, 7)
    finally:
        os.close(lock_descriptor)

    assert all_calls == [(lock_descriptor, 7, 1)] * 3


def test_should_raise_windows_lock_error_other_than_contention(tmp_path: Path) -> None:
    lock_descriptor = os.open(tmp_path / "state.json.lock", os.O_CREAT | os.O_RDWR)
    all_calls: list[int] = []

    def locking(descriptor: int, mode: int, byte_count: int) -> None:
        all_calls.append(descriptor)
        raise OSError(errno.EBADF, "Bad file descriptor")

    try:
        with pytest.raises(OSError):
            support._acquire_windows_lock(lock_descriptor, locking, 7)
    finally:
        os.close(lock_descriptor)

    assert all_calls == [lock_descriptor]


GRANDCHILD_HEARTBEAT_SCRIPT = (
    "import pathlib, sys, time\n"
    "heartbeat = pathlib.Path(sys.argv[1])\n"
    "for each_beat in range(300):\n"
    "    heartbeat.write_text(str(each_beat), encoding='utf-8')\n"
    "    time.sleep(0.1)\n"
)

CHILD_SCRIPT = (
    "import subprocess, sys, time\n"
    "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]])\n"
    "time.sleep(60)\n"
)


def test_should_end_grandchildren_when_the_job_times_out(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "heartbeat.txt"

    with pytest.raises(subprocess.TimeoutExpired):
        support._run_captured_subprocess(
            [sys.executable, "-c", CHILD_SCRIPT, GRANDCHILD_HEARTBEAT_SCRIPT, str(heartbeat_file)],
            timeout=5,
        )

    beat_after_timeout = heartbeat_file.read_text(encoding="utf-8")
    time.sleep(0.5)
    assert heartbeat_file.read_text(encoding="utf-8") == beat_after_timeout
