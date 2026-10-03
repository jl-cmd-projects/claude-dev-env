"""Account floors and command status values for the shared account broker."""

from __future__ import annotations

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

ALL_CLAUDE_FLOORS = {
    "main_weekly_used_ceiling": MAIN_WEEKLY_USED_CEILING_PERCENT,
    "main_session_used_ceiling": MAIN_SESSION_USED_CEILING_PERCENT,
    "main_spend_window": MAIN_SPEND_WINDOW,
    "extra_weekly_used_ceiling": SECOND_WEEKLY_USED_CEILING_PERCENT,
    "extra_session_used_ceiling": SECOND_SESSION_USED_CEILING_PERCENT,
}

ALL_CODEX_FLOORS = {
    "normal_minimum_left": NORMAL_TIER_MINIMUM_PERCENT_LEFT,
    "luna_stop_left": LUNA_TIER_STOP_PERCENT_LEFT,
    "luna_short_minimum_left": LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT,
}

WAIT_EXIT_CODE = 3
COMMAND_MISSING_EXIT_CODE = 127
REPORT_INDENT_SPACES = 2
