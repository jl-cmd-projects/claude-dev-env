"""Floors, outcome shape, and time helpers for the account broker."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from dev_env_scripts_constants import account_broker_constants as broker_constants
from dev_env_scripts_constants.account_broker_constants import (
    ALL_CLAUDE_FLOORS,
    ALL_CODEX_FLOORS,
    JobOutcome,
)
from dev_env_scripts_constants.claude_account_constants import (
    MAIN_SESSION_USED_CEILING_PERCENT,
    MAIN_SPEND_WINDOW,
    MAIN_WEEKLY_USED_CEILING_PERCENT,
    SECOND_SESSION_USED_CEILING_PERCENT,
    SECOND_WEEKLY_USED_CEILING_PERCENT,
)
from dev_env_scripts_constants.codex_account_constants import (
    LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT,
    LUNA_TIER_STOP_PERCENT_LEFT,
    NORMAL_TIER_MINIMUM_PERCENT_LEFT,
)


def test_should_keep_claude_floors_tied_to_the_account_ceilings() -> None:
    assert ALL_CLAUDE_FLOORS == {
        "main_weekly_used_ceiling": MAIN_WEEKLY_USED_CEILING_PERCENT,
        "main_session_used_ceiling": MAIN_SESSION_USED_CEILING_PERCENT,
        "main_spend_window": MAIN_SPEND_WINDOW,
        "extra_weekly_used_ceiling": SECOND_WEEKLY_USED_CEILING_PERCENT,
        "extra_session_used_ceiling": SECOND_SESSION_USED_CEILING_PERCENT,
    }


def test_should_keep_codex_floors_tied_to_the_tier_limits() -> None:
    assert ALL_CODEX_FLOORS == {
        "normal_minimum_left": NORMAL_TIER_MINIMUM_PERCENT_LEFT,
        "luna_stop_left": LUNA_TIER_STOP_PERCENT_LEFT,
        "luna_short_minimum_left": LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT,
    }


def test_should_freeze_job_outcome() -> None:
    outcome = JobOutcome(0, "", "", None, (), "served", None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.status = "wait"


def test_codex_usage_limit_signatures_loads_classifier_markers() -> None:
    signatures = broker_constants.codex_usage_limit_signatures()

    assert "rate limit" in signatures
    assert "http 429" in signatures


def test_utc_time_text_converts_an_offset_timestamp() -> None:
    moment = datetime(2026, 10, 3, 7, 30, tzinfo=timezone(timedelta(hours=-4)))

    assert broker_constants.utc_time_text(moment) == "2026-10-03T11:30:00+00:00"
    assert broker_constants.utc_time_text(None) is None


@pytest.mark.parametrize("timestamp", (None, 123, "not a timestamp", "2026-10-03T11:30:00"))
def test_parse_utc_time_rejects_values_without_a_timezone(timestamp: object) -> None:
    assert broker_constants.parse_utc_time(timestamp) is None


def test_parse_utc_time_converts_an_offset_timestamp() -> None:
    parsed = broker_constants.parse_utc_time("2026-10-03T07:30:00-04:00")

    assert parsed is not None
    assert parsed.isoformat() == "2026-10-03T11:30:00+00:00"
