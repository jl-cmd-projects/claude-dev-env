"""Plan, credit and floor rules for one Codex account's meters.

::

    free plan, any room, any credits       ->  no tier
    unlisted plan, any room, any credits   ->  no tier
    pro plan, session 5%, week 80%         ->  luna
    team plan, 40% left                    ->  normal

Only a plan on the paid list is chosen. A plan the broker does not list is
refused the way a missing plan is.

This module imports only the Codex constants, so the broker's shared module can
import it without a cycle.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from dev_env_scripts_constants.codex_account_constants import (
    ALL_CODEX_WEEKLY_FLOOR_DISABLED_TRUTHY_VALUES,
    ALL_FREE_PLAN_TYPES,
    ALL_PAID_PLAN_TYPES,
    ALL_PRO_PLAN_TYPES,
    CODEX_WEEKLY_FLOOR_DISABLED_ENVIRONMENT_VARIABLE,
    FREE_PLAN_REASON_TEMPLATE,
    LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT,
    LUNA_TIER_STOP_PERCENT_LEFT,
    NORMAL_TIER_MINIMUM_PERCENT_LEFT,
    PRO_PLAN_STOP_PERCENT_LEFT,
    TIER_LUNA,
    TIER_NORMAL,
    UNKNOWN_PLAN_REASON_TEMPLATE,
)

if TYPE_CHECKING:
    from dev_env_scripts_constants.account_broker_constants import Meters


def is_codex_weekly_floor_disabled() -> bool:
    setting = os.environ.get(CODEX_WEEKLY_FLOOR_DISABLED_ENVIRONMENT_VARIABLE, "")
    return setting.strip().lower() in ALL_CODEX_WEEKLY_FLOOR_DISABLED_TRUTHY_VALUES


def plan_type_key(meters: Meters | None) -> str | None:
    if meters is None or meters.plan_type is None:
        return None
    return meters.plan_type.strip().casefold()


def is_free_plan(meters: Meters | None) -> bool:
    return plan_type_key(meters) in ALL_FREE_PLAN_TYPES


def is_pro_plan(meters: Meters | None) -> bool:
    return plan_type_key(meters) in ALL_PRO_PLAN_TYPES


def is_paid_plan(meters: Meters | None) -> bool:
    return plan_type_key(meters) in ALL_PAID_PLAN_TYPES


def is_unknown_plan(meters: Meters | None) -> bool:
    """Tell whether a read meter names a plan that is neither listed as paid nor free.

    Args:
        meters: The account's meters, or None when they could not be read.

    Returns:
        True when the meters are read and the plan is missing, blank, unknown or
        any name the broker does not list.
    """
    if meters is None:
        return False
    return not is_paid_plan(meters) and not is_free_plan(meters)


def is_refused_plan(meters: Meters | None) -> bool:
    """Tell whether a read meter names a plan the broker never chooses.

    Args:
        meters: The account's meters, or None when they could not be read.

    Returns:
        True when the meters are read and the plan is not on the paid list.
    """
    return meters is not None and not is_paid_plan(meters)


def refusal_text(account_name: str, meters: Meters | None) -> str | None:
    """Name why an account on a refused plan is never chosen.

    Args:
        account_name: The account's name.
        meters: The account's meters, or None when they could not be read.

    Returns:
        The free-plan text for the free plan, the no-known-plan text for a
        missing, blank, unknown or unlisted plan, or None for a paid plan.
    """
    if is_free_plan(meters):
        return FREE_PLAN_REASON_TEMPLATE.format(name=account_name)
    if is_unknown_plan(meters):
        return UNKNOWN_PLAN_REASON_TEMPLATE.format(name=account_name)
    return None


def _is_at_or_under_floor(room: float | None, floor: float) -> bool:
    return room is not None and room <= floor


def codex_blocking_flags(meters: Meters) -> tuple[bool, bool]:
    """Tell which windows keep an account out of the luna tier.

    Args:
        meters: The account's read meters.

    Returns:
        A pair of flags for the session window and the weekly window.
    """
    if meters.has_spendable_credits:
        return False, False
    if is_pro_plan(meters):
        return (
            _is_at_or_under_floor(meters.session_percent_left, PRO_PLAN_STOP_PERCENT_LEFT),
            _is_at_or_under_floor(meters.weekly_percent_left, PRO_PLAN_STOP_PERCENT_LEFT),
        )
    return (
        meters.session_percent_left is not None
        and meters.session_percent_left < LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT,
        _is_at_or_under_floor(meters.weekly_percent_left, LUNA_TIER_STOP_PERCENT_LEFT)
        and not is_codex_weekly_floor_disabled(),
    )


def codex_tier(meters: Meters | None) -> str | None:
    """Pick the tier one account's meters allow.

    Args:
        meters: The account's meters, or None when they could not be read.

    Returns:
        The normal or luna tier, or None when the account cannot run.
    """
    if meters is None or meters.tightest_percent_left is None or is_refused_plan(meters):
        return None
    if (
        meters.has_spendable_credits
        or meters.tightest_percent_left > NORMAL_TIER_MINIMUM_PERCENT_LEFT
    ):
        return TIER_NORMAL
    if not any(codex_blocking_flags(meters)):
        return TIER_LUNA
    return None
