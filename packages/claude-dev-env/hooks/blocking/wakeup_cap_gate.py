#!/usr/bin/env python3
"""PreToolUse hook that keeps every self-wakeup inside the 1-hour prompt cache.

A session that wakes 60 minutes or more after its last turn resumes with a cold
prompt cache and re-reads its whole transcript. The gate reads each tool call
that schedules a later wake of a session and acts on how far away the wake is:

- At most the step-down (57 minutes for send_later and Routines, 3480 seconds
  for ScheduleWakeup): the call passes untouched.
- Over the step-down and at most 60 minutes: the call runs with the delay
  rewritten to the step-down through ``updatedInput``.
- Over 60 minutes: the call is denied with a reason that names the step-down and
  tells the session to stack wakes under it.

A cron schedule cannot be rewritten, so a cron that leaves more than the
step-down between wakes is denied. A Routine that starts a fresh session on each
firing has no cache to keep and passes. An ``update_trigger`` cron change passes,
because its input does not say whether the Routine wakes a session.

The step-down values come from fire-time probes: send_later rounds its fire time
up to the next minute and then waits up to one more minute for its poll, so it
lands up to two minutes after its requested delay. ScheduleWakeup rounds its
fire time up to the next minute and lands a few seconds after it, so it lands up
to about 64 seconds after its requested delay.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
    UPDATED_INPUT_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.wakeup_cap_constants import (
    ADDITIONAL_CONTEXT_KEY,
    ALL_CRON_FIELD_RANGES,
    ALLOW_DECISION,
    ALLOW_EXIT_CODE,
    AT_KEY,
    BLOCK_EXIT_CODE,
    CACHE_LIFETIME_MINUTES,
    CACHE_LIFETIME_SECONDS,
    CREATE_TRIGGER_TOOL_PATTERN,
    CRON_CREATE_TOOL_NAME,
    CRON_EXPRESSION_KEY,
    CRON_FIELD_COUNT,
    CRON_KEY,
    CRON_TIMEZONE_PREFIX_PATTERN,
    DELAY_MINUTES_KEY,
    DELAY_SECONDS_KEY,
    DENY_CRON_DETAIL,
    DENY_DELAY_DETAIL,
    DENY_REASON_TEMPLATE,
    GATE_EVENT_NAME,
    MINUTES_PER_HOUR,
    NEW_SESSION_ON_FIRE_KEY,
    PINNED_FIELD_COUNT,
    RECURRING_KEY,
    REWRITE_CONTEXT_TEMPLATE,
    RFC3339_OUTPUT_FORMAT,
    RUN_ONCE_AT_KEY,
    SCHEDULE_WAKEUP_STEP_DOWN_SECONDS,
    SCHEDULE_WAKEUP_TOOL_NAME,
    SECONDS_PER_MINUTE,
    SEND_LATER_STEP_DOWN_MINUTES,
    SEND_LATER_TOOL_PATTERN,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    UPDATE_TRIGGER_TOOL_PATTERN,
    UTC_OFFSET_TEXT,
    UTC_SUFFIX,
)


@dataclass(frozen=True)
class Rewrite:
    """A tool input field to replace with the step-down value."""

    field: str
    requested: object
    allowed: object


@dataclass(frozen=True)
class Denial:
    """The part of the deny reason that names what the call asked for."""

    detail: str


Decision = Rewrite | Denial | None


def _number_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _parse_utc_moment(text: object) -> datetime | None:
    if not isinstance(text, str):
        return None
    try:
        moment = datetime.fromisoformat(text.strip().replace(UTC_SUFFIX, UTC_OFFSET_TEXT))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment


def _decide_minutes(
    field: str, requested: object, minutes_away: float, allowed: object
) -> Decision:
    if minutes_away > CACHE_LIFETIME_MINUTES:
        return Denial(DENY_DELAY_DETAIL.format(minutes=math.ceil(minutes_away)))
    if minutes_away > SEND_LATER_STEP_DOWN_MINUTES:
        return Rewrite(field, requested, allowed)
    return None


def _decide_delay_minutes(all_tool_input_fields: dict[str, object]) -> Decision:
    requested = all_tool_input_fields.get(DELAY_MINUTES_KEY)
    requested_minutes = _number_or_none(requested)
    if requested_minutes is None:
        return None
    return _decide_minutes(
        DELAY_MINUTES_KEY, requested, requested_minutes, SEND_LATER_STEP_DOWN_MINUTES
    )


def _decide_fire_time(
    field: str, all_tool_input_fields: dict[str, object], now: datetime
) -> Decision:
    requested = all_tool_input_fields.get(field)
    fire_time = _parse_utc_moment(requested)
    if fire_time is None:
        return None
    minutes_away = (fire_time - now).total_seconds() / SECONDS_PER_MINUTE
    latest_allowed = (now + timedelta(minutes=SEND_LATER_STEP_DOWN_MINUTES)).replace(
        second=0, microsecond=0
    )
    allowed_text = latest_allowed.astimezone(timezone.utc).strftime(RFC3339_OUTPUT_FORMAT)
    return _decide_minutes(field, requested, minutes_away, allowed_text)


def _decide_delay_seconds(all_tool_input_fields: dict[str, object]) -> Decision:
    requested = all_tool_input_fields.get(DELAY_SECONDS_KEY)
    requested_seconds = _number_or_none(requested)
    if requested_seconds is None:
        return None
    if requested_seconds > CACHE_LIFETIME_SECONDS:
        return Denial(
            DENY_DELAY_DETAIL.format(minutes=math.ceil(requested_seconds / SECONDS_PER_MINUTE))
        )
    if requested_seconds > SCHEDULE_WAKEUP_STEP_DOWN_SECONDS:
        return Rewrite(DELAY_SECONDS_KEY, requested, SCHEDULE_WAKEUP_STEP_DOWN_SECONDS)
    return None


def _base_bounds(base: str, has_step: bool, lowest: int, highest: int) -> tuple[int, int] | None:
    if base == "*":
        return lowest, highest
    first_text, separator, last_text = base.partition("-")
    if separator and first_text.isdigit() and last_text.isdigit():
        return int(first_text), int(last_text)
    if separator or not base.isdigit():
        return None
    return int(base), highest if has_step else int(base)


def _part_values(cron_part: str, lowest: int, highest: int) -> range | None:
    base, _, step_text = cron_part.partition("/")
    if step_text and not step_text.isdigit():
        return None
    step = int(step_text) if step_text else 1
    bounds = _base_bounds(base, bool(step_text), lowest, highest)
    if bounds is None or step < 1 or not lowest <= bounds[0] <= bounds[1] <= highest:
        return None
    return range(bounds[0], bounds[1] + 1, step)


def _field_values(cron_field: str, lowest: int, highest: int) -> set[int] | None:
    all_values: set[int] = set()
    for each_part in cron_field.split(","):
        part_values = _part_values(each_part, lowest, highest)
        if part_values is None:
            return None
        all_values.update(part_values)
    return all_values


def _covers_every_value(cron_field: str, lowest: int, highest: int, wrap: int) -> bool:
    all_values = _field_values(cron_field, lowest, highest)
    if all_values is None:
        return False
    return {each_value % wrap for each_value in all_values} == set(range(lowest, wrap))


def _cron_fields(cron_expression: str) -> list[str] | None:
    all_fields = CRON_TIMEZONE_PREFIX_PATTERN.sub("", cron_expression.strip()).split()
    if len(all_fields) != CRON_FIELD_COUNT:
        return None
    return all_fields


def longest_cron_gap_minutes(cron_expression: str) -> int | None:
    """Return the longest wait between two firings of a cron schedule, in minutes.

    A schedule that limits its hour, day, month or weekday leaves an hour or more
    between some firings, so it reports the cache lifetime as a floor.

    >>> longest_cron_gap_minutes("*/20 * * * *")
    20
    >>> longest_cron_gap_minutes("5 9 * * *")
    60

    Args:
        cron_expression: A 5-field cron expression, with an optional CRON_TZ prefix.

    Returns:
        The longest gap in minutes, or None when the expression cannot be read.
    """
    all_fields = _cron_fields(cron_expression)
    if all_fields is None:
        return None
    all_minutes = _field_values(all_fields[0], 0, MINUTES_PER_HOUR - 1)
    if not all_minutes:
        return None
    if not _fires_every_hour(all_fields[1:]):
        return CACHE_LIFETIME_MINUTES
    return _longest_minute_gap(all_minutes)


def _fires_every_hour(all_hour_and_day_fields: list[str]) -> bool:
    return all(
        _covers_every_value(each_field, lowest, highest, wrap)
        for each_field, (lowest, highest, wrap) in zip(
            all_hour_and_day_fields, ALL_CRON_FIELD_RANGES, strict=True
        )
    )


def _longest_minute_gap(all_minutes: set[int]) -> int:
    ordered_minutes = sorted(all_minutes)
    all_gaps = [
        later - earlier
        for earlier, later in zip(ordered_minutes, ordered_minutes[1:], strict=False)
    ]
    all_gaps.append(ordered_minutes[0] + MINUTES_PER_HOUR - ordered_minutes[-1])
    return max(all_gaps)


def _decide_cron_gap(cron_expression: object) -> Decision:
    if not isinstance(cron_expression, str):
        return None
    longest_gap = longest_cron_gap_minutes(cron_expression)
    if longest_gap is None or longest_gap <= SEND_LATER_STEP_DOWN_MINUTES:
        return None
    return Denial(DENY_CRON_DETAIL.format(cron=cron_expression, minutes=longest_gap))


def _pinned_local_fire_time(cron_expression: str, now: datetime) -> datetime | None:
    if CRON_TIMEZONE_PREFIX_PATTERN.match(cron_expression.strip()):
        return None
    all_fields = _cron_fields(cron_expression)
    if all_fields is None:
        return None
    all_pinned_fields = all_fields[:PINNED_FIELD_COUNT]
    if not all(each_field.isdigit() for each_field in all_pinned_fields):
        return None
    minute, hour, day, month = (int(each_field) for each_field in all_pinned_fields)
    local_now = now.astimezone()
    try:
        fire_time = local_now.replace(
            month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0
        )
        if fire_time < local_now.replace(second=0, microsecond=0):
            fire_time = fire_time.replace(year=fire_time.year + 1)
    except ValueError:
        return None
    return fire_time


def _decide_pinned_one_shot(fire_time: datetime, now: datetime) -> Decision:
    minutes_away = (fire_time - now).total_seconds() / SECONDS_PER_MINUTE
    if minutes_away > SEND_LATER_STEP_DOWN_MINUTES:
        return Denial(DENY_DELAY_DETAIL.format(minutes=math.ceil(minutes_away)))
    return None


def _decide_cron_create(all_tool_input_fields: dict[str, object], now: datetime) -> Decision:
    cron_expression = all_tool_input_fields.get(CRON_KEY)
    if not isinstance(cron_expression, str):
        return None
    is_one_shot = all_tool_input_fields.get(RECURRING_KEY) is False
    fire_time = _pinned_local_fire_time(cron_expression, now) if is_one_shot else None
    if fire_time is not None:
        return _decide_pinned_one_shot(fire_time, now)
    return _decide_cron_gap(cron_expression)


def _decide_create_trigger(all_tool_input_fields: dict[str, object], now: datetime) -> Decision:
    if all_tool_input_fields.get(NEW_SESSION_ON_FIRE_KEY) is True:
        return None
    if RUN_ONCE_AT_KEY in all_tool_input_fields:
        return _decide_fire_time(RUN_ONCE_AT_KEY, all_tool_input_fields, now)
    return _decide_cron_gap(all_tool_input_fields.get(CRON_EXPRESSION_KEY))


def decide(tool_name: str, all_tool_input_fields: dict[str, object], now: datetime) -> Decision:
    """Return how the gate treats one tool call that may schedule a wake.

    Args:
        tool_name: The name of the tool being called.
        all_tool_input_fields: The tool call's input.
        now: The current time, timezone aware.

    Returns:
        A Rewrite, a Denial, or None when the call passes untouched.
    """
    if tool_name == SCHEDULE_WAKEUP_TOOL_NAME:
        return _decide_delay_seconds(all_tool_input_fields)
    if tool_name == CRON_CREATE_TOOL_NAME:
        return _decide_cron_create(all_tool_input_fields, now)
    if SEND_LATER_TOOL_PATTERN.match(tool_name):
        if DELAY_MINUTES_KEY in all_tool_input_fields:
            return _decide_delay_minutes(all_tool_input_fields)
        return _decide_fire_time(AT_KEY, all_tool_input_fields, now)
    if CREATE_TRIGGER_TOOL_PATTERN.match(tool_name):
        return _decide_create_trigger(all_tool_input_fields, now)
    if UPDATE_TRIGGER_TOOL_PATTERN.match(tool_name):
        return _decide_fire_time(RUN_ONCE_AT_KEY, all_tool_input_fields, now)
    return None


def _write_rewrite(all_tool_input_fields: dict[str, object], rewrite: Rewrite) -> None:
    payload = {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: GATE_EVENT_NAME,
            PERMISSION_DECISION_KEY: ALLOW_DECISION,
            UPDATED_INPUT_KEY: {**all_tool_input_fields, rewrite.field: rewrite.allowed},
            ADDITIONAL_CONTEXT_KEY: REWRITE_CONTEXT_TEMPLATE.format(
                field=rewrite.field,
                requested=rewrite.requested,
                allowed=rewrite.allowed,
                cap=f"{CACHE_LIFETIME_MINUTES} minutes",
            ),
        }
    }
    sys.stdout.write(json.dumps(payload) + "\n")


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    tool_name = hook_input.get(TOOL_NAME_KEY)
    tool_input = hook_input.get(TOOL_INPUT_KEY)
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return ALLOW_EXIT_CODE
    decision = decide(tool_name, tool_input, datetime.now(timezone.utc))
    if isinstance(decision, Rewrite):
        _write_rewrite(tool_input, decision)
        return ALLOW_EXIT_CODE
    if decision is None:
        return ALLOW_EXIT_CODE
    block_reason = DENY_REASON_TEMPLATE.format(
        tool_name=tool_name,
        detail=decision.detail,
        send_later_cap=SEND_LATER_STEP_DOWN_MINUTES,
        schedule_wakeup_cap=SCHEDULE_WAKEUP_STEP_DOWN_SECONDS,
    )
    log_hook_block(
        Path(__file__).name,
        GATE_EVENT_NAME,
        block_reason,
        tool_name=tool_name,
        offending_input_preview=json.dumps(tool_input),
    )
    sys.stderr.write(block_reason)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
