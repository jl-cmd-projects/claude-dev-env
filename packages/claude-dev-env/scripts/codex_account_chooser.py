"""Choose the Codex account a job runs on from the readings of the roster.

::

    pro 5% left, team 90% left, no tier required  ->  pro, tier luna
    the same roster, normal tier required         ->  team, tier normal
    named team home, 0.5% of its week left        ->  that home, tier luna

A Pro plan account that can run comes before every account on another plan. A
named home on a paid plan runs whatever its room, credits or floors. It takes
the tier its meters allow, or the lowest tier when none allows it. A required
tier still applies, so a named home below it does not run.
"""

from __future__ import annotations

from collections.abc import Sequence

from codex_plan_rules import codex_tier, is_pro_plan, is_refused_plan
from dev_env_scripts_constants.account_broker_constants import (
    Decision,
    Reading,
    _rank_key,
)
from dev_env_scripts_constants.codex_account_constants import (
    ALL_TIERS_BEST_FIRST,
    CREDITS_REASON_TEMPLATE,
    NAMED_HOME_REASON_TEMPLATE,
    NORMAL_TIER_MINIMUM_PERCENT_LEFT,
)


def _run_reason(reading: Reading) -> str:
    name = reading.account.name
    percent_left = reading.meters.tightest_percent_left
    if (
        reading.meters.has_spendable_credits
        and percent_left <= NORMAL_TIER_MINIMUM_PERCENT_LEFT
    ):
        return CREDITS_REASON_TEMPLATE.format(name=name, percent=percent_left)
    return f"{name} has {percent_left:g}% left"


def _choose_tier(all_candidates: Sequence[Reading], tier: str) -> Decision | None:
    for each_reading in all_candidates:
        if codex_tier(each_reading.meters) == tier:
            return Decision(
                "run", each_reading.account, None, _run_reason(each_reading), tier
            )
    return None


def _accepted_tiers(required_tier: str | None) -> tuple[str, ...]:
    if required_tier is None:
        return ALL_TIERS_BEST_FIRST
    return ALL_TIERS_BEST_FIRST[: ALL_TIERS_BEST_FIRST.index(required_tier) + 1]


def _choose_named_home(all_available: Sequence[Reading], required_tier: str | None) -> Decision | None:
    for each_reading in all_available:
        if each_reading.meters is None or is_refused_plan(each_reading.meters):
            continue
        allowed_tier = codex_tier(each_reading.meters)
        tier = allowed_tier or ALL_TIERS_BEST_FIRST[-1]
        if tier not in _accepted_tiers(required_tier):
            continue
        reason = (
            _run_reason(each_reading)
            if allowed_tier
            else NAMED_HOME_REASON_TEMPLATE.format(name=each_reading.account.name)
        )
        return Decision("run", each_reading.account, None, reason, tier)
    return None


def choose_codex(
    all_available: Sequence[Reading],
    required_tier: str | None = None,
    *,
    is_home_named: bool = False,
) -> Decision | None:
    """Choose the Codex account for a new job, Pro plan accounts first.

    ::

        roster, team 0.5% of its week left                  ->  None, the job waits
        named home, team 0.5% of its week left             ->  run on that home, tier luna
        named home, free plan or unread meters, any room   ->  None

    Args:
        all_available: Readings of the accounts that are not spent, plus any spent Codex account with spendable credits.
        required_tier: The lowest tier the caller accepts, or None for any tier.
        is_home_named: True when the caller named one Codex home, so its reading
            runs on any paid plan whatever its room, credits or floors, unless
            ``required_tier`` is above the tier it reaches.

    Returns:
        A run decision, or None when no account reaches an accepted tier.
    """
    if is_home_named:
        return _choose_named_home(all_available, required_tier)
    all_candidates = sorted(all_available, key=_rank_key)
    all_pro_candidates = [each_reading for each_reading in all_candidates if is_pro_plan(each_reading.meters)]
    all_other_candidates = [each_reading for each_reading in all_candidates if not is_pro_plan(each_reading.meters)]
    for each_group in (all_pro_candidates, all_other_candidates):
        for each_tier in _accepted_tiers(required_tier):
            chosen = _choose_tier(each_group, each_tier)
            if chosen is not None:
                return chosen
    return None
