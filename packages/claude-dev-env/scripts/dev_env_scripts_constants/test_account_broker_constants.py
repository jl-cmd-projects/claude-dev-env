"""Floors and outcome shape for the account broker."""

from __future__ import annotations

import dataclasses

import pytest

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
