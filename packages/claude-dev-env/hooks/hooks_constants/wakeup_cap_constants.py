"""Constants for wakeup_cap_gate.py."""

import re

TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
GATE_EVENT_NAME = "PreToolUse"
ALLOW_EXIT_CODE = 0
BLOCK_EXIT_CODE = 2
ALLOW_DECISION = "allow"
ADDITIONAL_CONTEXT_KEY = "additionalContext"

SCHEDULE_WAKEUP_TOOL_NAME = "ScheduleWakeup"
CRON_CREATE_TOOL_NAME = "CronCreate"
SEND_LATER_TOOL_PATTERN = re.compile(r"^mcp__.+__send_later$")
CREATE_TRIGGER_TOOL_PATTERN = re.compile(r"^mcp__.+__create_trigger$")
UPDATE_TRIGGER_TOOL_PATTERN = re.compile(r"^mcp__.+__update_trigger$")

DELAY_SECONDS_KEY = "delaySeconds"
DELAY_MINUTES_KEY = "delay_minutes"
AT_KEY = "at"
RUN_ONCE_AT_KEY = "run_once_at"
CRON_EXPRESSION_KEY = "cron_expression"
CRON_KEY = "cron"
RECURRING_KEY = "recurring"
NEW_SESSION_ON_FIRE_KEY = "create_new_session_on_fire"

SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60
CACHE_LIFETIME_MINUTES = 60
CACHE_LIFETIME_SECONDS = CACHE_LIFETIME_MINUTES * SECONDS_PER_MINUTE
SEND_LATER_STEP_DOWN_MINUTES = 57
SCHEDULE_WAKEUP_STEP_DOWN_SECONDS = 3480

CRON_TIMEZONE_PREFIX_PATTERN = re.compile(r"^CRON_TZ=\S+\s+")
CRON_FIELD_COUNT = 5
PINNED_FIELD_COUNT = 4
ALL_CRON_FIELD_RANGES = ((0, 23, 24), (1, 31, 32), (1, 12, 13), (0, 7, 7))
UTC_SUFFIX = "Z"
UTC_OFFSET_TEXT = "+00:00"
RFC3339_OUTPUT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

REWRITE_CONTEXT_TEMPLATE = (
    "wakeup_cap_gate rewrote {field} from {requested} to {allowed}. A wake {cap} or later"
    " lands after the 1-hour prompt cache expires, so this wake now fires sooner."
)
DENY_REASON_TEMPLATE = (
    "wakeup_cap_gate refused {tool_name}: {detail} A wake 60 minutes or more after the last"
    " turn lands after the 1-hour prompt cache expires and resumes cold. Arm a wake of at"
    " most {send_later_cap} minutes (send_later delay_minutes={send_later_cap}, ScheduleWakeup"
    " delaySeconds={schedule_wakeup_cap}). For a longer wait, stack wakes under that cap:"
    " put the remaining wait in the wake prompt and re-arm on each wake until it is covered,"
    " as the usage-pause skill's stages_seconds chain does."
)
DENY_DELAY_DETAIL = "the wake is {minutes} minutes away."
DENY_CRON_DETAIL = "the cron '{cron}' leaves {minutes} minutes or more between wakes."
