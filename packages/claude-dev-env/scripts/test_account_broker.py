from __future__ import annotations

import json
import io
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import account_broker
import account_broker_support
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
from dev_env_scripts_constants import codex_account_constants
from dev_env_scripts_constants.account_broker_constants import WAIT_EXIT_CODE
from dev_env_scripts_constants.claude_chain_usage_constants import NO_ACCESS_TOKEN_ERROR_TEMPLATE


NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)
DEFAULT_PLAN = "team"


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


def _account(name: str, product: Product = Product.CODEX, main: bool = False) -> Account:
    return Account(product, name, Path("/profiles") / name, main, name)


def _meters(
    short_left: float | None,
    weekly_left: float | None,
    *,
    short_reset: datetime | None = None,
    weekly_reset: datetime | None = None,
    plan_type: str | None = DEFAULT_PLAN,
    credit_balance: float | None = None,
    is_credits_unlimited: bool = False,
) -> Meters:
    return Meters(
        short_left,
        short_reset or NOW + timedelta(hours=5),
        weekly_left,
        weekly_reset or NOW + timedelta(days=3),
        plan_type,
        credit_balance is not None,
        is_credits_unlimited,
        credit_balance,
    )


def _adapter(accounts: tuple[Account, ...], meters: dict[str, Meters | None]) -> ProductAdapter:
    return ProductAdapter(
        load_accounts=lambda: accounts,
        read_meters=lambda account: meters[account.name],
        environment_variable="CODEX_HOME",
        usage_limit_signatures=("rate limit",),
    )


def test_should_name_the_unread_account_and_its_reason_when_no_account_has_room(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(account_broker_support.time, "sleep", lambda _: None)
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
        "no readable account has room (codex-4 0% left); meter unreadable for codex-3 (codex app-server failed: timed out); "
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


def test_should_pick_a_pro_plan_account_over_a_roomier_team_account() -> None:
    readings = (
        Reading(_account("team-mel"), _meters(90, 85, plan_type="team")),
        Reading(_account("personal"), _meters(40, 30, plan_type="promax")),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[1].account
    assert decision.tier == "normal"


def test_should_pick_a_pro_plan_account_below_the_floor_over_a_team_account_in_the_normal_tier() -> None:
    readings = (
        Reading(_account("personal"), _meters(50, 8, plan_type="pro")),
        Reading(_account("team-jon"), _meters(40, 30, plan_type="team")),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[0].account
    assert decision.tier == "luna"


FREE_PLAN = "free"
TEAM_PLAN = "team"
PRO_PLAN = "prolite"
CREDIT_BALANCE = 83600.8856485


def _current_roster() -> tuple[Reading, ...]:
    return (
        Reading(_account("editor"), _meters(None, 100, plan_type=FREE_PLAN)),
        Reading(_account("team-mel"), _meters(None, 81, plan_type=TEAM_PLAN)),
        Reading(_account("team-jon"), _meters(None, 81, plan_type=TEAM_PLAN)),
        Reading(_account("personal"), _meters(None, 1, plan_type=PRO_PLAN, credit_balance=CREDIT_BALANCE)),
    )


def test_should_choose_the_pro_account_with_credits_over_free_and_team_accounts_with_more_room() -> None:
    readings = _current_roster()

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.action == "run"
    assert decision.account == readings[3].account
    assert decision.tier == "normal"
    assert decision.reason == "personal has 1% left and credits"


def test_should_choose_the_current_roster_through_the_choose_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    readings = _current_roster()
    all_meters = {each_reading.account.name: each_reading.meters for each_reading in readings}
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter(tuple(each_reading.account for each_reading in readings), all_meters),
    )

    exit_code = account_broker.main(("choose", "--product", "codex"))

    payload = json.loads(capsys.readouterr().out)
    personal_entry = next(each_entry for each_entry in payload["accounts"] if each_entry["name"] == "personal")
    assert exit_code == 0
    assert payload["decision"]["account"] == "personal"
    assert payload["decision"]["tier"] == "normal"
    assert personal_entry["meters"]["plan_type"] == PRO_PLAN
    assert personal_entry["meters"]["has_credits"] is True
    assert personal_entry["meters"]["credit_balance"] == CREDIT_BALANCE


def test_should_never_choose_a_free_account_even_when_it_has_the_most_room() -> None:
    readings = (
        Reading(_account("editor"), _meters(100, 100, plan_type=FREE_PLAN)),
        Reading(_account("team"), _meters(40, 5, plan_type=TEAM_PLAN)),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[1].account
    assert decision.tier == "luna"


@pytest.mark.parametrize(
    ("credit_balance", "is_credits_unlimited"), ((None, False), (CREDIT_BALANCE, False), (None, True))
)
def test_should_wait_and_name_the_free_plan_when_the_only_account_is_free(
    credit_balance: float | None, is_credits_unlimited: bool
) -> None:
    reading = Reading(
        _account("editor"),
        _meters(100, 100, plan_type=FREE_PLAN, credit_balance=credit_balance, is_credits_unlimited=is_credits_unlimited),
    )

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.action == "wait"
    assert decision.account is None
    assert decision.reason == (
        "no account has room (editor is on a free plan and is never chosen); next check at 2026-10-03T01:00:00+00:00"
    )


def test_should_exit_three_for_check_when_the_only_account_is_free(monkeypatch: pytest.MonkeyPatch) -> None:
    account = _account("editor")
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter((account,), {"editor": _meters(100, 100, plan_type=FREE_PLAN)}),
    )

    assert account_broker.main(("check", "--product", "codex")) == WAIT_EXIT_CODE


def test_should_not_run_a_job_on_a_free_account(monkeypatch: pytest.MonkeyPatch) -> None:
    account = _account("editor")
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter((account,), {"editor": _meters(100, 100, plan_type=FREE_PLAN)}),
    )
    all_invoked_homes: list[str] = []

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        all_invoked_homes.append(Path(options["env"]["CODEX_HOME"]).name)
        return subprocess.CompletedProcess(argv, 0, "served", "")

    with account_broker.override_subprocess_runner(runner):
        outcome, _ = account_broker._execute(Product.CODEX, ("job",), now=NOW)

    assert all_invoked_homes == []
    assert outcome.status == "wait"
    assert outcome.returncode == WAIT_EXIT_CODE


def _pro_below_the_normal_bar_beside_a_roomy_team() -> tuple[Reading, ...]:
    return (
        Reading(_account("team"), _meters(None, 90, plan_type=TEAM_PLAN)),
        Reading(_account("personal"), _meters(None, 5, plan_type="pro")),
    )


def test_should_give_a_caller_with_no_tier_requirement_the_pro_account_in_the_luna_tier() -> None:
    readings = _pro_below_the_normal_bar_beside_a_roomy_team()

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[1].account
    assert decision.tier == "luna"


def test_should_give_a_caller_that_requires_the_normal_tier_the_team_account_over_a_pro_account_in_luna() -> None:
    readings = _pro_below_the_normal_bar_beside_a_roomy_team()

    decision = choose_from_readings(Product.CODEX, readings, now=NOW, required_tier="normal")

    assert decision.action == "run"
    assert decision.account == readings[0].account
    assert decision.tier == "normal"


def test_should_give_a_caller_that_requires_the_normal_tier_the_pro_account_when_it_qualifies() -> None:
    readings = (
        Reading(_account("team"), _meters(None, 90, plan_type=TEAM_PLAN)),
        Reading(_account("personal"), _meters(None, 30, plan_type="pro")),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW, required_tier="normal")

    assert decision.account == readings[1].account
    assert decision.tier == "normal"


def test_should_give_a_caller_that_requires_the_normal_tier_a_pro_account_that_runs_on_credits() -> None:
    readings = (
        Reading(_account("team"), _meters(None, 90, plan_type=TEAM_PLAN)),
        Reading(_account("personal"), _meters(None, 0.5, plan_type="pro", credit_balance=CREDIT_BALANCE)),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW, required_tier="normal")

    assert decision.account == readings[1].account
    assert decision.tier == "normal"


def test_should_wait_for_a_caller_that_requires_the_normal_tier_when_every_account_is_in_luna() -> None:
    readings = (
        Reading(_account("team"), _meters(None, 5, plan_type=TEAM_PLAN)),
        Reading(_account("personal"), _meters(None, 5, plan_type="pro")),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW, required_tier="normal")

    assert decision.action == "wait"
    assert decision.account is None
    assert decision.tier == "wait"


def test_should_never_give_a_caller_that_requires_the_normal_tier_a_free_account_with_more_room() -> None:
    readings = (
        Reading(_account("editor"), _meters(100, 100, plan_type=FREE_PLAN)),
        Reading(_account("team"), _meters(None, 5, plan_type=TEAM_PLAN)),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW, required_tier="normal")

    assert decision.action == "wait"


def test_should_leave_a_claude_choice_unchanged_for_a_caller_that_requires_the_normal_tier() -> None:
    readings = (
        Reading(_account("first", Product.CLAUDE), _meters(12, 80)),
        Reading(_account("second", Product.CLAUDE), _meters(70, 40)),
    )

    without_requirement = choose_from_readings(Product.CLAUDE, readings, now=NOW)
    with_requirement = choose_from_readings(Product.CLAUDE, readings, now=NOW, required_tier="normal")

    assert with_requirement == without_requirement


def test_should_pass_the_required_tier_through_the_choose_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    readings = _pro_below_the_normal_bar_beside_a_roomy_team()
    all_meters = {each_reading.account.name: each_reading.meters for each_reading in readings}
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter(tuple(each_reading.account for each_reading in readings), all_meters),
    )

    without_requirement_code = account_broker.main(("choose", "--product", "codex"))
    without_requirement = json.loads(capsys.readouterr().out)["decision"]
    with_requirement_code = account_broker.main(("choose", "--product", "codex", "--require-tier", "normal"))
    with_requirement = json.loads(capsys.readouterr().out)["decision"]

    assert (without_requirement_code, without_requirement["account"], without_requirement["tier"]) == (0, "personal", "luna")
    assert (with_requirement_code, with_requirement["account"], with_requirement["tier"]) == (0, "team", "normal")


def test_should_exit_three_with_a_wait_answer_when_the_required_tier_has_no_account(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("personal")
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter((account,), {"personal": _meters(None, 5, plan_type="pro")}),
    )

    exit_code = account_broker.main(("choose", "--product", "codex", "--require-tier", "normal"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert exit_code == WAIT_EXIT_CODE
    assert decision["action"] == "wait"
    assert decision["tier"] == "wait"


def test_should_refuse_a_required_tier_the_broker_does_not_name(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        account_broker.main(("choose", "--product", "codex", "--require-tier", "turbo"))

    assert raised.value.code == 2
    assert "invalid choice: 'turbo'" in capsys.readouterr().err


UNKNOWN_PLAN = "unknown"
NO_PLAN_VALUES = (None, UNKNOWN_PLAN, "Unknown", " UNKNOWN ", "")


@pytest.mark.parametrize("plan_type", NO_PLAN_VALUES)
def test_should_never_choose_an_account_with_no_known_plan_even_when_it_has_the_most_room(plan_type: str | None) -> None:
    readings = (
        Reading(_account("unlabelled"), _meters(100, 100, plan_type=plan_type)),
        Reading(_account("team"), _meters(40, 5, plan_type=TEAM_PLAN)),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[1].account
    assert decision.tier == "luna"


@pytest.mark.parametrize(
    ("credit_balance", "is_credits_unlimited"), ((None, False), (CREDIT_BALANCE, False), (None, True))
)
def test_should_wait_and_name_the_missing_plan_when_the_only_account_has_no_known_plan(
    credit_balance: float | None, is_credits_unlimited: bool
) -> None:
    reading = Reading(
        _account("unlabelled"),
        _meters(100, 100, plan_type=UNKNOWN_PLAN, credit_balance=credit_balance, is_credits_unlimited=is_credits_unlimited),
    )

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.action == "wait"
    assert decision.account is None
    assert decision.reason == (
        "no account has room (unlabelled reports no known plan and is never chosen); "
        "next check at 2026-10-03T01:00:00+00:00"
    )


def test_should_name_each_refusal_apart_when_a_free_account_and_an_account_with_no_plan_are_the_only_accounts() -> None:
    readings = (
        Reading(_account("editor"), _meters(100, 100, plan_type=FREE_PLAN)),
        Reading(_account("unlabelled"), _meters(100, 100, plan_type=None)),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.action == "wait"
    assert decision.reason == (
        "no account has room (editor is on a free plan and is never chosen, "
        "unlabelled reports no known plan and is never chosen); next check at 2026-10-03T01:00:00+00:00"
    )


def test_should_exit_three_for_check_when_the_only_account_has_no_known_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    account = _account("unlabelled")
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter((account,), {"unlabelled": _meters(100, 100, plan_type=UNKNOWN_PLAN)}),
    )

    assert account_broker.main(("check", "--product", "codex")) == WAIT_EXIT_CODE


def test_should_keep_the_unread_handling_for_an_account_whose_meters_could_not_be_read() -> None:
    readings = (
        Reading(_account("unread"), None, "codex app-server failed: timed out"),
        Reading(_account("unlabelled"), _meters(100, 100, plan_type=None)),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.action == "wait"
    assert decision.reason == (
        "no readable account has room (unlabelled reports no known plan and is never chosen); "
        "meter unreadable for unread (codex app-server failed: timed out); next check at 2026-10-03T01:00:00+00:00"
    )


UNRECOGNISED_PLANS = ("free_works", "free trial", "pro_trial", "teams", "freemium")
PAID_PLANS = ("pro", "prolite", "promax", "team", "plus", "business", "enterprise", "edu")


@pytest.mark.parametrize("plan_type", UNRECOGNISED_PLANS)
def test_should_never_choose_an_account_on_an_unrecognised_plan_even_when_it_has_the_most_room(plan_type: str) -> None:
    readings = (
        Reading(_account("unrecognised"), _meters(100, 100, plan_type=plan_type)),
        Reading(_account("team"), _meters(40, 5, plan_type=TEAM_PLAN)),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[1].account
    assert decision.tier == "luna"


@pytest.mark.parametrize("plan_type", UNRECOGNISED_PLANS)
@pytest.mark.parametrize(
    ("credit_balance", "is_credits_unlimited"), ((None, False), (CREDIT_BALANCE, False), (None, True))
)
def test_should_wait_and_name_the_missing_plan_when_the_only_account_is_on_an_unrecognised_plan(
    plan_type: str, credit_balance: float | None, is_credits_unlimited: bool
) -> None:
    reading = Reading(
        _account("unrecognised"),
        _meters(100, 100, plan_type=plan_type, credit_balance=credit_balance, is_credits_unlimited=is_credits_unlimited),
    )

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.action == "wait"
    assert decision.account is None
    assert decision.reason == (
        "no account has room (unrecognised reports no known plan and is never chosen); "
        "next check at 2026-10-03T01:00:00+00:00"
    )


@pytest.mark.parametrize("plan_type", UNRECOGNISED_PLANS)
def test_should_never_choose_an_account_on_an_unrecognised_plan_when_the_floor_switch_is_on(
    monkeypatch: pytest.MonkeyPatch, plan_type: str
) -> None:
    _disable_codex_weekly_floor(monkeypatch)
    reading = Reading(_account("unrecognised"), _meters(30, 0.5, plan_type=plan_type))

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.action == "wait"
    assert decision.account is None


@pytest.mark.parametrize("plan_type", UNRECOGNISED_PLANS)
def test_should_exit_three_for_check_when_the_only_account_is_on_an_unrecognised_plan(
    monkeypatch: pytest.MonkeyPatch, plan_type: str
) -> None:
    account = _account("unrecognised")
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter((account,), {"unrecognised": _meters(100, 100, plan_type=plan_type)}),
    )

    assert account_broker.main(("check", "--product", "codex")) == WAIT_EXIT_CODE


@pytest.mark.parametrize("plan_type", UNRECOGNISED_PLANS)
def test_should_not_run_a_job_on_an_account_on_an_unrecognised_plan(
    monkeypatch: pytest.MonkeyPatch, plan_type: str
) -> None:
    account = _account("unrecognised")
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter((account,), {"unrecognised": _meters(100, 100, plan_type=plan_type)}),
    )
    all_invoked_homes: list[str] = []

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        all_invoked_homes.append(Path(options["env"]["CODEX_HOME"]).name)
        return subprocess.CompletedProcess(argv, 0, "served", "")

    with account_broker.override_subprocess_runner(runner):
        outcome, _ = account_broker._execute(Product.CODEX, ("job",), now=NOW)

    assert all_invoked_homes == []
    assert outcome.status == "wait"
    assert outcome.returncode == WAIT_EXIT_CODE


@pytest.mark.parametrize("plan_type", PAID_PLANS)
def test_should_choose_an_account_on_every_listed_paid_plan(plan_type: str) -> None:
    reading = Reading(_account("paid"), _meters(100, 100, plan_type=plan_type))

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.action == "run"
    assert decision.account == reading.account
    assert decision.tier == "normal"


@pytest.mark.parametrize("plan_type", [each_plan.upper() for each_plan in PAID_PLANS] + [f" {PAID_PLANS[0]} "])
def test_should_choose_an_account_on_a_listed_paid_plan_whatever_its_case_or_padding(plan_type: str) -> None:
    reading = Reading(_account("paid"), _meters(100, 100, plan_type=plan_type))

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.action == "run"
    assert decision.account == reading.account


def test_should_still_choose_a_claude_account_whose_meters_carry_no_plan_type() -> None:
    readings = (Reading(_account("main", Product.CLAUDE), _meters(80, 80, plan_type=None)),)

    decision = choose_from_readings(Product.CLAUDE, readings, now=NOW)

    assert decision.action == "run"
    assert decision.account == readings[0].account
    assert decision.tier == "normal"


def test_should_keep_the_reset_time_of_a_claude_account_with_no_plan_type_when_it_has_no_room() -> None:
    reading = Reading(_account("main", Product.CLAUDE), _meters(0, 80, plan_type=None))

    decision = choose_from_readings(Product.CLAUDE, (reading,), now=NOW)

    assert decision.action == "wait"
    assert decision.resets_at == reading.meters.session_resets_at
    assert decision.reason == f"no account has room (main 0% left); next reset at {reading.meters.session_resets_at.isoformat()}"


def test_should_choose_a_team_account_with_credits_at_both_floors() -> None:
    reading = Reading(_account("team"), _meters(0, 0.5, plan_type=TEAM_PLAN, credit_balance=CREDIT_BALANCE))

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.action == "run"
    assert decision.account == reading.account


def test_should_exit_zero_for_check_on_an_account_with_credits_at_both_floors(monkeypatch: pytest.MonkeyPatch) -> None:
    account = _account("personal")
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter((account,), {"personal": _meters(0, 0.5, plan_type=PRO_PLAN, credit_balance=CREDIT_BALANCE)}),
    )

    assert account_broker.main(("check", "--product", "codex")) == 0


def test_should_wait_on_an_account_at_both_floors_with_a_zero_credit_balance() -> None:
    reading = Reading(_account("team"), _meters(0, 0.5, plan_type=TEAM_PLAN, credit_balance=0.0))

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.action == "wait"
    assert decision.resets_at == reading.meters.weekly_resets_at


def test_should_wait_for_the_session_reset_of_a_pro_account_at_zero_with_a_zero_credit_balance() -> None:
    reading = Reading(_account("personal"), _meters(0, 0.5, plan_type=PRO_PLAN, credit_balance=0.0))

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.action == "wait"
    assert decision.resets_at == reading.meters.session_resets_at


def test_should_choose_an_unlimited_credits_account_at_both_floors() -> None:
    reading = Reading(_account("personal"), _meters(0, 0.5, plan_type="pro", is_credits_unlimited=True))

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.action == "run"
    assert decision.account == reading.account


def test_should_prefer_a_pro_account_with_plan_usage_over_a_pro_account_with_only_credits() -> None:
    readings = (
        Reading(_account("credits-only"), _meters(None, 0.5, plan_type=PRO_PLAN, credit_balance=CREDIT_BALANCE)),
        Reading(_account("with-usage"), _meters(40, 30, plan_type="pro")),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[1].account
    assert decision.reason == "with-usage has 30% left"


def test_should_prefer_a_team_account_with_plan_usage_over_a_team_account_with_only_credits() -> None:
    readings = (
        Reading(_account("credits-only"), _meters(None, 0.5, plan_type=TEAM_PLAN, credit_balance=CREDIT_BALANCE)),
        Reading(_account("with-usage"), _meters(40, 30, plan_type=TEAM_PLAN)),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[1].account


def test_should_prefer_a_pro_account_with_only_credits_over_a_team_account_with_more_room() -> None:
    readings = (
        Reading(_account("team"), _meters(90, 85, plan_type=TEAM_PLAN)),
        Reading(_account("personal"), _meters(None, 0.5, plan_type="promax", credit_balance=CREDIT_BALANCE)),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[1].account


@pytest.mark.parametrize("weekly_left", (5, 9))
def test_should_choose_a_pro_account_below_the_normal_floor_over_a_team_account_with_more_room(weekly_left: float) -> None:
    readings = (
        Reading(_account("team"), _meters(None, 90, plan_type=TEAM_PLAN)),
        Reading(_account("personal"), _meters(None, weekly_left, plan_type="pro")),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[1].account
    assert decision.tier == "luna"


@pytest.mark.parametrize(("short_left", "weekly_left"), ((5, 80), (0.5, 80), (None, 1), (None, 0.5), (19, 1)))
def test_should_choose_a_pro_account_with_plan_usage_left_in_both_windows_over_a_team_account(
    short_left: float | None, weekly_left: float
) -> None:
    readings = (
        Reading(_account("team"), _meters(None, 90, plan_type=TEAM_PLAN)),
        Reading(_account("personal"), _meters(short_left, weekly_left, plan_type="pro")),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[1].account
    assert decision.tier == "luna"


@pytest.mark.parametrize(("short_left", "weekly_left"), ((0, 80), (80, 0), (0, 0), (None, 0)))
def test_should_skip_a_pro_account_with_a_window_at_zero_and_no_credits(
    short_left: float | None, weekly_left: float
) -> None:
    readings = (
        Reading(_account("team"), _meters(None, 90, plan_type=TEAM_PLAN)),
        Reading(_account("personal"), _meters(short_left, weekly_left, plan_type="pro")),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[0].account
    assert decision.tier == "normal"


def test_should_wait_for_the_reset_of_a_pro_account_at_zero_when_it_is_the_only_account() -> None:
    reading = Reading(_account("personal"), _meters(0, 80, plan_type="pro"))

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.action == "wait"
    assert decision.resets_at == reading.meters.session_resets_at


@pytest.mark.parametrize("weekly_left", (0, 1))
def test_should_choose_a_pro_account_with_credits_at_the_stop_floor_over_a_team_account(weekly_left: float) -> None:
    readings = (
        Reading(_account("team"), _meters(None, 90, plan_type=TEAM_PLAN)),
        Reading(_account("personal"), _meters(None, weekly_left, plan_type="pro", credit_balance=CREDIT_BALANCE)),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[1].account
    assert decision.tier == "normal"


def test_should_keep_plan_and_credits_through_the_meter_cache() -> None:
    account = _account("personal")
    all_reads: list[str] = []

    def read_meters(each_account: Account) -> Meters:
        all_reads.append(each_account.name)
        return _meters(None, 1, plan_type=PRO_PLAN, credit_balance=CREDIT_BALANCE)

    adapter = ProductAdapter(lambda: (account,), read_meters, "CODEX_HOME", ())
    state = account_broker._load_state(account_broker.broker_state_path())

    fresh = account_broker.read_accounts(Product.CODEX, adapter, all_state=state, now=NOW)
    cached = account_broker.read_accounts(Product.CODEX, adapter, all_state=state, now=NOW + timedelta(seconds=10))

    assert all_reads == ["personal"]
    assert cached[0].meters == fresh[0].meters
    assert cached[0].meters.has_spendable_credits is True
    assert cached[0].meters.plan_type == PRO_PLAN


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


def test_should_pick_main_when_its_5_hour_meter_is_null_and_its_week_has_room() -> None:
    main = Reading(
        _account("main", Product.CLAUDE, main=True),
        Meters(None, None, 96.0, NOW + timedelta(days=5)),
    )

    decision = choose_from_readings(Product.CLAUDE, (main,), now=NOW)

    assert decision.action == "run"
    assert decision.account == main.account
    assert decision.reason == "main has 96% left"


def test_should_wait_for_main_5_hour_reset_while_its_week_resets_days_away() -> None:
    short_reset = NOW + timedelta(hours=2)
    main = Reading(
        _account("main", Product.CLAUDE, main=True),
        _meters(5, 50, short_reset=short_reset, weekly_reset=NOW + timedelta(days=3)),
    )

    decision = choose_from_readings(Product.CLAUDE, (main,), now=NOW)

    assert decision.action == "wait"
    assert decision.resets_at == short_reset


def test_should_check_main_again_in_an_hour_when_a_blocking_window_has_no_reset() -> None:
    main = Reading(
        _account("main", Product.CLAUDE, main=True),
        Meters(5, None, 1, NOW + timedelta(hours=4)),
    )

    decision = choose_from_readings(Product.CLAUDE, (main,), now=NOW)

    assert decision.action == "wait"
    assert decision.resets_at == NOW + timedelta(hours=1)


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


def _disable_codex_weekly_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(codex_account_constants.CODEX_WEEKLY_FLOOR_DISABLED_ENVIRONMENT_VARIABLE, "1")


def test_should_wait_when_the_only_account_is_at_the_weekly_floor() -> None:
    reading = Reading(_account("credits"), _meters(30, 0.5))

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.action == "wait"
    assert decision.resets_at == reading.meters.weekly_resets_at


def test_should_choose_an_account_at_the_weekly_floor_when_the_floor_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_codex_weekly_floor(monkeypatch)
    reading = Reading(_account("credits"), _meters(30, 0.5))

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.action == "run"
    assert decision.account == reading.account
    assert decision.tier == "luna"


def test_should_prefer_an_account_with_room_over_one_at_the_weekly_floor_when_the_floor_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_codex_weekly_floor(monkeypatch)
    readings = (
        Reading(_account("credits"), _meters(30, 0.5)),
        Reading(_account("roomy"), _meters(30, 8)),
    )

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)

    assert decision.account == readings[1].account
    assert decision.tier == "luna"


def test_should_still_wait_on_a_spent_session_when_the_weekly_floor_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_codex_weekly_floor(monkeypatch)
    reading = Reading(_account("credits"), _meters(0, 0.5))

    decision = choose_from_readings(Product.CODEX, (reading,), now=NOW)

    assert decision.action == "wait"
    assert decision.resets_at == reading.meters.session_resets_at


def test_should_exit_zero_for_check_on_an_account_at_the_weekly_floor_when_the_floor_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_codex_weekly_floor(monkeypatch)
    account = _account("credits")
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter((account,), {"credits": _meters(30, 0.5)}),
    )

    assert account_broker.main(("check", "--product", "codex")) == 0


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
    assert payload["decision"]["profile"] is None
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
    reading = Reading(_account("one"), _meters(80, 70), measured_at=NOW)

    payload = account_broker.readings_payload((reading,))

    assert payload[0]["name"] == "one"
    assert payload[0]["meters"]["weekly_percent_left"] == 70
    assert payload[0]["measured_at"] == NOW.isoformat()


def test_should_wait_until_the_rate_limit_probe_after_stale_meters_expire() -> None:
    reading = Reading(
        _account("one", Product.CLAUDE), None,
        "usage probe failed: HTTP Error 429", NOW - timedelta(minutes=25),
        NOW + timedelta(minutes=5),
    )

    decision = choose_from_readings(Product.CLAUDE, (reading,), now=NOW)

    assert decision.action == "wait"
    assert decision.resets_at == NOW + timedelta(minutes=5)
    assert decision.reason == (
        "no account meter could be read (one (usage probe failed: HTTP Error 429)); "
        "next check at 2026-10-03T00:05:00+00:00"
    )


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
            "no readable account has room (main 5% left); meter unreadable for ev; next reset at 2026-10-03T00:30:00+00:00",
            NOW + timedelta(minutes=30),
            id="unreadable-beside-a-reset-before-the-check",
        ),
        pytest.param(
            (Reading(_MAIN_CLAUDE, _meters(5, 50, short_reset=NOW + timedelta(hours=2))), Reading(_EV_CLAUDE, None)),
            {},
            "no readable account has room (main 5% left); meter unreadable for ev; next check at 2026-10-03T01:00:00+00:00",
            NOW + timedelta(hours=1),
            id="unreadable-beside-a-reset-after-the-check",
        ),
        pytest.param(
            (Reading(_MAIN_CLAUDE, _meters(80, 80)), Reading(_EV_CLAUDE, None)),
            {_MAIN_CLAUDE: NOW + timedelta(minutes=30)},
            "no readable account has room (main spent); meter unreadable for ev; next reset at 2026-10-03T00:30:00+00:00",
            NOW + timedelta(minutes=30),
            id="unreadable-beside-a-spent-account",
        ),
        pytest.param(
            (
                Reading(_MAIN_CLAUDE, _meters(5, 50, short_reset=NOW + timedelta(hours=2))),
                Reading(_EV_CLAUDE, _meters(5, 80, short_reset=NOW + timedelta(hours=3))),
            ),
            {},
            "no account has room (main 5% left, ev 5% left); next reset at 2026-10-03T02:00:00+00:00",
            NOW + timedelta(hours=2),
            id="every-meter-read-with-known-resets",
        ),
        pytest.param(
            (Reading(_MAIN_CLAUDE, Meters(5, None, 50, None)),),
            {},
            "no account has room (main 5% left); next check at 2026-10-03T01:00:00+00:00",
            NOW + timedelta(hours=1),
            id="every-meter-read-without-a-known-reset",
        ),
        pytest.param(
            (),
            {},
            "no account has room; next check at 2026-10-03T01:00:00+00:00",
            NOW + timedelta(hours=1),
            id="no-account-in-the-roster",
        ),
        pytest.param(
            (Reading(_MAIN_CLAUDE, Meters(None, None, None, None)),),
            {},
            "no account has room (main percent left unread); next check at 2026-10-03T01:00:00+00:00",
            NOW + timedelta(hours=1),
            id="meter-read-without-a-percent",
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
        each_name: _meters(80, 80) for each_name in (*roster_names, "default")
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
        "accounts": [{"name": "listed", "profile": None, "home": str(account.home), "is_main": False}]
    }


def test_should_use_default_codex_home_without_roster(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("CODEX_ACCOUNT_PROFILES", raising=False)
    monkeypatch.setattr(account_broker.support.codex_account_choice, "default_profiles_root", lambda: tmp_path / "profiles")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "default"))

    assert account_broker.load_codex_accounts() == ()
    all_meters = {"default": _meters(40, 60, plan_type="pro")}
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((), all_meters))
    state = account_broker._load_state(account_broker.broker_state_path())

    readings = account_broker.read_accounts(Product.CODEX, all_state=state, now=NOW)

    decision = choose_from_readings(Product.CODEX, readings, now=NOW)
    assert decision.account.name == "default"
    assert decision.account.home == (tmp_path / "default").resolve()
    assert decision.reason == "default has 40% left"


def _use_default_home_without_roster(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, default_meters: Meters | Exception
) -> tuple[Path, list[str]]:
    home = tmp_path / "default-home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(account_broker_support.time, "sleep", lambda _: None)
    all_read_names: list[str] = []

    def read_meters(account: Account) -> Meters:
        all_read_names.append(account.name)
        if isinstance(default_meters, Exception):
            raise default_meters
        return default_meters

    adapter = ProductAdapter(lambda: (), read_meters, "CODEX_HOME", ("rate limit",))
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, adapter)
    _freeze_clock(monkeypatch, NOW)
    return home.resolve(), all_read_names


def test_should_read_the_meters_of_the_default_home_when_no_roster_is_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home, all_read_names = _use_default_home_without_roster(monkeypatch, tmp_path, _meters(40, 60, plan_type="pro"))

    code = account_broker.main(("choose", "--product", "codex"))

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert all_read_names == ["default"]
    assert payload["decision"]["account"] == "default"
    assert payload["decision"]["home"] == str(home)
    assert payload["decision"]["reason"] == "default has 40% left"
    assert payload["accounts"][0]["meters"]["plan_type"] == "pro"


@pytest.mark.parametrize("blank_home", ("", "   ", "\t"))
def test_should_choose_the_home_directory_default_when_codex_home_is_blank_and_no_roster_is_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], blank_home: str
) -> None:
    _use_default_home_without_roster(monkeypatch, tmp_path, _meters(40, 60, plan_type="pro"))
    monkeypatch.setenv("CODEX_HOME", blank_home)

    code = account_broker.main(("choose", "--product", "codex"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == 0
    assert decision["action"] == "run"
    assert decision["home"] == str((Path.home() / ".codex").resolve())


@pytest.mark.parametrize(
    ("plan_type", "refusal"),
    (
        ("free", "default is on a free plan and is never chosen"),
        (None, "default reports no known plan and is never chosen"),
        ("unknown", "default reports no known plan and is never chosen"),
        ("free_works", "default reports no known plan and is never chosen"),
    ),
)
def test_should_wait_when_the_default_home_is_free_or_has_no_known_plan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    plan_type: str | None,
    refusal: str,
) -> None:
    _use_default_home_without_roster(monkeypatch, tmp_path, _meters(100, 100, plan_type=plan_type))

    code = account_broker.main(("choose", "--product", "codex"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == WAIT_EXIT_CODE
    assert decision["action"] == "wait"
    assert decision["account"] is None
    assert decision["reason"] == f"no account has room ({refusal}); next check at 2026-10-03T01:00:00+00:00"


def test_should_wait_and_name_the_failed_read_when_the_default_home_meters_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_default_home_without_roster(monkeypatch, tmp_path, OSError("codex app-server failed: timed out"))

    code = account_broker.main(("choose", "--product", "codex"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == WAIT_EXIT_CODE
    assert decision["action"] == "wait"
    assert decision["reason"] == (
        "no account meter could be read (default (codex app-server failed: timed out)); "
        "next check at 2026-10-03T01:00:00+00:00"
    )


def test_should_wait_when_the_default_home_has_no_reading() -> None:
    decision = choose_from_readings(Product.CODEX, (), now=NOW)

    assert decision.action == "wait"
    assert decision.account is None


def test_should_not_start_a_job_on_a_free_default_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _use_default_home_without_roster(monkeypatch, tmp_path, _meters(100, 100, plan_type=FREE_PLAN))
    all_invoked_homes: list[str] = []

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        all_invoked_homes.append(options["env"]["CODEX_HOME"])
        return subprocess.CompletedProcess(argv, 0, "served", "")

    with account_broker.override_subprocess_runner(runner):
        outcome, _ = account_broker._execute(Product.CODEX, ("job",), now=NOW)

    assert all_invoked_homes == []
    assert outcome.status == "wait"
    assert outcome.returncode == WAIT_EXIT_CODE


@pytest.mark.parametrize("plan_type", UNRECOGNISED_PLANS)
def test_should_not_start_a_job_on_a_default_home_on_an_unrecognised_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, plan_type: str
) -> None:
    _use_default_home_without_roster(monkeypatch, tmp_path, _meters(100, 100, plan_type=plan_type))
    all_invoked_homes: list[str] = []

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        all_invoked_homes.append(options["env"]["CODEX_HOME"])
        return subprocess.CompletedProcess(argv, 0, "served", "")

    with account_broker.override_subprocess_runner(runner):
        outcome, _ = account_broker._execute(Product.CODEX, ("job",), now=NOW)

    assert all_invoked_homes == []
    assert outcome.status == "wait"
    assert outcome.returncode == WAIT_EXIT_CODE


def _use_roster_beside_an_outside_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outside_meters: Meters | Exception
) -> tuple[Path, list[str]]:
    outside_home = (tmp_path / "exported-home").resolve()
    roster = (_account("team"),)
    all_read_names: list[str] = []

    def read_meters(account: Account) -> Meters:
        all_read_names.append(account.name)
        if account.name == "team":
            return _meters(90, 90, plan_type=TEAM_PLAN)
        if isinstance(outside_meters, Exception):
            raise outside_meters
        return outside_meters

    monkeypatch.setattr(account_broker_support.time, "sleep", lambda _: None)
    monkeypatch.setitem(
        account_broker.all_product_adapters, Product.CODEX, ProductAdapter(lambda: roster, read_meters, "CODEX_HOME", ())
    )
    _freeze_clock(monkeypatch, NOW)
    return outside_home, all_read_names


def test_should_judge_only_the_named_home_when_choose_gets_a_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside_home, all_read_names = _use_roster_beside_an_outside_home(
        monkeypatch, tmp_path, _meters(None, 5, plan_type="pro")
    )

    code = account_broker.main(("choose", "--product", "codex", "--home", str(outside_home)))

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert all_read_names == ["exported-home"]
    assert payload["decision"]["action"] == "run"
    assert payload["decision"]["home"] == str(outside_home)
    assert payload["decision"]["tier"] == "luna"
    assert [each_entry["home"] for each_entry in payload["accounts"]] == [str(outside_home)]


@pytest.mark.parametrize(
    ("plan_type", "refusal"),
    (
        ("free", "exported-home is on a free plan and is never chosen"),
        (None, "exported-home reports no known plan and is never chosen"),
        ("unknown", "exported-home reports no known plan and is never chosen"),
        ("free_works", "exported-home reports no known plan and is never chosen"),
    ),
)
def test_should_wait_when_the_named_home_is_free_or_has_no_known_plan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    plan_type: str | None,
    refusal: str,
) -> None:
    outside_home, _ = _use_roster_beside_an_outside_home(monkeypatch, tmp_path, _meters(100, 100, plan_type=plan_type))

    code = account_broker.main(("choose", "--product", "codex", "--home", str(outside_home)))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == WAIT_EXIT_CODE
    assert decision["action"] == "wait"
    assert decision["reason"] == f"no account has room ({refusal}); next check at 2026-10-03T01:00:00+00:00"


def test_should_wait_when_the_meters_of_the_named_home_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside_home, _ = _use_roster_beside_an_outside_home(monkeypatch, tmp_path, OSError("codex app-server failed: timed out"))

    code = account_broker.main(("choose", "--product", "codex", "--home", str(outside_home)))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == WAIT_EXIT_CODE
    assert decision["reason"] == (
        "no account meter could be read (exported-home (codex app-server failed: timed out)); "
        "next check at 2026-10-03T01:00:00+00:00"
    )


def test_should_exit_three_for_check_when_the_named_home_is_free(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outside_home, _ = _use_roster_beside_an_outside_home(monkeypatch, tmp_path, _meters(100, 100, plan_type=FREE_PLAN))

    assert account_broker.main(("check", "--product", "codex", "--home", str(outside_home))) == WAIT_EXIT_CODE


@pytest.mark.parametrize("plan_type", UNRECOGNISED_PLANS)
def test_should_exit_three_for_check_when_the_named_home_is_on_an_unrecognised_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, plan_type: str
) -> None:
    outside_home, _ = _use_roster_beside_an_outside_home(monkeypatch, tmp_path, _meters(100, 100, plan_type=plan_type))

    assert account_broker.main(("check", "--product", "codex", "--home", str(outside_home))) == WAIT_EXIT_CODE


def test_should_not_let_the_floor_switch_or_credits_unlock_a_named_home_on_an_unrecognised_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _disable_codex_weekly_floor(monkeypatch)
    outside_home, _ = _use_roster_beside_an_outside_home(
        monkeypatch, tmp_path, _meters(30, 0.5, plan_type="free_works", credit_balance=CREDIT_BALANCE, is_credits_unlimited=True)
    )

    code = account_broker.main(("choose", "--product", "codex", "--home", str(outside_home)))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == WAIT_EXIT_CODE
    assert decision["action"] == "wait"
    assert decision["account"] is None


def test_should_run_a_named_team_home_at_half_a_percent_weekly_without_credits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside_home, _ = _use_roster_beside_an_outside_home(monkeypatch, tmp_path, _meters(80, 0.5, plan_type=TEAM_PLAN))

    code = account_broker.main(("choose", "--product", "codex", "--home", str(outside_home)))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == 0
    assert decision["action"] == "run"
    assert decision["home"] == str(outside_home)
    assert decision["tier"] == "luna"
    assert decision["reason"] == "exported-home is the named home and runs whatever room it has left"


def test_should_run_a_named_pro_home_with_no_session_room(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside_home, _ = _use_roster_beside_an_outside_home(monkeypatch, tmp_path, _meters(0, 70, plan_type="pro"))

    code = account_broker.main(("choose", "--product", "codex", "--home", str(outside_home)))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == 0
    assert decision["action"] == "run"
    assert decision["home"] == str(outside_home)
    assert decision["tier"] == "luna"


@pytest.mark.parametrize("is_floor_switch_on", (False, True))
def test_should_run_a_named_home_at_the_weekly_floor_whether_the_floor_switch_is_on_or_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], is_floor_switch_on: bool
) -> None:
    if is_floor_switch_on:
        _disable_codex_weekly_floor(monkeypatch)
    outside_home, _ = _use_roster_beside_an_outside_home(monkeypatch, tmp_path, _meters(80, 0.5, plan_type=TEAM_PLAN))

    code = account_broker.main(("choose", "--product", "codex", "--home", str(outside_home)))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == 0
    assert decision["action"] == "run"
    assert decision["tier"] == "luna"


@pytest.mark.parametrize(
    ("meters", "tier"),
    (
        (_meters(80, 50, plan_type=TEAM_PLAN), "normal"),
        (_meters(30, 8, plan_type=TEAM_PLAN), "luna"),
        (_meters(80, 0.5, plan_type=TEAM_PLAN, credit_balance=CREDIT_BALANCE), "normal"),
        (_meters(80, 0.5, plan_type=TEAM_PLAN), "luna"),
        (_meters(0, 0, plan_type="promax"), "luna"),
    ),
)
def test_should_name_the_tier_a_named_home_would_have_and_luna_when_none_fits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], meters: Meters, tier: str
) -> None:
    outside_home, _ = _use_roster_beside_an_outside_home(monkeypatch, tmp_path, meters)

    code = account_broker.main(("choose", "--product", "codex", "--home", str(outside_home)))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == 0
    assert decision["action"] == "run"
    assert decision["tier"] == tier


def test_should_exit_zero_for_check_when_the_named_home_is_at_half_a_percent_weekly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outside_home, _ = _use_roster_beside_an_outside_home(monkeypatch, tmp_path, _meters(80, 0.5, plan_type=TEAM_PLAN))

    assert account_broker.main(("check", "--product", "codex", "--home", str(outside_home))) == 0


def test_should_still_wait_on_a_roster_account_at_half_a_percent_weekly_when_no_home_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter((_account("team"),), {"team": _meters(80, 0.5, plan_type=TEAM_PLAN)}),
    )
    _freeze_clock(monkeypatch, NOW)

    code = account_broker.main(("choose", "--product", "codex"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == WAIT_EXIT_CODE
    assert decision["action"] == "wait"
    assert decision["account"] is None


def test_should_exit_three_for_check_on_a_roster_account_at_half_a_percent_weekly_when_no_home_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CODEX,
        _adapter((_account("team"),), {"team": _meters(80, 0.5, plan_type=TEAM_PLAN)}),
    )
    _freeze_clock(monkeypatch, NOW)

    assert account_broker.main(("check", "--product", "codex")) == WAIT_EXIT_CODE


def test_should_wait_when_a_named_home_below_normal_meets_a_normal_requirement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside_home, _ = _use_roster_beside_an_outside_home(monkeypatch, tmp_path, _meters(80, 0.5, plan_type=TEAM_PLAN))

    code = account_broker.main(("choose", "--product", "codex", "--home", str(outside_home), "--require-tier", "normal"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == WAIT_EXIT_CODE
    assert decision["action"] == "wait"


def test_should_wait_on_a_named_home_that_a_saved_spent_mark_still_covers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside_home, _ = _use_roster_beside_an_outside_home(monkeypatch, tmp_path, _meters(80, 80, plan_type="pro"))
    account_broker._save_state(
        account_broker.broker_state_path(),
        {
            "meters": {},
            "spent": {
                account_broker._state_key(Account(Product.CODEX, "exported-home", outside_home)): (NOW + timedelta(hours=3)).timestamp()
            },
            "affinity": {},
        },
    )

    code = account_broker.main(("choose", "--product", "codex", "--home", str(outside_home)))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == WAIT_EXIT_CODE
    assert decision["action"] == "wait"
    assert decision["account"] is None


def test_should_use_the_roster_account_when_the_named_home_is_a_roster_home(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    roster_account = _account("team")
    roster = (roster_account, _account("personal"))
    all_read_names: list[str] = []

    def read_meters(account: Account) -> Meters:
        all_read_names.append(account.name)
        return _meters(80, 80, plan_type=TEAM_PLAN)

    monkeypatch.setitem(
        account_broker.all_product_adapters, Product.CODEX, ProductAdapter(lambda: roster, read_meters, "CODEX_HOME", ())
    )

    code = account_broker.main(("choose", "--product", "codex", "--home", str(roster_account.home)))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == 0
    assert all_read_names == ["team"]
    assert decision["account"] == "team"


def test_should_not_let_a_spent_roster_account_stop_the_named_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside_home, _ = _use_roster_beside_an_outside_home(monkeypatch, tmp_path, _meters(80, 80, plan_type="pro"))
    account_broker._save_state(
        account_broker.broker_state_path(),
        {"meters": {}, "spent": {account_broker._state_key(_account("team")): (NOW + timedelta(hours=3)).timestamp()}, "affinity": {}},
    )

    code = account_broker.main(("choose", "--product", "codex", "--home", str(outside_home)))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == 0
    assert decision["action"] == "run"
    assert decision["tier"] == "normal"


def test_should_refuse_a_home_beside_spent_marks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside_home, all_read_names = _use_roster_beside_an_outside_home(monkeypatch, tmp_path, _meters(80, 80, plan_type="pro"))

    code = account_broker.main(("choose", "--product", "codex", "--home", str(outside_home), "--spent", "team"))

    assert code == 2
    assert all_read_names == []
    assert "--home cannot be used with --spent" in capsys.readouterr().err


def test_should_refuse_a_home_for_the_claude_product(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = account_broker.main(("choose", "--product", "claude", "--home", str(tmp_path)))

    assert code == 2
    assert "--home applies to the codex product only" in capsys.readouterr().err


def test_should_start_a_job_on_a_paid_default_home_with_its_home_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home, _ = _use_default_home_without_roster(monkeypatch, tmp_path, _meters(40, 60, plan_type="pro"))
    all_invoked_homes: list[str] = []

    def runner(argv: object, **options: object) -> subprocess.CompletedProcess[str]:
        all_invoked_homes.append(options["env"]["CODEX_HOME"])
        return subprocess.CompletedProcess(argv, 0, "served", "")

    with account_broker.override_subprocess_runner(runner):
        outcome, _ = account_broker._execute(Product.CODEX, ("job",), now=NOW)

    assert all_invoked_homes == [str(home)]
    assert outcome.status == "served"


def test_should_keep_the_codex_roster_for_a_process_without_the_roster_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(account_broker.support.codex_account_choice, "default_profiles_root", lambda: tmp_path / "profiles")
    monkeypatch.setenv("CODEX_ACCOUNT_PROFILES", "team,personal")
    assert [each_account.name for each_account in account_broker.load_codex_accounts()] == ["team", "personal"]

    monkeypatch.delenv("CODEX_ACCOUNT_PROFILES")

    assert [each_account.name for each_account in account_broker.load_codex_accounts()] == ["team", "personal"]


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
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((), {"default": _meters(80, 80)}))
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


def test_should_run_on_a_roster_account_while_a_no_roster_default_mark_is_live(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("personal")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"personal": _meters(99, 99)}))
    _freeze_clock(monkeypatch, NOW)
    no_roster_account = Account(Product.CODEX, "default", Path(), False)
    account_broker._save_state(
        account_broker.broker_state_path(),
        {"meters": {}, "spent": {account_broker._state_key(no_roster_account): (NOW + timedelta(hours=1)).timestamp()}, "affinity": {}},
    )

    code = account_broker.main(("choose", "--product", "codex"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == 0
    assert decision["action"] == "run"
    assert decision["account"] == "personal"


def test_should_not_save_a_default_spent_mark_while_a_roster_exists(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("personal")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"personal": _meters(99, 99)}))
    _freeze_clock(monkeypatch, NOW)

    code = account_broker.main(("choose", "--product", "codex", "--spent", "default"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == 0
    assert decision["account"] == "personal"
    assert account_broker._load_state(account_broker.broker_state_path())["spent"] == {}


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


def test_should_mark_an_account_spent_by_its_profile(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    launcher_name = "C:\\Users\\someone\\.local\\bin\\claude-first.cmd"
    first = Account(Product.CLAUDE, launcher_name, Path("/profiles/first"), command=launcher_name, profile="first")
    second = _account("second", Product.CLAUDE)
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CLAUDE,
        _adapter((first, second), {launcher_name: _meters(80, 80), "second": _meters(80, 80)}),
    )
    _freeze_clock(monkeypatch, NOW)

    code = account_broker.main(("choose", "--product", "claude", "--spent", f"first:{(NOW + timedelta(hours=2)).timestamp()}"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == 0
    assert decision["account"] == "second"


def test_should_mark_the_account_named_by_a_mark_that_is_also_another_profile(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    launcher_name = "C:\\Users\\someone\\.local\\bin\\claude-editor.cmd"
    profiled = Account(Product.CLAUDE, launcher_name, Path("/profiles/second"), command=launcher_name, profile="second")
    second = _account("second", Product.CLAUDE)
    monkeypatch.setitem(
        account_broker.all_product_adapters,
        Product.CLAUDE,
        _adapter((second, profiled), {launcher_name: _meters(80, 80), "second": _meters(90, 90)}),
    )
    _freeze_clock(monkeypatch, NOW)

    code = account_broker.main(("choose", "--product", "claude", "--spent", f"second:{(NOW + timedelta(hours=2)).timestamp()}"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert code == 0
    assert decision["account"] == launcher_name


def test_should_save_no_spent_mark_when_a_later_mark_is_unreadable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("first")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"first": _meters(80, 80)}))

    code = account_broker.main(("choose", "--product", "codex", "--spent", "first", "--spent", "guest:tomorrow"))

    assert code == 2
    assert "invalid reset" in capsys.readouterr().err
    assert account_broker._load_state(account_broker.broker_state_path()).get("spent", {}) == {}


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


def test_should_wait_on_an_outside_spent_mark_under_another_state_key_layout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("first")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"first": _meters(80, 80)}))
    monkeypatch.setattr(account_broker, "_state_key", lambda marked: f"{marked.product.value}|{marked.name}|{marked.home}")
    _freeze_clock(monkeypatch, NOW)
    reset = NOW + timedelta(hours=2)

    account_broker.main(("choose", "--product", "codex", "--spent", f"visitor:{int(reset.timestamp())}"))

    decision = json.loads(capsys.readouterr().out)["decision"]
    assert decision["action"] == "wait"
    assert "account visitor outside the roster is spent" in decision["reason"]


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
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((), {"default": _meters(80, 80)}))
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
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter(all_accounts, {each_name: _meters(80, 80) for each_name in (*all_roster_names, "default")}))
    _freeze_clock(monkeypatch, NOW)
    reset = NOW + timedelta(hours=2)

    account_broker.main(("choose", "--product", "codex", "--spent", f"{marked_name}:{int(reset.timestamp())}"))

    all_warning_lines = capsys.readouterr().err.splitlines()
    assert len(all_warning_lines) == 1
    assert marked_name in all_warning_lines[0]
    assert "outside the roster" in all_warning_lines[0]


def test_should_print_no_outside_roster_warning_when_a_later_mark_is_unreadable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("first")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"first": _meters(80, 80)}))

    code = account_broker.main(("choose", "--product", "codex", "--spent", "visitor", "--spent", "first:notanumber"))

    all_error_lines = capsys.readouterr().err.splitlines()
    assert code == 2
    assert len(all_error_lines) == 1
    assert "invalid reset in spent mark 'first:notanumber'" in all_error_lines[0]
    assert account_broker._load_state(account_broker.broker_state_path())["spent"] == {}


def test_should_save_an_outside_launcher_path_given_with_an_explicit_reset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = _account("first")
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter((account,), {"first": _meters(80, 80)}))
    reset = int((datetime.now(timezone.utc) + timedelta(hours=2)).timestamp())

    code = account_broker.main(("choose", "--product", "codex", "--spent", f"C:\\bin\\old.cmd:{reset}"))

    all_warning_lines = capsys.readouterr().err.splitlines()
    all_saved_marks = account_broker._load_state(account_broker.broker_state_path())["spent"]
    assert code == WAIT_EXIT_CODE
    assert "C:\\bin\\old.cmd" in all_warning_lines[0]
    assert all_saved_marks == {f"codex:C:\\bin\\old.cmd:{Path()}": float(reset)}


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

    assert run_payload == {"action": "run", "account": "first", "profile": None, "home": str(Path("/profiles/first")), "reason": "first has 80% left", "tier": "normal", "resets_at": None}
    assert wait_payload == {"action": "wait", "account": None, "profile": None, "home": None, "reason": "no account has room", "tier": "wait", "resets_at": reset.isoformat()}


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


def test_decision_payload_should_carry_the_profile_of_a_claude_account() -> None:
    account = Account(Product.CLAUDE, "C:\\bin\\claude-editor.cmd", Path("/profiles/editor"), command="C:\\bin\\claude-editor.cmd", profile="editor")

    assert account_broker.decision_payload(account_broker.Decision("run", account, None, "most room", "normal"))["profile"] == "editor"


def test_decision_payload_should_name_the_chosen_account_and_its_home() -> None:
    account = _account("codex-2")
    decision = account_broker.Decision("run", account, None, "most room", "normal")

    assert account_broker.decision_payload(decision) == {
        "action": "run",
        "account": "codex-2",
        "profile": None,
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


def test_should_save_every_spent_mark_in_one_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accounts = (_account("first"), _account("second"))
    monkeypatch.setitem(account_broker.all_product_adapters, Product.CODEX, _adapter(accounts, {
        "first": _meters(80, 80), "second": _meters(70, 70)
    }))
    all_saved_marks: list[dict[str, object]] = []

    def save_or_fail(path: Path, all_state: dict[str, object]) -> None:
        all_saved_marks.append(dict(all_state["spent"]))
        raise OSError("disk full")

    monkeypatch.setattr(account_broker, "_save_state", save_or_fail)

    with pytest.raises(OSError):
        account_broker.main(("choose", "--product", "codex", "--spent", "first", "--spent", "second"))

    assert len(all_saved_marks) == 1
    assert len(all_saved_marks[0]) == 2


def _claude_adapter(accounts: tuple[Account, ...], read_meters: Callable[[Account], Meters | None]) -> ProductAdapter:
    return ProductAdapter(
        load_accounts=lambda: accounts,
        read_meters=read_meters,
        environment_variable="CLAUDE_CONFIG_DIR",
        usage_limit_signatures=("rate limit",),
    )


def _execute_claude(
    monkeypatch: pytest.MonkeyPatch,
    accounts: tuple[Account, ...],
    read_meters: Callable[[Account], Meters | None],
    completions_by_name: dict[str, tuple[int, str, str]],
    attempted: list[str],
) -> tuple[account_broker.JobOutcome, account_broker.Report]:
    def runner(command: object, **options: object) -> subprocess.CompletedProcess[str]:
        selected = Path(options["env"]["CLAUDE_CONFIG_DIR"]).name
        attempted.append(selected)
        returncode, stdout, stderr = completions_by_name[selected]
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    monkeypatch.setitem(account_broker.all_product_adapters, Product.CLAUDE, _claude_adapter(accounts, read_meters))
    with account_broker.override_subprocess_runner(runner):
        return account_broker._execute(Product.CLAUDE, ("job",), now=NOW)


def test_should_skip_an_account_whose_sign_in_fails_and_run_the_next_account(monkeypatch: pytest.MonkeyPatch) -> None:
    accounts = (_account("first", Product.CLAUDE), _account("second", Product.CLAUDE))
    meters_by_name = {"first": _meters(90, 90), "second": _meters(70, 70)}
    attempted: list[str] = []

    outcome, report = _execute_claude(
        monkeypatch,
        accounts,
        lambda account: meters_by_name[account.name],
        {"first": (1, "", "Stored token expired"), "second": (0, "served", "")},
        attempted,
    )

    assert outcome.returncode == 0
    assert attempted == ["first", "second"]
    assert "skipped first: Stored token expired" in outcome.stderr
    assert any(
        each_event.get("type") == "sign_in_failure" and each_event.get("account") == "first"
        for each_event in report.events
    )


def test_should_exit_four_and_name_each_account_when_every_sign_in_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    accounts = (_account("first", Product.CLAUDE), _account("second", Product.CLAUDE))
    meters_by_name = {"first": _meters(90, 90), "second": _meters(70, 70)}
    attempted: list[str] = []

    outcome, _ = _execute_claude(
        monkeypatch,
        accounts,
        lambda account: meters_by_name[account.name],
        {
            "first": (1, "", "Organization has status: canceled"),
            "second": (1, "", "Stored token expired"),
        },
        attempted,
    )

    assert outcome.returncode == 4
    assert outcome.status == "no_usable_account"
    assert attempted == ["first", "second"]
    assert "first: Organization has status: canceled" in outcome.stderr
    assert "second: Stored token expired" in outcome.stderr


def test_should_exit_four_when_a_signed_out_account_and_a_failed_sign_in_leave_no_usable_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accounts = (_account("first", Product.CLAUDE), _account("second", Product.CLAUDE))
    signed_out_path = Path("/profiles/second/.credentials.json")
    attempted: list[str] = []

    def read_meters(account: Account) -> Meters | None:
        if account.name == "second":
            raise account_broker_support.ClaudeSignedOutError(
                NO_ACCESS_TOKEN_ERROR_TEMPLATE.format(credentials_path=signed_out_path)
            )
        return _meters(90, 90)

    outcome, _ = _execute_claude(
        monkeypatch,
        accounts,
        read_meters,
        {"first": (1, "", "stored token expired")},
        attempted,
    )

    assert outcome.returncode == 4
    assert attempted == ["first"]
    assert "second: " + NO_ACCESS_TOKEN_ERROR_TEMPLATE.format(credentials_path=signed_out_path) in outcome.stderr


def test_should_wait_with_exit_three_when_a_failed_sign_in_leaves_a_usage_limited_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accounts = (_account("first", Product.CLAUDE), _account("second", Product.CLAUDE))
    meters_by_name = {"first": _meters(90, 90), "second": _meters(70, 70)}
    attempted: list[str] = []

    outcome, _ = _execute_claude(
        monkeypatch,
        accounts,
        lambda account: meters_by_name[account.name],
        {"first": (1, "", "Stored token expired"), "second": (1, "", "rate limit")},
        attempted,
    )

    assert outcome.returncode == WAIT_EXIT_CODE
    assert attempted == ["first", "second"]


def test_should_not_skip_an_account_when_only_stdout_quotes_a_sign_in_message(monkeypatch: pytest.MonkeyPatch) -> None:
    accounts = (_account("first", Product.CLAUDE), _account("second", Product.CLAUDE))
    meters_by_name = {"first": _meters(90, 90), "second": _meters(70, 70)}
    attempted: list[str] = []

    outcome, _ = _execute_claude(
        monkeypatch,
        accounts,
        lambda account: meters_by_name[account.name],
        {"first": (1, "stored token expired", ""), "second": (0, "served", "")},
        attempted,
    )

    assert outcome.returncode == 1
    assert attempted == ["first"]


def test_should_stop_on_a_failure_that_is_not_a_sign_in(monkeypatch: pytest.MonkeyPatch) -> None:
    accounts = (_account("first", Product.CLAUDE), _account("second", Product.CLAUDE))
    meters_by_name = {"first": _meters(90, 90), "second": _meters(70, 70)}
    attempted: list[str] = []

    outcome, _ = _execute_claude(
        monkeypatch,
        accounts,
        lambda account: meters_by_name[account.name],
        {"first": (1, "", "boom"), "second": (0, "served", "")},
        attempted,
    )

    assert outcome.returncode == 1
    assert attempted == ["first"]
