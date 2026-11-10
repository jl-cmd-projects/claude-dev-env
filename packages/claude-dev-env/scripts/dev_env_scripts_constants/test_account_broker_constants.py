"""Floors, outcome shape, and time helpers for the account broker."""

from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import shutil
import sys
import types
from datetime import datetime, timedelta, timezone
from collections.abc import Callable
from pathlib import Path

import pytest

import codex_plan_rules
from dev_env_scripts_constants import account_broker_constants as broker_constants
from dev_env_scripts_constants import claude_account_constants, codex_account_constants, shared_tree_constants
from dev_env_scripts_constants.account_broker_constants import (
    ALL_ACCOUNT_ENVIRONMENT_VARIABLES,
    ALL_BATCH_FILE_EXTENSIONS,
    ALL_CLAUDE_FLOORS,
    ALL_CODEX_FLOORS,
    ALL_PARENT_CLAUDE_SESSION_VARIABLES,
    CMD_SHELL_METACHARACTERS,
    Account,
    JobOutcome,
    Product,
)
from dev_env_scripts_constants.claude_account_constants import (
    MAIN_SESSION_USED_CEILING_PERCENT,
    MAIN_WEEKLY_USED_CEILING_PERCENT,
    SECOND_SESSION_USED_CEILING_PERCENT,
    SECOND_WEEKLY_USED_CEILING_PERCENT,
)
from dev_env_scripts_constants.codex_account_constants import (
    LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT,
    LUNA_TIER_STOP_PERCENT_LEFT,
    NORMAL_TIER_MINIMUM_PERCENT_LEFT,
)

TEMP_TREE_MARKER = "marker-only-in-the-temp-install-tree"
FLOOR_TEST_PLAN_TYPE = "team"


def test_should_keep_claude_floors_tied_to_the_account_ceilings() -> None:
    assert ALL_CLAUDE_FLOORS == {
        "main_weekly_used_ceiling": MAIN_WEEKLY_USED_CEILING_PERCENT,
        "main_session_used_ceiling": MAIN_SESSION_USED_CEILING_PERCENT,
        "extra_weekly_used_ceiling": SECOND_WEEKLY_USED_CEILING_PERCENT,
        "extra_session_used_ceiling": SECOND_SESSION_USED_CEILING_PERCENT,
    }


def test_should_keep_codex_floors_tied_to_the_tier_limits() -> None:
    assert ALL_CODEX_FLOORS == {
        "normal_minimum_left": NORMAL_TIER_MINIMUM_PERCENT_LEFT,
        "luna_stop_left": LUNA_TIER_STOP_PERCENT_LEFT,
        "luna_short_minimum_left": LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT,
    }


def test_should_list_every_account_environment_variable() -> None:
    all_declared_variables = {
        each_value
        for each_module in (claude_account_constants, codex_account_constants, shared_tree_constants)
        for each_name, each_value in vars(each_module).items()
        if each_name.endswith(("_ENVIRONMENT_VARIABLE", "_ENV_VAR"))
    }
    assert all_declared_variables == set(ALL_ACCOUNT_ENVIRONMENT_VARIABLES)


def test_batch_command_boundaries_include_shell_metacharacters() -> None:
    assert ALL_BATCH_FILE_EXTENSIONS == frozenset({".bat", ".cmd"})
    assert set(CMD_SHELL_METACHARACTERS) == set('&|<>^%!"\r\n')


def test_should_freeze_job_outcome() -> None:
    outcome = JobOutcome(0, "", "", None, (), "served", None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.status = "wait"


def test_codex_usage_limit_signatures_loads_classifier_markers() -> None:
    signatures = broker_constants.codex_usage_limit_signatures()

    assert "rate limit" in signatures
    assert "http 429" in signatures


def test_codex_usage_limit_signatures_raises_import_error_when_markers_are_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(broker_constants, "__file__", str(tmp_path / "scripts" / "constants" / "module.py"))

    with pytest.raises(ImportError, match="cannot load usage markers from") as raised:
        broker_constants.codex_usage_limit_signatures()

    assert str(tmp_path) in str(raised.value)
    assert isinstance(raised.value.__cause__, FileNotFoundError)


def test_utc_time_text_converts_an_offset_timestamp() -> None:
    moment = datetime(2026, 10, 3, 7, 30, tzinfo=timezone(timedelta(hours=-4)))

    assert broker_constants.utc_time_text(moment) == "2026-10-03T11:30:00+00:00"
    assert broker_constants.utc_time_text(None) is None


@pytest.mark.parametrize("timestamp", (None, 123, "not a timestamp", "2026-10-03T11:30:00"))
def test_parse_utc_time_rejects_values_without_a_timezone(timestamp: object) -> None:
    assert broker_constants.parse_utc_time(timestamp) is None


def test_tightest_percent_left_should_take_the_lower_known_window() -> None:
    reset = datetime(2026, 10, 3, tzinfo=timezone.utc)

    assert broker_constants.Meters(30.0, reset, 70.0, reset).tightest_percent_left == 30.0
    assert broker_constants.Meters(80.0, reset, 20.0, reset).tightest_percent_left == 20.0
    assert broker_constants.Meters(None, None, 45.0, reset).tightest_percent_left == 45.0
    assert broker_constants.Meters(None, None, None, None).tightest_percent_left is None


def test_parse_utc_time_converts_an_offset_timestamp() -> None:
    parsed = broker_constants.parse_utc_time("2026-10-03T07:30:00-04:00")

    assert parsed is not None
    assert parsed.isoformat() == "2026-10-03T11:30:00+00:00"


def _build_install_layout(
    home: Path, create_directory_link: Callable[..., None]
) -> tuple[Path, Path]:
    agents_constants_directory = (
        home / ".agents" / "scripts" / "dev_env_scripts_constants"
    )
    agents_constants_directory.mkdir(parents=True)
    shutil.copy(
        Path(broker_constants.__file__),
        agents_constants_directory / "account_broker_constants.py",
    )
    classifier_directory = (
        home
        / ".claude"
        / "_shared"
        / "pr-loop"
        / "scripts"
        / "codex_review_scripts_constants"
    )
    classifier_directory.mkdir(parents=True)
    (classifier_directory / "classifier_constants.py").write_text(
        f"ALL_USAGE_LIMIT_MARKERS = ({TEMP_TREE_MARKER!r},)\n", encoding="utf-8"
    )
    create_directory_link(
        from_link=home / ".claude" / "scripts", to_target=home / ".agents" / "scripts"
    )
    linked_module = (
        home
        / ".claude"
        / "scripts"
        / "dev_env_scripts_constants"
        / "account_broker_constants.py"
    )
    agents_module = agents_constants_directory / "account_broker_constants.py"
    return linked_module, agents_module


def _load_module_from(
    module_file: Path, module_name: str, monkeypatch: pytest.MonkeyPatch
) -> types.ModuleType:
    specification = importlib.util.spec_from_file_location(module_name, module_file)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    monkeypatch.setitem(sys.modules, module_name, module)
    specification.loader.exec_module(module)
    return module


@pytest.mark.parametrize("entry_point", ("through_scripts_link", "through_agents_path"))
def test_codex_usage_limit_signatures_finds_shared_tree_beside_the_scripts_link(
    entry_point: str, tmp_path: Path, create_directory_link: Callable[..., None], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    linked_module, agents_module = _build_install_layout(tmp_path / "home", create_directory_link)
    module_file = (
        linked_module if entry_point == "through_scripts_link" else agents_module
    )
    installed_constants = _load_module_from(
        module_file, f"installed_account_broker_constants_{entry_point}", monkeypatch
    )

    assert installed_constants.codex_usage_limit_signatures() == (TEMP_TREE_MARKER,)


def test_parent_session_variables_name_the_session_link_and_leave_the_account_home() -> None:
    assert "CLAUDE_CODE_SESSION_ID" in ALL_PARENT_CLAUDE_SESSION_VARIABLES
    assert "CLAUDECODE" in ALL_PARENT_CLAUDE_SESSION_VARIABLES
    assert "CLAUDE_CONFIG_DIR" not in ALL_PARENT_CLAUDE_SESSION_VARIABLES


def test_should_treat_accounts_that_differ_only_in_profile_as_one_account() -> None:
    home = Path("/profiles/first")

    assert Account(Product.CLAUDE, "first", home, profile="first") == Account(Product.CLAUDE, "first", home)


def test_should_wait_until_a_rate_limited_meter_may_be_probed_again() -> None:
    now = datetime(2026, 10, 11, 19, 31, tzinfo=timezone.utc)
    probe_again_at = now + timedelta(minutes=5)
    account = Account(Product.CLAUDE, "second", Path("second"))
    reading = broker_constants.Reading(account, None, "usage probe failed: HTTP Error 429", None, probe_again_at)

    decision = broker_constants._wait_decision([reading], now, frozenset(), {})

    assert decision.resets_at == probe_again_at
    assert decision.reason == (
        "no account meter could be read (second (usage probe failed: HTTP Error 429)); "
        "next check at 2026-10-11T19:36:00+00:00"
    )


def _codex_reading(meters: broker_constants.Meters) -> broker_constants.Reading:
    return broker_constants.Reading(Account(Product.CODEX, "codex-1", Path("/profiles/codex-1")), meters)


def test_should_let_a_codex_account_at_the_short_window_floor_take_luna() -> None:
    weekly_reset = datetime(2026, 10, 4, tzinfo=timezone.utc)
    session_reset = weekly_reset + timedelta(hours=4)
    meters = broker_constants.Meters(
        LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT,
        session_reset,
        LUNA_TIER_STOP_PERCENT_LEFT / 2,
        weekly_reset,
        FLOOR_TEST_PLAN_TYPE,
    )

    assert codex_plan_rules.codex_tier(
        dataclasses.replace(meters, weekly_percent_left=NORMAL_TIER_MINIMUM_PERCENT_LEFT)
    ) == "luna"
    assert broker_constants._account_reset(_codex_reading(meters)) == weekly_reset


def test_should_name_no_codex_reset_when_a_blocking_window_has_none() -> None:
    session_reset = datetime(2026, 10, 3, 2, tzinfo=timezone.utc)
    meters = broker_constants.Meters(
        LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT / 2, session_reset, LUNA_TIER_STOP_PERCENT_LEFT / 2, None
    )

    assert broker_constants._account_reset(_codex_reading(meters)) is None


def test_should_name_the_latest_codex_reset_when_every_blocking_window_has_one() -> None:
    session_reset = datetime(2026, 10, 3, 2, tzinfo=timezone.utc)
    weekly_reset = datetime(2026, 10, 4, tzinfo=timezone.utc)
    meters = broker_constants.Meters(
        LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT / 2, session_reset, LUNA_TIER_STOP_PERCENT_LEFT / 2, weekly_reset
    )

    assert broker_constants._account_reset(_codex_reading(meters)) == weekly_reset


WEEKLY_FLOOR_SESSION_RESET = datetime(2026, 10, 3, 2, tzinfo=timezone.utc)
WEEKLY_FLOOR_WEEKLY_RESET = datetime(2026, 10, 4, tzinfo=timezone.utc)
ROOMY_SESSION_PERCENT_LEFT = LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT * 2


def _weekly_floor_meters(session_percent_left: float | None) -> broker_constants.Meters:
    return broker_constants.Meters(
        session_percent_left,
        WEEKLY_FLOOR_SESSION_RESET if session_percent_left is not None else None,
        LUNA_TIER_STOP_PERCENT_LEFT / 2,
        WEEKLY_FLOOR_WEEKLY_RESET,
        FLOOR_TEST_PLAN_TYPE,
    )


def _disable_codex_weekly_floor(monkeypatch: pytest.MonkeyPatch, setting: str = "1") -> None:
    monkeypatch.setenv(codex_account_constants.CODEX_WEEKLY_FLOOR_DISABLED_ENVIRONMENT_VARIABLE, setting)


def test_should_block_a_codex_account_at_the_weekly_floor_by_default() -> None:
    meters = _weekly_floor_meters(ROOMY_SESSION_PERCENT_LEFT)

    assert codex_plan_rules.codex_tier(meters) is None
    assert broker_constants._account_reset(_codex_reading(meters)) == WEEKLY_FLOOR_WEEKLY_RESET


def test_should_let_a_codex_account_at_the_weekly_floor_take_luna_when_the_floor_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_codex_weekly_floor(monkeypatch)
    meters = _weekly_floor_meters(ROOMY_SESSION_PERCENT_LEFT)

    assert codex_plan_rules.codex_tier(meters) == "luna"
    assert broker_constants._account_reset(_codex_reading(meters)) is None


def test_should_let_a_codex_account_with_only_a_weekly_window_take_luna_when_the_floor_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_codex_weekly_floor(monkeypatch)
    meters = _weekly_floor_meters(None)

    assert codex_plan_rules.codex_tier(meters) == "luna"
    assert broker_constants._account_reset(_codex_reading(meters)) is None


def test_should_keep_the_session_floor_when_the_weekly_floor_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_codex_weekly_floor(monkeypatch)
    meters = _weekly_floor_meters(LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT / 2)

    assert codex_plan_rules.codex_tier(meters) is None
    assert broker_constants._account_reset(_codex_reading(meters)) == WEEKLY_FLOOR_SESSION_RESET


@pytest.mark.parametrize("setting", ("1", "true", "TRUE", " yes ", "on"))
def test_should_disable_the_codex_weekly_floor_for_every_truthy_setting(
    monkeypatch: pytest.MonkeyPatch, setting: str
) -> None:
    _disable_codex_weekly_floor(monkeypatch, setting)

    assert codex_plan_rules.codex_tier(_weekly_floor_meters(ROOMY_SESSION_PERCENT_LEFT)) == "luna"


@pytest.mark.parametrize("setting", ("", "0", "false", "off", "no", "disabled"))
def test_should_keep_the_codex_weekly_floor_for_every_other_setting(
    monkeypatch: pytest.MonkeyPatch, setting: str
) -> None:
    _disable_codex_weekly_floor(monkeypatch, setting)

    assert codex_plan_rules.codex_tier(_weekly_floor_meters(ROOMY_SESSION_PERCENT_LEFT)) is None


CREDIT_BALANCE = 12.5
PRO_PLAN_TYPE = "prolite"
FREE_PLAN_TYPE = "free"
TEAM_PLAN_TYPE = "team"
UNKNOWN_PLAN_TYPE = "unknown"
WAIT_NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def _credit_meters(
    session_percent_left: float | None,
    *,
    plan_type: str | None = PRO_PLAN_TYPE,
    weekly_percent_left: float = LUNA_TIER_STOP_PERCENT_LEFT / 2,
    has_credits: bool = True,
    is_credits_unlimited: bool = False,
    credit_balance: float | None = CREDIT_BALANCE,
) -> broker_constants.Meters:
    return dataclasses.replace(
        _weekly_floor_meters(session_percent_left),
        weekly_percent_left=weekly_percent_left,
        plan_type=plan_type,
        has_credits=has_credits,
        is_credits_unlimited=is_credits_unlimited,
        credit_balance=credit_balance,
    )


@pytest.mark.parametrize(
    ("has_credits", "is_unlimited", "balance", "is_spendable"),
    (
        (True, False, CREDIT_BALANCE, True),
        (True, False, 0.0, False),
        (True, False, -1.0, False),
        (True, False, None, False),
        (False, False, CREDIT_BALANCE, False),
        (False, False, None, False),
        (False, True, None, True),
        (True, True, 0.0, True),
    ),
)
def test_should_count_credits_as_spendable_only_with_a_balance_or_unlimited_use(
    has_credits: bool, is_unlimited: bool, balance: float | None, is_spendable: bool
) -> None:
    meters = _credit_meters(None, has_credits=has_credits, is_credits_unlimited=is_unlimited, credit_balance=balance)

    assert meters.has_spendable_credits is is_spendable


def test_should_report_no_credits_for_meters_built_without_them() -> None:
    meters = broker_constants.Meters(80.0, None, 70.0, None, PRO_PLAN_TYPE)

    assert meters.has_credits is False
    assert meters.is_credits_unlimited is False
    assert meters.credit_balance is None
    assert meters.has_spendable_credits is False


@pytest.mark.parametrize(
    "session_percent_left", (ROOMY_SESSION_PERCENT_LEFT, LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT / 2, 0.0, None)
)
def test_should_let_a_codex_account_with_credits_run_under_both_floors(session_percent_left: float | None) -> None:
    meters = _credit_meters(session_percent_left)

    assert codex_plan_rules.codex_tier(meters) == codex_account_constants.TIER_NORMAL
    assert broker_constants._account_reset(_codex_reading(meters)) is None


def test_should_let_a_codex_account_with_unlimited_credits_run_under_both_floors() -> None:
    meters = _credit_meters(0.0, has_credits=False, is_credits_unlimited=True, credit_balance=None)

    assert codex_plan_rules.codex_tier(meters) == codex_account_constants.TIER_NORMAL
    assert broker_constants._account_reset(_codex_reading(meters)) is None


def test_should_let_a_team_account_with_credits_run_under_both_floors() -> None:
    meters = _credit_meters(0.0, plan_type=TEAM_PLAN_TYPE)

    assert codex_plan_rules.codex_tier(meters) == codex_account_constants.TIER_NORMAL


def test_should_keep_both_floors_for_a_non_pro_codex_account_with_a_zero_credit_balance() -> None:
    meters = _credit_meters(ROOMY_SESSION_PERCENT_LEFT, plan_type=TEAM_PLAN_TYPE, credit_balance=0.0)

    assert codex_plan_rules.codex_tier(meters) is None
    assert broker_constants._account_reset(_codex_reading(meters)) == WEEKLY_FLOOR_WEEKLY_RESET


def test_should_let_a_pro_codex_account_with_a_zero_credit_balance_and_plan_room_take_luna() -> None:
    meters = _credit_meters(ROOMY_SESSION_PERCENT_LEFT, credit_balance=0.0)

    assert codex_plan_rules.codex_tier(meters) == codex_account_constants.TIER_LUNA
    assert broker_constants._account_reset(_codex_reading(meters)) is None


@pytest.mark.parametrize("plan_type", (FREE_PLAN_TYPE, "Free", " FREE "))
def test_should_never_give_a_free_codex_account_a_tier(plan_type: str) -> None:
    roomy_meters = _credit_meters(
        ROOMY_SESSION_PERCENT_LEFT, plan_type=plan_type, weekly_percent_left=codex_account_constants.FULL_PERCENT, has_credits=False, credit_balance=None
    )

    assert codex_plan_rules.codex_tier(roomy_meters) is None
    assert codex_plan_rules.codex_tier(dataclasses.replace(roomy_meters, has_credits=True, credit_balance=CREDIT_BALANCE)) is None
    assert codex_plan_rules.codex_tier(dataclasses.replace(roomy_meters, is_credits_unlimited=True)) is None


def test_should_never_give_a_free_codex_account_a_tier_whatever_the_floors(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_codex_weekly_floor(monkeypatch)
    meters = _credit_meters(ROOMY_SESSION_PERCENT_LEFT, plan_type=FREE_PLAN_TYPE, has_credits=False, credit_balance=None)

    assert codex_plan_rules.codex_tier(meters) is None


@pytest.mark.parametrize("plan_type", (None, "unknown", "Unknown", " UNKNOWN ", ""))
def test_should_never_give_a_codex_account_with_no_known_plan_a_tier(plan_type: str | None) -> None:
    roomy_meters = _credit_meters(
        ROOMY_SESSION_PERCENT_LEFT, plan_type=plan_type, weekly_percent_left=codex_account_constants.FULL_PERCENT, has_credits=False, credit_balance=None
    )

    assert codex_plan_rules.codex_tier(roomy_meters) is None
    assert codex_plan_rules.codex_tier(dataclasses.replace(roomy_meters, has_credits=True, credit_balance=CREDIT_BALANCE)) is None
    assert codex_plan_rules.codex_tier(dataclasses.replace(roomy_meters, is_credits_unlimited=True)) is None


def test_should_never_give_a_codex_account_with_no_known_plan_a_tier_whatever_the_floors(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_codex_weekly_floor(monkeypatch)
    meters = _credit_meters(ROOMY_SESSION_PERCENT_LEFT, plan_type=UNKNOWN_PLAN_TYPE, has_credits=False, credit_balance=None)

    assert codex_plan_rules.codex_tier(meters) is None


UNRECOGNISED_PLAN_TYPES = ("free_works", "Free_Works", " free_works ", "free trial", "pro_trial", "teams", "freemium", "proo")


@pytest.mark.parametrize("plan_type", UNRECOGNISED_PLAN_TYPES)
def test_should_never_give_a_codex_account_on_an_unrecognised_plan_a_tier(plan_type: str) -> None:
    roomy_meters = _credit_meters(
        ROOMY_SESSION_PERCENT_LEFT, plan_type=plan_type, weekly_percent_left=codex_account_constants.FULL_PERCENT, has_credits=False, credit_balance=None
    )

    assert codex_plan_rules.codex_tier(roomy_meters) is None
    assert codex_plan_rules.codex_tier(dataclasses.replace(roomy_meters, has_credits=True, credit_balance=CREDIT_BALANCE)) is None
    assert codex_plan_rules.codex_tier(dataclasses.replace(roomy_meters, is_credits_unlimited=True)) is None


@pytest.mark.parametrize("plan_type", UNRECOGNISED_PLAN_TYPES)
def test_should_never_give_a_codex_account_on_an_unrecognised_plan_a_tier_whatever_the_floors_or_credits(
    monkeypatch: pytest.MonkeyPatch, plan_type: str
) -> None:
    _disable_codex_weekly_floor(monkeypatch)
    meters = _credit_meters(0.0, plan_type=plan_type, weekly_percent_left=0.0, is_credits_unlimited=True)

    assert codex_plan_rules.codex_tier(meters) is None


@pytest.mark.parametrize("plan_type", UNRECOGNISED_PLAN_TYPES)
def test_should_name_the_missing_plan_when_a_codex_account_is_on_an_unrecognised_plan(plan_type: str) -> None:
    meters = _credit_meters(ROOMY_SESSION_PERCENT_LEFT, plan_type=plan_type)

    assert codex_plan_rules.is_refused_plan(meters) is True
    assert codex_plan_rules.refusal_text("editor", meters) == "editor reports no known plan and is never chosen"


@pytest.mark.parametrize(
    "plan_type", ("pro", "prolite", "promax", "team", "plus", "business", "enterprise", "edu", "Team", " PRO ")
)
def test_should_not_refuse_a_codex_account_on_a_listed_paid_plan(plan_type: str) -> None:
    meters = _credit_meters(ROOMY_SESSION_PERCENT_LEFT, plan_type=plan_type)

    assert codex_plan_rules.is_refused_plan(meters) is False
    assert codex_plan_rules.refusal_text("editor", meters) is None
    assert codex_plan_rules.codex_tier(meters) == codex_account_constants.TIER_NORMAL


def test_should_not_refuse_a_codex_account_whose_meters_could_not_be_read() -> None:
    assert codex_plan_rules.refusal_text("unread", None) is None


@pytest.mark.parametrize(
    ("plan_type", "expected_text"),
    (
        (FREE_PLAN_TYPE, "editor is on a free plan and is never chosen"),
        (None, "editor reports no known plan and is never chosen"),
        (UNKNOWN_PLAN_TYPE, "editor reports no known plan and is never chosen"),
        (TEAM_PLAN_TYPE, None),
        (PRO_PLAN_TYPE, None),
    ),
)
def test_should_name_why_a_codex_plan_is_refused(plan_type: str | None, expected_text: str | None) -> None:
    meters = _credit_meters(ROOMY_SESSION_PERCENT_LEFT, plan_type=plan_type)

    assert codex_plan_rules.refusal_text("editor", meters) == expected_text


def test_should_name_the_free_plan_when_a_free_codex_account_is_the_only_account() -> None:
    meters = _credit_meters(
        ROOMY_SESSION_PERCENT_LEFT, plan_type=FREE_PLAN_TYPE, weekly_percent_left=codex_account_constants.FULL_PERCENT, has_credits=False, credit_balance=None
    )
    reading = broker_constants.Reading(Account(Product.CODEX, "editor", Path("/profiles/editor")), meters)

    decision = broker_constants._wait_decision([reading], WAIT_NOW, frozenset(), {})

    assert decision.action == "wait"
    assert decision.reason == (
        "no account has room (editor is on a free plan and is never chosen); "
        "next check at 2026-10-03T01:00:00+00:00"
    )


def test_should_not_wait_for_a_free_codex_account_to_reset() -> None:
    free_meters = _credit_meters(
        ROOMY_SESSION_PERCENT_LEFT, plan_type=FREE_PLAN_TYPE, weekly_percent_left=codex_account_constants.FULL_PERCENT, has_credits=False, credit_balance=None
    )
    team_meters = _credit_meters(None, plan_type=TEAM_PLAN_TYPE, has_credits=False, credit_balance=None)
    all_readings = [
        broker_constants.Reading(Account(Product.CODEX, "editor", Path("/profiles/editor")), free_meters),
        broker_constants.Reading(Account(Product.CODEX, "team", Path("/profiles/team")), team_meters),
    ]

    decision = broker_constants._wait_decision(all_readings, WAIT_NOW, frozenset(), {})

    assert decision.resets_at == WEEKLY_FLOOR_WEEKLY_RESET
    assert decision.reason == (
        "no account has room (editor is on a free plan and is never chosen, team 0.5% left); "
        "next reset at 2026-10-04T00:00:00+00:00"
    )


@pytest.mark.parametrize(
    ("session_percent_left", "weekly_percent_left"),
    (
        (LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT / 4, ROOMY_SESSION_PERCENT_LEFT * 2),
        (None, LUNA_TIER_STOP_PERCENT_LEFT / 2),
        (LUNA_TIER_STOP_PERCENT_LEFT, LUNA_TIER_STOP_PERCENT_LEFT),
    ),
)
def test_should_let_a_pro_codex_account_with_plan_room_in_both_windows_take_luna(
    session_percent_left: float | None, weekly_percent_left: float
) -> None:
    meters = _credit_meters(
        session_percent_left, weekly_percent_left=weekly_percent_left, has_credits=False, credit_balance=None
    )

    assert codex_plan_rules.codex_blocking_flags(meters) == (False, False)
    assert codex_plan_rules.codex_tier(meters) == codex_account_constants.TIER_LUNA
    assert broker_constants._account_reset(_codex_reading(meters)) is None


@pytest.mark.parametrize(
    ("session_percent_left", "weekly_percent_left", "expected_flags"),
    (
        (codex_account_constants.PRO_PLAN_STOP_PERCENT_LEFT, ROOMY_SESSION_PERCENT_LEFT, (True, False)),
        (ROOMY_SESSION_PERCENT_LEFT, codex_account_constants.PRO_PLAN_STOP_PERCENT_LEFT, (False, True)),
        (codex_account_constants.PRO_PLAN_STOP_PERCENT_LEFT, codex_account_constants.PRO_PLAN_STOP_PERCENT_LEFT, (True, True)),
    ),
)
def test_should_block_a_pro_codex_account_only_when_a_window_has_no_room_left(
    session_percent_left: float, weekly_percent_left: float, expected_flags: tuple[bool, bool]
) -> None:
    meters = _credit_meters(
        session_percent_left, weekly_percent_left=weekly_percent_left, has_credits=False, credit_balance=None
    )

    assert codex_plan_rules.codex_blocking_flags(meters) == expected_flags
    assert codex_plan_rules.codex_tier(meters) is None


def test_should_keep_the_short_window_and_weekly_floors_for_a_team_codex_account_with_pro_room() -> None:
    meters = _credit_meters(
        LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT / 4,
        plan_type=TEAM_PLAN_TYPE,
        weekly_percent_left=ROOMY_SESSION_PERCENT_LEFT * 2,
        has_credits=False,
        credit_balance=None,
    )

    assert codex_plan_rules.codex_blocking_flags(meters) == (True, False)
    assert codex_plan_rules.codex_tier(meters) is None


def test_should_double_the_meter_read_delay_up_to_its_cap() -> None:
    all_delays = [broker_constants.meter_read_delay_seconds(each_attempt) for each_attempt in range(1, 6)]

    assert all_delays == [1.0, 2.0, 4.0, 8.0, 8.0]
