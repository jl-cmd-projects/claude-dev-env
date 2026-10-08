from __future__ import annotations

import errno
import json
import os
import shutil
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


def _claude_home_with_extras(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, extras: list[str]) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(support, "default_profile_home", lambda name="extra": tmp_path / "profiles" / name)
    main_home = tmp_path / ".claude"
    main_home.mkdir()
    (main_home / "extra-profiles.json").write_text(json.dumps(extras), encoding="utf-8")
    return main_home


def test_should_leave_claude_priorities_unset_without_an_order_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _claude_home_with_extras(monkeypatch, tmp_path, ["first", "second"])

    accounts = support.load_claude_accounts()

    assert [each_account.priority for each_account in accounts] == [None, None, None]


def test_should_assign_claude_priorities_from_the_order_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    main_home = _claude_home_with_extras(monkeypatch, tmp_path, ["first", "second", "unlisted"])
    (main_home / "claude-account-order.json").write_text(
        json.dumps(["claude-second", "missing", "claude", "FIRST"]), encoding="utf-8"
    )

    accounts = support.load_claude_accounts()

    assert {each_account.name: each_account.priority for each_account in accounts} == {
        "main": 2,
        "first": 3,
        "second": 0,
        "unlisted": None,
    }


def test_should_read_an_order_file_saved_with_a_byte_order_mark(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    main_home = _claude_home_with_extras(monkeypatch, tmp_path, ["first"])
    (main_home / "claude-account-order.json").write_text('["first"]', encoding="utf-8-sig")

    accounts = support.load_claude_accounts()

    assert {each_account.name: each_account.priority for each_account in accounts} == {"main": None, "first": 0}


def test_should_reject_an_order_file_that_is_not_a_list_of_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    main_home = _claude_home_with_extras(monkeypatch, tmp_path, ["first"])
    (main_home / "claude-account-order.json").write_text('{"order": ["first"]}', encoding="utf-8")

    with pytest.raises(support.BrokerConfigurationError, match="claude-account-order.json"):
        support.load_claude_accounts()


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


def _codex_meter_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, all_outcomes: list[object]
) -> list[Path]:
    all_homes_read: list[Path] = []

    def read_codex_meters(_codex_path: Path, codex_home: Path) -> object:
        all_homes_read.append(codex_home)
        outcome = all_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(support.codex_account_meters, "resolve_codex_path", lambda _: tmp_path / "codex")
    monkeypatch.setattr(support.codex_account_meters, "read_codex_meters", read_codex_meters)
    return all_homes_read


def test_should_read_codex_meters_again_after_one_failed_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    weekly = SimpleNamespace(duration_minutes=10080, used_percent=30.0, resets_at=None)
    usage = SimpleNamespace(all_windows=(weekly,), short_window_percent_left=None)
    unread = support.codex_account_meters.CodexMeterUnreadError("codex app-server sent no rate-limit reply")
    all_homes_read = _codex_meter_reads(monkeypatch, tmp_path, [unread, usage])

    meters = support.read_codex_account_meters(Account(Product.CODEX, "one", tmp_path))

    assert meters is not None
    assert meters.weekly_percent_left == 70.0
    assert all_homes_read == [tmp_path, tmp_path]


def test_should_keep_the_unread_reason_after_two_failed_codex_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(support, "broker_state_path", lambda: tmp_path / "broker" / "state.json")
    first_unread = support.codex_account_meters.CodexMeterUnreadError("codex app-server failed: timed out")
    second_unread = support.codex_account_meters.CodexMeterUnreadError("codex app-server sent no rate-limit reply")
    all_homes_read = _codex_meter_reads(monkeypatch, tmp_path, [first_unread, second_unread])
    account = Account(Product.CODEX, "codex-3", tmp_path)
    adapter = ProductAdapter(lambda: (account,), support.read_codex_account_meters, "CODEX_HOME", ())
    state = support._load_state(support.broker_state_path())
    now = datetime(2026, 10, 3, tzinfo=timezone.utc)

    first_reading = support.read_accounts(Product.CODEX, adapter, all_state=state, now=now)[0]
    cached_reading = support.read_accounts(Product.CODEX, adapter, all_state=state, now=now)[0]

    assert first_reading.meters is None
    assert first_reading.unread_reason == "codex app-server sent no rate-limit reply"
    assert cached_reading.unread_reason == "codex app-server sent no rate-limit reply"
    assert all_homes_read == [tmp_path, tmp_path]


def test_should_cache_account_reading_under_injected_state_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(support, "broker_state_path", lambda: tmp_path / "broker" / "state.json")
    account = Account(Product.CODEX, "one", tmp_path / "one")
    seen: list[str] = []

    def reader(selected: Account) -> Meters:
        seen.append(selected.name)
        return Meters(80.0, None, 80.0, None)

    adapter = ProductAdapter(lambda: (account,), reader, "CODEX_HOME", ())
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


def test_should_end_grandchildren_when_the_broker_is_interrupted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    heartbeat_file = tmp_path / "heartbeat.txt"
    original_communicate = subprocess.Popen.communicate

    def interrupted_communicate(process: subprocess.Popen[bytes], *args: object, **kwargs: object) -> object:
        try:
            return original_communicate(process, *args, timeout=5)
        except subprocess.TimeoutExpired:
            raise KeyboardInterrupt from None

    monkeypatch.setattr(subprocess.Popen, "communicate", interrupted_communicate)

    with pytest.raises(KeyboardInterrupt):
        support._run_captured_subprocess(
            [sys.executable, "-c", CHILD_SCRIPT, GRANDCHILD_HEARTBEAT_SCRIPT, str(heartbeat_file)],
        )

    beat_after_interrupt = heartbeat_file.read_text(encoding="utf-8")
    time.sleep(0.5)
    assert heartbeat_file.read_text(encoding="utf-8") == beat_after_interrupt


def _record_launches(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    all_launched_argv: list[list[str]] = []

    class FakeProcess:
        returncode = 0

        def __init__(self, all_argv: list[str], **options: object) -> None:
            all_launched_argv.append(list(all_argv))

        def __enter__(self) -> "FakeProcess":
            return self

        def __exit__(self, *exception_info: object) -> None:
            return None

        def communicate(self, **options: object) -> tuple[None, None]:
            return None, None

    monkeypatch.setattr(support.subprocess, "Popen", FakeProcess)
    return all_launched_argv


def test_should_launch_the_path_resolved_command_file(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved_command = r"C:\Users\someone\AppData\Roaming\npm\claude.cmd"
    monkeypatch.setattr(shutil, "which", lambda name: resolved_command if name == "claude" else None)
    all_launched_argv = _record_launches(monkeypatch)

    completion = support.subprocess_runner(["claude", "-p"], input=b"", encoding="utf-8", errors="replace")

    assert all_launched_argv == [[resolved_command, "-p"]]
    assert completion.returncode == 0


def test_should_refuse_to_launch_a_bare_command_missing_from_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(support.subprocess, "Popen", lambda *arguments, **options: pytest.fail("a missing command ran"))

    with pytest.raises(FileNotFoundError) as raised:
        support.subprocess_runner(["claude", "-p"])

    assert raised.value.errno == errno.ENOENT
    assert raised.value.filename == "claude"


@pytest.mark.parametrize("metacharacter", ["&", "|", "<", ">", "^", "%", "!", '"', "\n", "\r"])
def test_should_refuse_a_batch_file_argument_that_cmd_would_parse(
    monkeypatch: pytest.MonkeyPatch, metacharacter: str
) -> None:
    resolved_command = r"C:\Users\someone\AppData\Roaming\npm\claude.cmd"
    monkeypatch.setattr(shutil, "which", lambda name: resolved_command)
    monkeypatch.setattr(support.subprocess, "Popen", lambda *arguments, **options: pytest.fail("a batch file ran"))

    with pytest.raises(OSError) as raised:
        support.subprocess_runner(["claude", "-p", f"fix{metacharacter}test"])

    assert raised.value.errno == errno.EINVAL
    assert raised.value.filename == resolved_command
    assert "stdin" in raised.value.strerror


def test_should_refuse_metacharacters_for_an_uppercase_bat_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved_command = r"C:\tools\CLAUDE.BAT"
    monkeypatch.setattr(shutil, "which", lambda name: resolved_command)
    monkeypatch.setattr(support.subprocess, "Popen", lambda *arguments, **options: pytest.fail("a batch file ran"))

    with pytest.raises(OSError) as raised:
        support.subprocess_runner(["claude", "a & b"])

    assert raised.value.errno == errno.EINVAL


def test_should_launch_a_batch_file_with_flags_only(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved_command = r"C:\Users\someone\AppData\Roaming\npm\claude.cmd"
    monkeypatch.setattr(shutil, "which", lambda name: resolved_command)
    all_launched_argv = _record_launches(monkeypatch)

    support.subprocess_runner(["claude", "-p", "--output-format", "json", "--model", "opus"], input=b"a & b")

    assert all_launched_argv == [[resolved_command, "-p", "--output-format", "json", "--model", "opus"]]


def test_should_pass_metacharacters_to_an_executable_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved_command = "/usr/local/bin/claude"
    monkeypatch.setattr(shutil, "which", lambda name: resolved_command)
    all_launched_argv = _record_launches(monkeypatch)

    support.subprocess_runner(["claude", "-p", 'say "a & b" | 100%!'])

    assert all_launched_argv == [[resolved_command, "-p", 'say "a & b" | 100%!']]
