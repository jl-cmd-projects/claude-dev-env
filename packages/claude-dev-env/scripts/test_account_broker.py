from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import account_broker
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
        main_guard=False,
    )


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
        (NOW + timedelta(days=3), 20, 80),
        (NOW + timedelta(hours=4), 10, 80),
        (NOW + timedelta(hours=4), 20, 50),
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


def test_should_prioritize_main_when_its_guard_passes() -> None:
    main = Reading(
        _account("main", Product.CLAUDE, main=True),
        _meters(80, 20, weekly_reset=NOW + timedelta(hours=4)),
    )
    extra = Reading(_account("extra", Product.CLAUDE), _meters(90, 90))

    decision = choose_from_readings(Product.CLAUDE, (main, extra), now=NOW)

    assert decision.account == main.account


def test_should_try_next_account_after_usage_limit(tmp_path: Path) -> None:
    accounts = (_account("first"), _account("second"))
    adapter = _adapter(accounts, {"first": _meters(80, 80), "second": _meters(70, 70)})
    attempted: list[str] = []

    def runner(command: object, environment: object) -> subprocess.CompletedProcess[str]:
        selected = Path(environment["CODEX_HOME"]).name
        attempted.append(selected)
        if selected == "first":
            return subprocess.CompletedProcess(command, 1, "", "rate limit")
        return subprocess.CompletedProcess(command, 0, "served", "")

    report_path = tmp_path / "report.json"
    exit_code = run_job(
        Product.CODEX,
        ("job",),
        report_path,
        adapter=adapter,
        runner=runner,
        now=NOW,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert attempted == ["first", "second"]
    assert [event["type"] for event in report["events"]] == [
        "pick", "attempt", "usage_limit", "pick", "attempt"
    ]
    assert report["final_decision"]["account"] == "second"


def test_should_wait_for_soonest_reset_and_exit_three(tmp_path: Path) -> None:
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
    exit_code = run_job(
        Product.CODEX,
        ("job",),
        report_path,
        adapter=adapter,
        runner=lambda command, environment: pytest.fail("a waiting job ran"),
        now=NOW,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == WAIT_EXIT_CODE
    assert report["final_decision"]["action"] == "wait"
    assert report["final_decision"]["reset_at"] == second_reset.isoformat()


def test_should_wait_until_both_blocking_windows_reset() -> None:
    short_reset = NOW + timedelta(hours=2)
    weekly_reset = NOW + timedelta(days=2)
    reading = Reading(
        _account("spent"),
        _meters(0, 0, short_reset=short_reset, weekly_reset=weekly_reset),
    )

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.reset_at == weekly_reset


def test_should_use_claude_extra_floors_and_unread_fallback() -> None:
    blocked = Reading(
        _account("blocked", Product.CLAUDE), _meters(10, 5)
    )
    unread = Reading(_account("unread", Product.CLAUDE), None)

    decision = choose_from_readings(Product.CLAUDE, (blocked, unread), now=NOW)

    assert decision.account == unread.account


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
        account_broker.ADAPTERS,
        Product.CODEX,
        _adapter((account,), {"spent": _meters(0, 0)}),
    )

    assert account_broker.main(("check", "--product", "codex")) == WAIT_EXIT_CODE


def test_should_print_decision_and_meters_for_choose(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("roomy")
    monkeypatch.setitem(
        account_broker.ADAPTERS,
        Product.CODEX,
        _adapter((account,), {"roomy": _meters(80, 70)}),
    )

    assert account_broker.main(("choose", "--product", "codex")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"]["account"] == "roomy"
    assert payload["accounts"][0]["meters"]["session_percent_left"] == 80
