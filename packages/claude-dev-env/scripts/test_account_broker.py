from __future__ import annotations

import json
import io
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import account_broker
import claude_account_worker
from account_broker import (
    Account,
    Meters,
    Product,
    ProductAdapter,
    Reading,
    choose_from_readings,
    run_job,
)
from dev_env_scripts_constants.account_broker_constants import WAIT_EXIT_CODE


NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


class _FrozenClock(datetime):
    instant = NOW

    @classmethod
    def now(cls, tz: timezone | None = None) -> datetime:
        if tz is None:
            return cls.instant.replace(tzinfo=None)
        return cls.instant.astimezone(tz)


def _freeze_clock(monkeypatch: pytest.MonkeyPatch, instant: datetime) -> None:
    _FrozenClock.instant = instant
    monkeypatch.setattr(account_broker, "datetime", _FrozenClock)


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(account_broker, "broker_state_path", lambda: tmp_path / "broker" / "state.json")
    monkeypatch.setattr(account_broker.support, "broker_state_path", lambda: tmp_path / "broker" / "state.json")


def _account(name: str, product: Product = Product.CODEX, main: bool = False) -> Account:
    return Account(product, name, Path("/profiles") / name, main, name)


def _meters(
    short_left: float | None,
    weekly_left: float | None,
    *,
    short_reset: datetime | None = None,
    weekly_reset: datetime | None = None,
) -> Meters:
    return Meters(
        short_left,
        short_reset or NOW + timedelta(hours=5),
        weekly_left,
        weekly_reset or NOW + timedelta(days=3),
    )


def _adapter(accounts: tuple[Account, ...], meters: dict[str, Meters | None]) -> ProductAdapter:
    return ProductAdapter(
        load_accounts=lambda: accounts,
        read_meters=lambda account: meters[account.name],
        environment_variable="CODEX_HOME",
        usage_limit_signatures=("rate limit",),
    )


def test_should_name_the_unread_account_and_its_reason_when_no_account_has_room() -> None:
    codex_3 = _account("codex-3")
    codex_4 = _account("codex-4")

    def read_meter(account: Account) -> Meters:
        if account is codex_3:
            raise OSError("codex app-server failed: timed out")
        return _meters(0, 40, short_reset=NOW + timedelta(hours=2))

    adapter = ProductAdapter(lambda: (codex_3, codex_4), read_meter, "CODEX_HOME", ())
    state = account_broker._load_state(account_broker.broker_state_path())
    readings = account_broker.read_accounts(Product.CODEX, adapter, all_state=state, now=NOW)

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)
    payload = account_broker.readings_payload(readings)

    assert decision.action == "wait"
    assert decision.reason == (
        "no readable account has room; meter unreadable for codex-3 (codex app-server failed: timed out); "
        "next check at 2026-10-03T01:00:00+00:00"
    )
    assert payload[0]["unread_reason"] == "codex app-server failed: timed out"
    assert payload[1]["unread_reason"] is None


def test_should_rank_by_room_in_the_tighter_window() -> None:
    readings = (
        Reading(_account("first"), _meters(12, 80)),
        Reading(_account("second"), _meters(70, 40)),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[1].account
    assert decision.tier == "normal"


def test_should_put_unread_accounts_after_readable_accounts() -> None:
    readings = (
        Reading(_account("unread", Product.CLAUDE), None),
        Reading(_account("readable", Product.CLAUDE), _meters(20, 20)),
    )

    decision = choose_from_readings(Product.CLAUDE, readings, now=NOW)

    assert decision.account == readings[1].account


def test_should_keep_list_order_when_tighter_windows_tie() -> None:
    readings = (
        Reading(_account("first"), _meters(40, 60)),
        Reading(_account("second"), _meters(70, 40)),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[0].account


@pytest.mark.parametrize(
    ("weekly_reset", "weekly_left", "short_left"),
    (
        (NOW + timedelta(hours=4), 1, 80),
        (NOW + timedelta(hours=4), 20, 5),
    ),
)
def test_should_guard_main_at_each_limit(
    weekly_reset: datetime, weekly_left: float, short_left: float
) -> None:
    main = Reading(
        _account("main", Product.CLAUDE, main=True),
        _meters(short_left, weekly_left, weekly_reset=weekly_reset),
    )
    extra = Reading(_account("extra", Product.CLAUDE), _meters(20, 20))

    decision = choose_from_readings(Product.CLAUDE, (main, extra), now=NOW)

    assert decision.account == extra.account


def test_should_pick_main_when_it_has_more_room_than_every_extra() -> None:
    main = Reading(
        _account("main", Product.CLAUDE, main=True),
        _meters(80, 80, weekly_reset=NOW + timedelta(days=5)),
    )
    extras = (
        Reading(_account("second", Product.CLAUDE), _meters(60, 60)),
        Reading(_account("third", Product.CLAUDE), _meters(40, 40)),
    )

    decision = choose_from_readings(Product.CLAUDE, (*extras, main), now=NOW)

    assert decision.action == "run"
    assert decision.account == main.account


def test_should_pick_an_extra_with_more_room_than_main() -> None:
    main = Reading(
        _account("main", Product.CLAUDE, main=True),
        _meters(60, 60, weekly_reset=NOW + timedelta(hours=4)),
    )
    extra = Reading(_account("extra", Product.CLAUDE), _meters(90, 90))

    decision = choose_from_readings(Product.CLAUDE, (main, extra), now=NOW)

    assert decision.account == extra.account


@pytest.mark.parametrize(("main_short_left", "expected_name"), ((6, "main"), (5, "extra")))
def test_should_pick_main_only_while_under_its_5_hour_ceiling(
    main_short_left: float, expected_name: str
) -> None:
    main = Reading(
        _account("main", Product.CLAUDE, main=True),
        _meters(main_short_left, 95, weekly_reset=NOW + timedelta(days=5)),
    )
    extra = Reading(_account("extra", Product.CLAUDE), _meters(20, 2))

    decision = choose_from_readings(Product.CLAUDE, (main, extra), now=NOW)

    assert decision.account.name == expected_name


def test_should_pick_main_when_it_is_the_only_readable_account() -> None:
    main = Reading(
        _account("main", Product.CLAUDE, main=True),
        _meters(80, 80, weekly_reset=NOW + timedelta(days=5)),
    )
    unread = Reading(_account("extra", Product.CLAUDE), None)

    decision = choose_from_readings(Product.CLAUDE, (unread, main), now=NOW)

    assert decision.action == "run"
    assert decision.account == main.account


def test_should_wait_for_main_5_hour_reset_while_its_week_resets_days_away() -> None:
    short_reset = NOW + timedelta(hours=2)
    main = Reading(
        _account("main", Product.CLAUDE, main=True),
        _meters(5, 50, short_reset=short_reset, weekly_reset=NOW + timedelta(days=3)),
    )

    decision = choose_from_readings(Product.CLAUDE, (main,), now=NOW)

    assert decision.action == "wait"
    assert decision.resets_at == short_reset


@pytest.mark.parametrize(
    ("short_left", "weekly_left", "weekly_reset", "expected_reset"),
    (
        (5, 20, NOW + timedelta(hours=4), NOW + timedelta(hours=2)),
        (80, 1, NOW + timedelta(hours=4), NOW + timedelta(hours=4)),
    ),
)
def test_should_wait_for_the_meter_or_window_that_blocks_main(
    short_left: float, weekly_left: float, weekly_reset: datetime, expected_reset: datetime
) -> None:
    main = Reading(
        _account("main", Product.CLAUDE, main=True),
        _meters(short_left, weekly_left, short_reset=NOW + timedelta(hours=2), weekly_reset=weekly_reset),
    )

    decision = choose_from_readings(Product.CLAUDE, (main,), now=NOW)

    assert decision.action == "wait"
    assert decision.resets_at == expected_reset


def test_should_try_next_account_after_usage_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    accounts = (_account("first"), _account("second"))
    adapter = _adapter(accounts, {"first": _meters(80, 80), "second": _meters(70, 70)})
    attempted: list[str] = []

    def runner(command: object, **options: object) -> subprocess.CompletedProcess[str]:
        selected = Path(options["env"]["CODEX_HOME"]).name
        attempted.append(selected)
        if selected == "first":
            return subprocess.CompletedProcess(command, 1, "", "rate limit")
        return subprocess.CompletedProcess(command, 0, "served", "")

    report_path = tmp_path / "report.json"
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, adapter)
    with account_broker.override_subprocess_runner(runner):
        outcome, report = account_broker._execute(
        Product.CODEX,
        ("job",),
        now=NOW,
        )
    account_broker._write_report(report_path, report)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert outcome.returncode == 0
    assert attempted == ["first", "second"]
    assert [event["type"] for event in report["events"]] == ["pick", "attempt", "pick", "attempt"]
    assert report["final_decision"]["account"] == "second"


def test_should_wait_for_soonest_reset_and_exit_three(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    accounts = (_account("first"), _account("second"))
    first_reset = NOW + timedelta(hours=5)
    second_reset = NOW + timedelta(hours=3)
    adapter = _adapter(
        accounts,
        {
            "first": _meters(0, 0, short_reset=first_reset, weekly_reset=first_reset),
            "second": _meters(0, 0, short_reset=second_reset, weekly_reset=second_reset),
        },
    )

    report_path = tmp_path / "report.json"
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, adapter)
    with account_broker.override_subprocess_runner(lambda command, **options: pytest.fail("a waiting job ran")):
        outcome, report = account_broker._execute(
        Product.CODEX,
        ("job",),
        now=NOW,
        )
    account_broker._write_report(report_path, report)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert outcome.returncode == WAIT_EXIT_CODE
    assert report["final_decision"]["action"] == "wait"
    assert report["final_decision"]["resets_at"] == second_reset.isoformat()


def test_should_wait_until_both_blocking_windows_reset() -> None:
    short_reset = NOW + timedelta(hours=2)
    weekly_reset = NOW + timedelta(days=2)
    reading = Reading(
        _account("spent"),
        _meters(0, 0, short_reset=short_reset, weekly_reset=weekly_reset),
    )

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.resets_at == weekly_reset


def test_should_use_claude_extra_floors_and_wait_for_unread() -> None:
    blocked = Reading(
        _account("blocked", Product.CLAUDE), _meters(5, 1)
    )
    unread = Reading(_account("unread", Product.CLAUDE), None)

    decision = choose_from_readings(Product.CLAUDE, (blocked, unread), now=NOW)

    assert decision.action == "wait"
    assert decision.account is None


def _ranked_claude_account(name: str, priority: int | None) -> Account:
    return Account(Product.CLAUDE, name, Path("/profiles") / name, False, name, priority)


def test_should_pick_the_first_claude_account_in_priority_order_with_room() -> None:
    readings = (
        Reading(_ranked_claude_account("roomy", 2), _meters(90, 90)),
        Reading(_ranked_claude_account("spent", 0), _meters(5, 90)),
        Reading(_ranked_claude_account("preferred", 1), _meters(20, 20)),
        Reading(_ranked_claude_account("unranked", None), _meters(99, 99)),
    )

    decision = choose_from_readings(Product.CLAUDE, readings, now=NOW)

    assert decision.account.name == "preferred"
    assert "priority 2" in decision.reason


def test_should_fall_back_to_the_roomiest_unranked_claude_account() -> None:
    readings = (
        Reading(_ranked_claude_account("ranked_spent", 0), _meters(5, 5)),
        Reading(_ranked_claude_account("tight", None), _meters(30, 30)),
        Reading(_ranked_claude_account("roomy", None), _meters(60, 60)),
    )

    decision = choose_from_readings(Product.CLAUDE, readings, now=NOW)

    assert decision.account.name == "roomy"


def test_should_keep_resume_affinity_ahead_of_priority() -> None:
    readings = (
        Reading(_ranked_claude_account("first", 0), _meters(90, 90)),
        Reading(_ranked_claude_account("bound", 1), _meters(40, 40)),
    )

    decision = choose_from_readings(Product.CLAUDE, readings, now=NOW, preferred_command="bound")

    assert decision.account.name == "bound"
    assert decision.reason == "resume affinity"


def test_should_wait_when_every_ranked_claude_account_is_spent() -> None:
    readings = (
        Reading(_ranked_claude_account("first", 0), _meters(5, 5)),
        Reading(_ranked_claude_account("second", 1), _meters(0, 50)),
    )

    decision = choose_from_readings(Product.CLAUDE, readings, now=NOW)

    assert decision.action == "wait"


@pytest.mark.parametrize("count", (1, 5))
def test_should_consider_every_account_in_the_roster(count: int) -> None:
    readings = tuple(
        Reading(_account(f"account_{index}"), _meters(30 + index, 30 + index))
        for index in range(count)
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[-1].account


def test_should_use_luna_floor_without_choosing_a_model() -> None:
    reading = Reading(_account("low"), _meters(30, 8))

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.account == reading.account
    assert decision.tier == "luna"
    assert not hasattr(decision, "model")


def test_should_keep_resume_affinity_when_account_has_room() -> None:
    readings = (
        Reading(_account("roomy", Product.CLAUDE), _meters(80, 80)),
        Reading(_account("origin", Product.CLAUDE), _meters(20, 20)),
    )

    decision = choose_from_readings(
        Product.CLAUDE, readings, now=NOW, preferred_command="origin"
    )

    assert decision.account == readings[1].account


def test_should_exit_three_for_check_while_all_accounts_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    account = _account("spent")
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter((account,), {"spent": _meters(0, 0)}),
    )

    assert account_broker.main(("check", "--product", "codex")) == WAIT_EXIT_CODE


def test_should_print_decision_and_meters_for_choose(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("roomy")
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter((account,), {"roomy": _meters(80, 70)}),
    )

    assert account_broker.main(("choose", "--product", "codex")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"]["account"] == "roomy"
    assert payload["accounts"][0]["meters"]["session_percent_left"] == 80
    assert payload["state_path"].endswith("state.json")


def test_should_count_failed_meter_read_as_spent() -> None:
    readings = (
        Reading(_account("unread"), None),
        Reading(_account("roomy"), _meters(70, 70)),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[1].account


def test_should_serialize_readings_with_named_fields() -> None:
    reading = Reading(_account("one"), _meters(80, 70))

    payload = account_broker.readings_payload((reading,))

    assert payload[0]["name"] == "one"
    assert payload[0]["meters"]["weekly_percent_left"] == 70


def test_should_wait_when_all_meter_reads_fail() -> None:
    readings = (Reading(_account("first"), None), Reading(_account("second"), None))

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.action == "wait"
    assert decision.resets_at == NOW + timedelta(hours=1)


_MAIN_CLAUDE = _account("main", Product.CLAUDE, main=True)
_EV_CLAUDE = _account("ev", Product.CLAUDE)


@pytest.mark.parametrize(
    ("readings", "spent_resets", "expected_reason", "expected_resets_at"),
    (
        pytest.param(
            (Reading(_MAIN_CLAUDE, None), Reading(_EV_CLAUDE, None)),
            {},
            "no account meter could be read (main, ev); next check at 2026-10-03T01:00:00+00:00",
            NOW + timedelta(hours=1),
            id="every-meter-unreadable",
        ),
        pytest.param(
            (Reading(_MAIN_CLAUDE, _meters(5, 50, short_reset=NOW + timedelta(minutes=30))), Reading(_EV_CLAUDE, None)),
            {},
            "no readable account has room; meter unreadable for ev; next reset at 2026-10-03T00:30:00+00:00",
            NOW + timedelta(minutes=30),
            id="unreadable-beside-a-reset-before-the-check",
        ),
        pytest.param(
            (Reading(_MAIN_CLAUDE, _meters(5, 50, short_reset=NOW + timedelta(hours=2))), Reading(_EV_CLAUDE, None)),
            {},
            "no readable account has room; meter unreadable for ev; next check at 2026-10-03T01:00:00+00:00",
            NOW + timedelta(hours=1),
            id="unreadable-beside-a-reset-after-the-check",
        ),
        pytest.param(
            (Reading(_MAIN_CLAUDE, _meters(80, 80)), Reading(_EV_CLAUDE, None)),
            {_MAIN_CLAUDE: NOW + timedelta(minutes=30)},
            "no readable account has room; meter unreadable for ev; next reset at 2026-10-03T00:30:00+00:00",
            NOW + timedelta(minutes=30),
            id="unreadable-beside-a-spent-account",
        ),
        pytest.param(
            (
                Reading(_MAIN_CLAUDE, _meters(5, 50, short_reset=NOW + timedelta(hours=2))),
                Reading(_EV_CLAUDE, _meters(5, 80, short_reset=NOW + timedelta(hours=3))),
            ),
            {},
            "no account has room; next reset at 2026-10-03T02:00:00+00:00",
            NOW + timedelta(hours=2),
            id="every-meter-read-with-known-resets",
        ),
        pytest.param(
            (Reading(_MAIN_CLAUDE, Meters(5, None, 50, None)),),
            {},
            "no account has room; next check at 2026-10-03T01:00:00+00:00",
            NOW + timedelta(hours=1),
            id="every-meter-read-without-a-known-reset",
        ),
    ),
)
def test_should_name_what_the_broker_knows_in_the_wait_reason(
    readings: tuple[Reading, ...],
    spent_resets: dict[Account, datetime],
    expected_reason: str,
    expected_resets_at: datetime,
) -> None:
    decision = choose_from_readings(
        Product.CLAUDE,
        readings,
        now=NOW,
        all_spent_accounts=frozenset(spent_resets),
        all_spent_resets=spent_resets,
    )

    assert decision.action == "wait"
    assert decision.reason == expected_reason
    assert decision.resets_at == expected_resets_at


def test_should_carry_the_unreadable_meter_reason_into_the_worker_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter = _adapter((_MAIN_CLAUDE, _EV_CLAUDE), {"main": None, "ev": None})
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CLAUDE, adapter)
    prompt_file = tmp_path / "brief.md"
    prompt_file.write_text("standalone brief", encoding="utf-8")
    report_file = tmp_path / "report.json"

    with account_broker.override_subprocess_runner(lambda command, **options: pytest.fail("a waiting job ran")):
        exit_code = claude_account_worker.run_worker(
            prompt_file=prompt_file,
            cwd=tmp_path,
            report_file=report_file,
            model=None,
            permission_mode="auto",
            timeout_minutes=60,
        )

    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert exit_code == WAIT_EXIT_CODE
    assert report["account"] == "wait"
    assert report["reason"].startswith("no account meter could be read")


def test_should_replay_stdin_bytes_and_only_print_served_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    accounts = (_account("first"), _account("second"))
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter(accounts, {
        "first": _meters(80, 80), "second": _meters(70, 70)
    }))
    original = b"first\r\nsecond\x00\xff"
    received: list[bytes] = []

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        received.append(options["input"])
        if len(received) == 1:
            return subprocess.CompletedProcess(argv, 1, "discard this", "rate limit")
        return subprocess.CompletedProcess(argv, 0, "command output", "")

    monkeypatch.setattr(account_broker.sys, "stdin", io.TextIOWrapper(io.BytesIO(original), encoding="utf-8"))
    report_path = tmp_path / "report.json"
    with account_broker.override_subprocess_runner(runner):
        code = account_broker.main(("run", "--product", "codex", "--report", str(report_path), "--", "job"))

    captured_streams = capsys.readouterr()
    assert code == 0
    assert received == [original, original]
    assert captured_streams.out == "command output"
    assert json.loads(report_path.read_text(encoding="utf-8"))["final_decision"]["account"] == "second"


def test_should_write_wait_report_without_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("spent")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"spent": _meters(0, 0)}))
    monkeypatch.setattr(account_broker.sys, "stdin", io.TextIOWrapper(io.BytesIO(b""), encoding="utf-8"))
    report_path = tmp_path / "report.json"

    code = account_broker.main(("run", "--product", "codex", "--report", str(report_path), "--", "job"))

    assert code == WAIT_EXIT_CODE
    assert capsys.readouterr().out == ""
    final = json.loads(report_path.read_text(encoding="utf-8"))["final_decision"]
    assert final["action"] == "wait"
    assert final["resets_at"] is not None


def test_should_keep_spent_mark_until_reset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    accounts = (_account("first"), _account("second"))
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter(accounts, {
        "first": _meters(80, 80), "second": _meters(70, 70)
    }))
    reset = int((datetime.now(timezone.utc) + timedelta(hours=2)).timestamp())

    assert account_broker.main(("choose", "--product", "codex", "--spent", f"first:{reset}")) == 0
    assert json.loads(capsys.readouterr().out)["decision"]["account"] == "second"
    assert account_broker.main(("choose", "--product", "codex")) == 0
    assert json.loads(capsys.readouterr().out)["decision"]["account"] == "second"


def test_should_leave_later_choices_open_after_start_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    accounts = (_account("first"), _account("second"))
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter(accounts, {
        "first": _meters(80, 80), "second": _meters(70, 70)
    }))

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        raise OSError("missing command")

    with account_broker.override_subprocess_runner(runner):
        outcome, _ = account_broker._execute(Product.CODEX, ("job",), now=datetime.now(timezone.utc))

    assert outcome.attempts == (("first", "start_failed"), ("second", "start_failed"))
    assert account_broker.main(("choose", "--product", "codex")) == 0
    assert json.loads(capsys.readouterr().out)["decision"]["account"] == "first"


@pytest.mark.parametrize("product", (Product.CLAUDE, Product.CODEX))
def test_should_exit_127_when_every_account_fails_to_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, product: Product
) -> None:
    accounts = (_account("first", product), _account("second", product))
    monkeypatch.setitem(account_broker.all_product_adapters, product, _adapter(accounts, {
        "first": _meters(80, 80), "second": _meters(70, 70)
    }))
    monkeypatch.setattr(account_broker.sys, "stdin", io.TextIOWrapper(io.BytesIO(b""), encoding="utf-8"))

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        raise OSError("missing command")

    with account_broker.override_subprocess_runner(runner):
        outcome, _ = account_broker._execute(product, ("job",), now=datetime.now(timezone.utc))
        code = account_broker.main(("run", "--product", product.value, "--report", str(tmp_path / "report.json"), "--", "job"))

    assert outcome.status == "start_failed"
    assert outcome.returncode == 127
    assert outcome.wait_reset_at is None
    assert code == 127


def test_should_report_exhausted_when_start_failure_meets_usage_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accounts = (_account("first"), _account("second"))
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter(accounts, {
        "first": _meters(80, 80), "second": _meters(70, 70)
    }))

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        if Path(options["env"]["CODEX_HOME"]).name == "first":
            raise OSError("missing command")
        return subprocess.CompletedProcess(argv, 1, "", "rate limit")

    with account_broker.override_subprocess_runner(runner):
        outcome, _ = account_broker._execute(Product.CODEX, ("job",), now=datetime.now(timezone.utc))

    assert outcome.attempts == (("first", "start_failed"), ("second", "usage_limited"))
    assert outcome.status == "exhausted"
    assert outcome.returncode == 3


def test_should_stop_after_timeout_without_running_job_again(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    accounts = (_account("first"), _account("second"))
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter(accounts, {
        "first": _meters(80, 80), "second": _meters(70, 70)
    }))
    invoked_homes: list[str] = []

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        invoked_homes.append(Path(options["env"]["CODEX_HOME"]).name)
        raise subprocess.TimeoutExpired("job", 1)

    with account_broker.override_subprocess_runner(runner):
        outcome, report = account_broker._execute(Product.CODEX, ("job",), now=datetime.now(timezone.utc))

    assert invoked_homes == ["first"]
    assert outcome.attempts == (("first", "timeout"),)
    assert outcome.status == "timeout"
    assert outcome.returncode == 124
    assert outcome.account_name == "first"
    assert report.final_decision.account.name == "first"
    assert account_broker.main(("choose", "--product", "codex")) == 0
    assert json.loads(capsys.readouterr().out)["decision"]["account"] == "first"


@pytest.mark.parametrize(
    ("product", "roster_names", "start_error", "expected_code"),
    (
        (Product.CLAUDE, ("first",), subprocess.TimeoutExpired("job", 1), 124),
        (Product.CODEX, ("first",), subprocess.TimeoutExpired("job", 1), 124),
        (Product.CODEX, (), OSError("missing command"), 127),
    ),
)
def test_should_exit_with_job_failure_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    product: Product,
    roster_names: tuple[str, ...],
    start_error: Exception,
    expected_code: int,
) -> None:
    accounts = tuple(_account(each_name, product) for each_name in roster_names)
    monkeypatch.setitem(account_broker.all_product_adapters, product, _adapter(accounts, {
        each_name: _meters(80, 80) for each_name in roster_names
    }))
    monkeypatch.setattr(account_broker.sys, "stdin", io.TextIOWrapper(io.BytesIO(b""), encoding="utf-8"))

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        raise start_error

    with account_broker.override_subprocess_runner(runner):
        code = account_broker.main(("run", "--product", product.value, "--report", str(tmp_path / "report.json"), "--", "job"))

    assert code == expected_code


def test_should_keep_usage_limited_account_spent_for_later_choices(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    accounts = (_account("first"), _account("second"))
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter(accounts, {
        "first": _meters(80, 80), "second": _meters(70, 70)
    }))

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        if Path(options["env"]["CODEX_HOME"]).name == "first":
            return subprocess.CompletedProcess(argv, 1, "", "rate limit")
        return subprocess.CompletedProcess(argv, 0, "served", "")

    with account_broker.override_subprocess_runner(runner):
        account_broker._execute(Product.CODEX, ("job",), now=datetime.now(timezone.utc))

    assert account_broker.main(("choose", "--product", "codex")) == 0
    assert json.loads(capsys.readouterr().out)["decision"]["account"] == "second"


def test_should_list_accounts_without_reading_meters(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("listed")
    adapter = ProductAdapter(lambda: (account,), lambda _: pytest.fail("meter read"), "CODEX_HOME", ())
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, adapter)

    assert account_broker.main(("accounts", "--product", "codex")) == 0
    assert json.loads(capsys.readouterr().out) == {
        "accounts": [{"name": "listed", "home": str(account.home), "is_main": False}]
    }


def test_should_use_default_codex_home_without_roster(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("CODEX_ACCOUNT_PROFILES", raising=False)
    monkeypatch.setattr(account_broker.support.codex_account_choice, "default_profiles_root", lambda: tmp_path / "profiles")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "default"))

    assert account_broker.load_codex_accounts() == ()
    decision = choose_from_readings(Product.CODEX, (), now=NOW)
    assert decision.account.name == "default"
    assert decision.account.home == (tmp_path / "default").resolve()
    assert "no roster" in decision.reason


def test_should_reuse_meter_cache_for_60_seconds() -> None:
    account = _account("cached")
    calls: list[str] = []

    def read_meter(selected: Account) -> Meters:
        calls.append(selected.name)
        return _meters(80, 80)

    adapter = ProductAdapter(lambda: (account,), read_meter, "CODEX_HOME", ())
    state = account_broker._load_state(account_broker.broker_state_path())

    account_broker.read_accounts(Product.CODEX, adapter, all_state=state, now=NOW)
    account_broker.read_accounts(Product.CODEX, adapter, all_state=state, now=NOW + timedelta(seconds=59))
    account_broker.read_accounts(Product.CODEX, adapter, all_state=state, now=NOW + timedelta(seconds=60))
    assert calls == ["cached", "cached"]


def test_should_route_resume_to_bound_account(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    accounts = (_account("first", Product.CLAUDE), _account("second", Product.CLAUDE))
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CLAUDE, _adapter(accounts, {
        "first": _meters(80, 80), "second": _meters(70, 70)
    }))
    chosen: list[str] = []

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        chosen.append(Path(options["env"]["CODEX_HOME"]).name)
        return subprocess.CompletedProcess(argv, 0, '{"session_id":"session-1"}', "")

    with account_broker.override_subprocess_runner(runner):
        first = run_job(Product.CLAUDE, ("job",))
        second = run_job(Product.CLAUDE, ("job", "--resume", "session-1"))

    assert first.session_id == "session-1"
    assert second.account_name == "first"
    assert chosen == ["first", "first"]


def test_should_raise_configuration_error_for_broken_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    directory = tmp_path / ".claude"
    directory.mkdir()
    (directory / "claude-chain.json").write_text('{"chain": "broken"}', encoding="utf-8")

    with pytest.raises(account_broker.BrokerConfigurationError):
        account_broker.load_claude_accounts()


def test_should_wait_when_a_spent_mark_names_an_account_outside_the_roster(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("first")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"first": _meters(80, 80)}))
    _freeze_clock(monkeypatch, NOW)
    sooner = NOW + timedelta(hours=2)
    later = NOW + timedelta(hours=5)

    code = account_broker.main((
        "choose", "--product", "codex",
        "--spent", f"visitor:{int(sooner.timestamp())}",
        "--spent", f"guest:{int(later.timestamp())}",
    ))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == WAIT_EXIT_CODE
    assert decision["action"] == "wait"
    assert decision["account"] is None
    assert decision["resets_at"] == sooner.isoformat()


def test_should_wait_for_spent_default_home_until_the_mark_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "default-home"
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((), {}))
    monkeypatch.setenv("CODEX_HOME", str(home))
    _freeze_clock(monkeypatch, NOW)
    reset = NOW + timedelta(hours=2)

    waiting = account_broker.main(("choose", "--product", "codex", "--spent", f"default:{int(reset.timestamp())}"))
    waiting_decision = json.loads(capsys.readouterr().out)["decision"]
    assert waiting == WAIT_EXIT_CODE
    assert waiting_decision["action"] == "wait"
    assert waiting_decision["resets_at"] == reset.isoformat()

    _FrozenClock.instant = reset + timedelta(seconds=1)
    running = account_broker.main(("choose", "--product", "codex"))
    running_decision = json.loads(capsys.readouterr().out)["decision"]
    assert running == 0
    assert running_decision["action"] == "run"
    assert running_decision["account"] == "default"
    assert running_decision["home"] == str(home.resolve())


def test_should_keep_a_spent_mark_without_a_reset_for_one_hour(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("first")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"first": _meters(80, 80)}))
    _freeze_clock(monkeypatch, NOW)

    code = account_broker.main(("choose", "--product", "codex", "--spent", "guest"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == WAIT_EXIT_CODE
    assert decision["action"] == "wait"
    assert decision["resets_at"] == (NOW + timedelta(hours=1)).isoformat()


def test_should_mark_a_windows_launcher_path_account_spent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    launcher_name = "C:\\Users\\someone\\.local\\bin\\claude-first.cmd"
    first = _account(launcher_name)
    second = _account("second")
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter((first, second), {launcher_name: _meters(80, 80), "second": _meters(80, 80)}),
    )
    _freeze_clock(monkeypatch, NOW)

    code = account_broker.main(("choose", "--product", "codex", "--spent", f"{launcher_name}:{(NOW + timedelta(hours=2)).timestamp()}"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == 0
    assert decision["account"] == "second"


def test_should_reject_an_invalid_spent_reset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("first")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"first": _meters(80, 80)}))

    code = account_broker.main(("choose", "--product", "codex", "--spent", "guest:tomorrow"))

    assert code == 2
    assert "invalid reset" in capsys.readouterr().err


@pytest.mark.parametrize("reset_text", ["inf", "1e20", "-1e20"])
def test_should_reject_a_spent_reset_outside_the_platform_range(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], reset_text: str
) -> None:
    account = _account("first")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"first": _meters(80, 80)}))

    code = account_broker.main(("choose", "--product", "codex", "--spent", f"guest:{reset_text}"))

    assert code == 2
    assert "invalid reset" in capsys.readouterr().err


def test_should_run_past_a_spent_mark_left_by_an_account_removed_from_the_roster(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("first")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"first": _meters(80, 80)}))
    _freeze_clock(monkeypatch, NOW)
    retired_key = account_broker._state_key(_account("retired"))
    account_broker._save_state(
        account_broker.broker_state_path(),
        {"meters": {}, "spent": {retired_key: (NOW + timedelta(days=6)).timestamp()}, "affinity": {}},
    )

    code = account_broker.main(("choose", "--product", "codex"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == 0
    assert decision["action"] == "run"
    assert decision["account"] == "first"


def test_should_run_job_through_override(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    account = _account("only")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"only": _meters(80, 80)}))
    calls: list[bytes] = []

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        calls.append(options["input"])
        return subprocess.CompletedProcess(argv, 0, "done", "")

    with account_broker.override_subprocess_runner(runner):
        outcome = run_job(Product.CODEX, ("job",), stdin_text=b"input")

    assert outcome.status == "served"
    assert outcome.attempts == (("only", "served"),)
    assert calls == [b"input"]


def test_should_record_start_failure_without_launching_a_command_missing_from_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CLAUDE, _adapter(
        (_account("extra", Product.CLAUDE),), {"extra": _meters(80, 80)}
    ))
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(account_broker.support.subprocess, "run", lambda *arguments, **options: pytest.fail("a missing command ran"))

    outcome, _ = account_broker._execute(Product.CLAUDE, ("claude", "-p"), now=NOW)

    assert outcome.attempts == (("extra", "start_failed"),)
    assert outcome.status == "start_failed"
    assert outcome.returncode == 127


def test_should_keep_the_start_failure_text_when_no_account_can_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CLAUDE, _adapter(
        (_account("first", Product.CLAUDE), _account("second", Product.CLAUDE)),
        {"first": _meters(80, 80), "second": _meters(70, 70)},
    ))
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(account_broker.support.subprocess, "run", lambda *arguments, **options: pytest.fail("a missing command ran"))

    outcome, _ = account_broker._execute(Product.CLAUDE, ("claude", "-p"), now=NOW)

    assert outcome.status == "start_failed"
    assert "claude" in outcome.stderr


@pytest.mark.parametrize("marked_name", ["retired", "first"])
def test_should_run_past_a_stored_spent_mark_beyond_the_platform_range(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], marked_name: str
) -> None:
    account = _account("first")
    second = _account("second")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account, second), {"first": _meters(80, 80), "second": _meters(80, 80)}))
    _freeze_clock(monkeypatch, NOW)
    marked_account = account if marked_name == "first" else Account(Product.CODEX, marked_name, Path(), False)
    account_broker._save_state(
        account_broker.broker_state_path(),
        {"meters": {}, "spent": {account_broker._state_key(marked_account): 1e20}, "affinity": {}},
    )

    code = account_broker.main(("choose", "--product", "codex"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == 0
    assert decision["action"] == "run"


def test_should_name_the_outside_spent_mark_when_it_forces_a_wait(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("first")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"first": _meters(80, 80)}))
    _freeze_clock(monkeypatch, NOW)
    reset = NOW + timedelta(hours=2)

    account_broker.main(("choose", "--product", "codex", "--spent", f"visitor:{int(reset.timestamp())}"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert decision["action"] == "wait"
    assert decision["reason"] == f"account visitor outside the roster is spent; next reset at {account_broker._time_text(reset)}"


def test_should_warn_when_a_spent_mark_names_an_account_outside_the_roster(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("first")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"first": _meters(80, 80)}))
    _freeze_clock(monkeypatch, NOW)

    account_broker.main(("choose", "--product", "codex", "--spent", "frist", "--spent", "first"))

    all_warning_lines = capsys.readouterr().err.splitlines()
    assert len(all_warning_lines) == 1
    assert "frist" in all_warning_lines[0]
    assert "outside the roster" in all_warning_lines[0]


def test_should_not_warn_when_the_default_account_is_marked_without_a_roster(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((), {}))
    _freeze_clock(monkeypatch, NOW)
    reset = NOW + timedelta(hours=2)

    account_broker.main(("choose", "--product", "codex", "--spent", f"default:{int(reset.timestamp())}"))

    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    ("all_roster_names", "marked_name"),
    [(("first",), "default"), ((), "visitor")],
)
def test_should_warn_when_a_spent_mark_names_an_account_the_roster_lacks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], all_roster_names: tuple[str, ...], marked_name: str
) -> None:
    all_accounts = tuple(_account(each_name) for each_name in all_roster_names)
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter(all_accounts, {each_name: _meters(80, 80) for each_name in all_roster_names}))
    _freeze_clock(monkeypatch, NOW)
    reset = NOW + timedelta(hours=2)

    account_broker.main(("choose", "--product", "codex", "--spent", f"{marked_name}:{int(reset.timestamp())}"))

    all_warning_lines = capsys.readouterr().err.splitlines()
    assert len(all_warning_lines) == 1
    assert marked_name in all_warning_lines[0]
    assert "outside the roster" in all_warning_lines[0]


@pytest.mark.parametrize("mark", ["", ":1800000000"])
def test_should_reject_a_spent_mark_without_an_account_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], mark: str
) -> None:
    account = _account("first")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"first": _meters(80, 80)}))

    code = account_broker.main(("choose", "--product", "codex", "--spent", mark))

    assert code == 2
    assert "account name" in capsys.readouterr().err
    assert account_broker._load_state(account_broker.broker_state_path())["spent"] == {}


def test_should_serialize_a_run_and_a_wait_decision() -> None:
    account = _account("first")
    reset = NOW + timedelta(hours=2)

    run_payload = account_broker.decision_payload(account_broker.Decision("run", account, None, "first has 80% left", "normal"))
    wait_payload = account_broker.decision_payload(account_broker.Decision("wait", None, reset, "no account has room", "wait"))

    assert run_payload == {"action": "run", "account": "first", "home": str(Path("/profiles/first")), "reason": "first has 80% left", "tier": "normal", "resets_at": None}
    assert wait_payload == {"action": "wait", "account": None, "home": None, "reason": "no account has room", "tier": "wait", "resets_at": reset.isoformat()}


def test_should_print_the_whole_rate_limit_result_for_one_home(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    rate_limit_records = {"rateLimitsByLimitId": {"codex": {"primary": {"usedPercent": 20}}}}
    observed: list[tuple[Path, Path]] = []

    def read_result(codex_path: Path, codex_home: Path) -> dict[str, object]:
        observed.append((codex_path, codex_home))
        return rate_limit_records

    monkeypatch.setattr(account_broker.codex_account_meters, "read_rate_limit_records", read_result)
    home = tmp_path / "codex-2"

    assert account_broker.main(("limits", "--product", "codex", "--home", str(home), "--codex", "codex-bin")) == 0
    assert json.loads(capsys.readouterr().out) == {"home": str(home), "rate_limits": rate_limit_records}
    assert observed == [(Path("codex-bin"), home)]


def test_should_exit_two_when_the_limits_read_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def read_result(_codex_path: Path, _codex_home: Path) -> dict[str, object]:
        raise account_broker.codex_account_meters.CodexMeterUnreadError("codex app-server sent no rate-limit reply")

    monkeypatch.setattr(account_broker.codex_account_meters, "read_rate_limit_records", read_result)

    assert account_broker.main(("limits", "--product", "codex", "--home", str(tmp_path), "--codex", "codex-bin")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no rate-limit reply" in captured.err


def test_should_refuse_limits_for_claude(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        account_broker.main(("limits", "--product", "claude", "--home", str(tmp_path)))
    assert exit_info.value.code == 2
    assert "invalid choice: 'claude'" in capsys.readouterr().err


def test_should_start_claude_job_without_the_parent_session_variables(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    accounts = (_account("first", Product.CLAUDE),)
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CLAUDE, _adapter(accounts, {
        "first": _meters(80, 80)
    }))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent-session")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_SOCKET", "/parent/socket")
    monkeypatch.setenv("UNRELATED_SETTING", "kept")
    all_child_environments: list[dict[str, str]] = []

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        all_child_environments.append(options["env"])
        return subprocess.CompletedProcess(argv, 0, "", "")

    with account_broker.override_subprocess_runner(runner):
        run_job(Product.CLAUDE, ("claude", "-p", "task"))

    child_environment = all_child_environments[0]
    assert "CLAUDE_CODE_SESSION_ID" not in child_environment
    assert "CLAUDECODE" not in child_environment
    assert "CLAUDE_CODE_MESSAGING_SOCKET" not in child_environment
    assert child_environment["UNRELATED_SETTING"] == "kept"
    assert child_environment["CODEX_HOME"] == str(Path("/profiles") / "first")


def test_should_keep_the_parent_environment_for_codex_jobs(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    accounts = (_account("first"),)
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter(accounts, {
        "first": _meters(80, 80)
    }))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent-session")
    all_child_environments: list[dict[str, str]] = []

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        all_child_environments.append(options["env"])
        return subprocess.CompletedProcess(argv, 0, "", "")

    with account_broker.override_subprocess_runner(runner):
        run_job(Product.CODEX, ("codex", "exec", "task"))

    assert all_child_environments[0]["CLAUDE_CODE_SESSION_ID"] == "parent-session"



def test_should_hand_the_live_log_to_the_subprocess_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    live_log = tmp_path / "events.jsonl"
    adapter = _adapter((_account("only"),), {"only": _meters(80, 80)})
    captured_options: dict[str, object] = {}

    def runner(command: object, **options: object) -> subprocess.CompletedProcess[str]:
        captured_options.update(options)
        return subprocess.CompletedProcess(command, 0, "served", "")

    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, adapter)
    with account_broker.override_subprocess_runner(runner):
        outcome, _ = account_broker._execute(Product.CODEX, ("job",), now=NOW, live_log=live_log)

    assert outcome.returncode == 0
    assert captured_options["live_log"] == live_log


def test_decision_payload_should_name_the_chosen_account_and_its_home() -> None:
    account = _account("codex-2")
    decision = account_broker.Decision("run", account, None, "most room", "normal")

    assert account_broker.decision_payload(decision) == {
        "action": "run",
        "account": "codex-2",
        "home": str(Path("/profiles") / "codex-2"),
        "reason": "most room",
        "tier": "normal",
        "resets_at": None,
    }


def test_decision_payload_should_leave_the_account_empty_and_give_the_reset_for_a_wait() -> None:
    reset = datetime(2026, 10, 3, 4, 0, tzinfo=timezone(timedelta(hours=-4)))
    decision = account_broker.Decision("wait", None, reset, "no account has room", "wait")

    payload = account_broker.decision_payload(decision)

    assert payload["account"] is None
    assert payload["home"] is None
    assert payload["resets_at"] == "2026-10-03T08:00:00+00:00"
