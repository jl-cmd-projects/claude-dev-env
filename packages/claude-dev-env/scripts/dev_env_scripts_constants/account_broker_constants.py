"""Account floors and command status values for the shared account broker."""

from __future__ import annotations

import importlib.machinery
import os
import subprocess
import types
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping, Sequence

from dev_env_scripts_constants.claude_account_constants import (
    FULL_PERCENT,
    MAIN_SESSION_USED_CEILING_PERCENT,
    MAIN_WEEKLY_USED_CEILING_PERCENT,
    PROFILES_ROOT_ENVIRONMENT_VARIABLE,
    SECOND_SESSION_USED_CEILING_PERCENT,
    SECOND_WEEKLY_USED_CEILING_PERCENT,
)
from dev_env_scripts_constants.claude_chain_usage_constants import NO_ACCESS_TOKEN_ERROR_TEMPLATE
from dev_env_scripts_constants.codex_account_constants import (
    CODEX_ACCOUNT_PROFILES_ENVIRONMENT_VARIABLE,
    CODEX_HOME_ENVIRONMENT_VARIABLE,
    CODEX_PROFILES_ROOT_ENVIRONMENT_VARIABLE,
    CODEX_WEEKLY_FLOOR_DISABLED_ENVIRONMENT_VARIABLE,
    LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT,
    LUNA_TIER_STOP_PERCENT_LEFT,
    NORMAL_TIER_MINIMUM_PERCENT_LEFT,
    TIER_NORMAL,
)
from dev_env_scripts_constants.shared_tree_constants import (
    CLAUDE_CONFIG_DIR_ENV_VAR,
    CODEX_CLASSIFIER_CONSTANTS_RELATIVE_PATH,
    CONSTANTS_PACKAGE_ANCHOR_DEPTH,
    PR_LOOP_DIRECTORY_NAME,
)
from codex_plan_rules import codex_blocking_flags, is_pro_plan, refusal_text
from shared_tree_paths import resolve_shared_scripts_directory

ALL_CHOOSE_AND_CHECK_ACTIONS = ("choose", "check")

ALL_CLAUDE_FLOORS = {
    "main_weekly_used_ceiling": MAIN_WEEKLY_USED_CEILING_PERCENT,
    "main_session_used_ceiling": MAIN_SESSION_USED_CEILING_PERCENT,
    "extra_weekly_used_ceiling": SECOND_WEEKLY_USED_CEILING_PERCENT,
    "extra_session_used_ceiling": SECOND_SESSION_USED_CEILING_PERCENT,
}

ALL_CODEX_FLOORS = {
    "normal_minimum_left": NORMAL_TIER_MINIMUM_PERCENT_LEFT,
    "luna_stop_left": LUNA_TIER_STOP_PERCENT_LEFT,
    "luna_short_minimum_left": LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT,
}

METER_READ_ATTEMPTS = 3
METER_READ_FIRST_DELAY_SECONDS = 1.0
METER_READ_DELAY_FACTOR = 2.0
METER_READ_MAX_DELAY_SECONDS = 8.0
LAST_GOOD_METER_MAX_AGE_SECONDS = 1800.0
METER_RATE_LIMIT_COOLDOWN_SECONDS = 300.0
PUBLISHED_USAGE_DIRECTORY_ENV_VAR = "CLAUDE_USAGE_READINGS_DIR"
PUBLISHED_USAGE_FILE_PATTERN = "meters-*.json"
PUBLISHED_USAGE_MAX_AGE_SECONDS = 1800.0
WAIT_EXIT_CODE = 3
COMMAND_MISSING_EXIT_CODE = 127
TIMEOUT_EXIT_CODE = 124
NO_USABLE_ACCOUNT_EXIT_CODE = 4
NO_USABLE_ACCOUNT_STATUS = "no_usable_account"
NO_USABLE_REASON_SEPARATOR = "; "
SIGN_IN_FAILED_STATUS = "sign_in_failed"
ALL_SIGN_IN_FAILURE_SIGNATURES: tuple[str, ...] = (
    "stored token expired",
    "authorization failed",
    "organization has status: canceled",
)
"""Case-insensitive substrings that mark a failed Claude run as a sign-in failure of its account."""
NO_USABLE_TOKEN_REASON_PREFIX = NO_ACCESS_TOKEN_ERROR_TEMPLATE.partition("{")[0]
REPORT_INDENT_SPACES = 2
PLACEHOLDER_NAME_SLOT = "{name}"
BROKER_STATE_DIRECTORY_NAME = "account-broker"
BROKER_STATE_FILE_NAME = "state.json"
BROKER_STATE_TEMP_SUFFIX = ".json"
BROKER_STATE_LOCK_SUFFIX = ".lock"
ALL_ACCOUNT_ENVIRONMENT_VARIABLES = (
    CLAUDE_CONFIG_DIR_ENV_VAR,
    CODEX_HOME_ENVIRONMENT_VARIABLE,
    CODEX_ACCOUNT_PROFILES_ENVIRONMENT_VARIABLE,
    CODEX_PROFILES_ROOT_ENVIRONMENT_VARIABLE,
    CODEX_WEEKLY_FLOOR_DISABLED_ENVIRONMENT_VARIABLE,
    PROFILES_ROOT_ENVIRONMENT_VARIABLE,
)
"""Variables that point the account tools at a developer's own account roots, Codex home and Codex roster, or lift the Codex weekly floor."""
ALL_BATCH_FILE_EXTENSIONS = frozenset({".bat", ".cmd"})
CMD_SHELL_METACHARACTERS = "&|<>^%!\"\r\n"
CLAUDE_BINARY_NAME = "claude"
ALL_CLAUDE_BINARY_CANDIDATE_RELATIVE_PARTS: tuple[tuple[str, ...], ...] = (
    (".local", "bin", "claude.exe"),
    (".local", "bin", "claude"),
)
ALL_LOGIN_REFRESH_ARGUMENTS: tuple[str, ...] = (
    "-p",
    "ok",
    "--model",
    "haiku",
    "--setting-sources",
    "local",
    "--settings",
    '{"enabledPlugins": {}, "autoMemoryEnabled": false}',
    "--strict-mcp-config",
    "--mcp-config",
    '{"mcpServers": {}}',
    "--no-session-persistence",
    "--disable-slash-commands",
    "--tools",
    "",
    "--max-turns",
    "1",
)
ALL_LOGIN_REFRESH_ENVIRONMENT: dict[str, str] = {
    "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "DISABLE_TELEMETRY": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "DISABLE_AUTOUPDATER": "1",
}
LOGIN_REFRESH_TIMEOUT_SECONDS = 120.0
ALL_PARENT_CLAUDE_SESSION_VARIABLES: frozenset[str] = frozenset({
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_REMOTE",
    "CLAUDE_CODE_REMOTE_SESSION_ID",
    "CLAUDE_CODE_MESSAGING_SOCKET",
    "CLAUDE_CODE_MESSAGING_TOKEN",
    "CLAUDE_SESSION_INGRESS_TOKEN_FILE",
    "CLAUDE_CODE_POST_FOR_SESSION_INGRESS_V2",
    "CLAUDE_CODE_TEE_SDK_STDOUT",
    "CLAUDE_CODE_SYNC_SESSION_REFS",
    "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_SESSION_ATTENDED",
    "CLAUDECODE",
    "CLAUDE_PID",
    "CLAUDE_AFTER_LAST_COMPACT",
    "CLAUDE_CODE_DIAGNOSTICS_FILE",
    "CLAUDE_CODE_REMOTE_SEND_KEEPALIVES",
    "CLAUDE_CODE_WORKER_EPOCH",
    "CLAUDE_CODE_SYNC_SKILLS",
    "CLAUDE_EFFORT",
})


def codex_usage_limit_signatures() -> tuple[str, ...]:
    """Load usage limit markers.

    Returns:
        Markers that identify usage limit responses.

    Raises:
        ImportError: The marker module cannot be loaded.
    """
    constants_path = resolve_shared_scripts_directory(__file__, os.environ, PR_LOOP_DIRECTORY_NAME, CODEX_CLASSIFIER_CONSTANTS_RELATIVE_PATH, CONSTANTS_PACKAGE_ANCHOR_DEPTH) / CODEX_CLASSIFIER_CONSTANTS_RELATIVE_PATH
    loader = importlib.machinery.SourceFileLoader("account_broker_codex_classifier_constants", str(constants_path))
    module = types.ModuleType(loader.name)
    try:
        loader.exec_module(module)
    except OSError as error:
        raise ImportError(f"cannot load usage markers from {constants_path}") from error
    return module.ALL_USAGE_LIMIT_MARKERS


def meter_read_delay_seconds(attempt_index: int) -> float:
    """Seconds to wait before a meter read retry, where the first retry has index 1."""
    return min(METER_READ_FIRST_DELAY_SECONDS * METER_READ_DELAY_FACTOR ** (attempt_index - 1), METER_READ_MAX_DELAY_SECONDS)


def utc_time_text(moment: datetime | None) -> str | None:
    return moment.astimezone(timezone.utc).isoformat() if moment is not None else None


def parse_utc_time(timestamp: object) -> datetime | None:
    """Parse an ISO timestamp as UTC.

    Args:
        timestamp: Serialized timestamp.

    Returns:
        UTC timestamp or None.
    """
    if not isinstance(timestamp, str):
        return None
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


class Product(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"


class BrokerConfigurationError(Exception):
    """An account list cannot be read."""


@dataclass(frozen=True)
class Account:
    product: Product
    name: str
    home: Path
    is_main: bool = False
    command: str | None = None
    priority: int | None = None
    profile: str | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Meters:
    session_percent_left: float | None
    session_resets_at: datetime | None
    weekly_percent_left: float | None
    weekly_resets_at: datetime | None
    plan_type: str | None = None
    has_credits: bool = False
    is_credits_unlimited: bool = False
    credit_balance: float | None = None

    @property
    def tightest_percent_left(self) -> float | None:
        all_percentages = (self.session_percent_left, self.weekly_percent_left)
        return min((each_percent for each_percent in all_percentages if each_percent is not None), default=None)

    @property
    def has_spendable_credits(self) -> bool:
        if self.is_credits_unlimited:
            return True
        return self.has_credits and self.credit_balance is not None and self.credit_balance > 0


@dataclass(frozen=True)
class Reading:
    account: Account
    meters: Meters | None
    unread_reason: str | None = None
    measured_at: datetime | None = None
    retry_at: datetime | None = None


@dataclass(frozen=True)
class Decision:
    action: str
    account: Account | None
    resets_at: datetime | None
    reason: str
    tier: str | None


@dataclass(frozen=True)
class JobOutcome:
    returncode: int
    stdout: str
    stderr: str
    account_name: str | None
    attempts: tuple[tuple[str, str], ...]
    status: str
    session_id: str | None
    wait_reset_at: datetime | None
    wait_reason: str | None = None


@dataclass
class Report:
    product: Product
    command: list[str]
    events: list[dict[str, object]] = field(default_factory=list)
    final_decision: Decision | None = None


MeterReader = Callable[[Account], Meters | None]
AccountLoader = Callable[[], Sequence[Account]]
SubprocessRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class ProductAdapter:
    load_accounts: AccountLoader
    read_meters: MeterReader
    environment_variable: str
    usage_limit_signatures: tuple[str, ...]


def _is_at_or_under(room: float | None, floor: float) -> bool:
    return room is not None and room <= floor


def _claude_blocking_flags(meters: Meters, is_main: bool) -> tuple[bool, bool]:
    session_key, weekly_key = (
        ("main_session_used_ceiling", "main_weekly_used_ceiling")
        if is_main
        else ("extra_session_used_ceiling", "extra_weekly_used_ceiling")
    )
    return (
        _is_at_or_under(meters.session_percent_left, FULL_PERCENT - ALL_CLAUDE_FLOORS[session_key]),
        _is_at_or_under(meters.weekly_percent_left, FULL_PERCENT - ALL_CLAUDE_FLOORS[weekly_key]),
    )


def _account_reset(reading: Reading, is_spent: bool = False) -> datetime | None:
    meters = reading.meters
    if meters is None:
        return None
    if is_spent:
        return min((reset for reset in (meters.session_resets_at, meters.weekly_resets_at) if reset is not None), default=None)
    if reading.account.product is Product.CLAUDE:
        all_blocking_flags = _claude_blocking_flags(meters, reading.account.is_main)
    else:
        all_blocking_flags = codex_blocking_flags(meters)
    all_resets = (meters.session_resets_at, meters.weekly_resets_at)
    all_blocking_resets = [reset for is_blocking, reset in zip(all_blocking_flags, all_resets) if is_blocking]
    all_known_resets = [reset for reset in all_blocking_resets if reset is not None]
    if len(all_known_resets) < len(all_blocking_resets):
        return None
    return max(all_known_resets, default=None)


def _rank_key(reading: Reading) -> tuple[bool, int, bool, float]:
    room = reading.meters.tightest_percent_left if reading.meters else None
    priority = reading.account.priority
    is_pro_plan_account = is_pro_plan(reading.meters)
    return (priority is None, priority or 0, not is_pro_plan_account, -(room if room is not None else -1.0))


def _claude_has_room(reading: Reading) -> bool:
    meters = reading.meters
    return (
        meters is not None
        and meters.tightest_percent_left is not None
        and not any(_claude_blocking_flags(meters, reading.account.is_main))
    )


def _choose_claude(all_available: Sequence[Reading], preferred_command: str | None) -> Decision | None:
    all_with_room = [each_reading for each_reading in all_available if _claude_has_room(each_reading)]
    for each_reading in all_with_room:
        is_bound = preferred_command in (each_reading.account.command, each_reading.account.name)
        if preferred_command is not None and is_bound:
            return Decision("run", each_reading.account, None, "resume affinity", TIER_NORMAL)
    chosen = min(all_with_room, key=_rank_key, default=None)
    if chosen is None:
        return None
    room_text = f"{chosen.account.name} has {chosen.meters.tightest_percent_left:g}% left"
    if chosen.account.priority is not None:
        room_text = f"{room_text}; priority {chosen.account.priority + 1} in the account order"
    return Decision("run", chosen.account, None, room_text, TIER_NORMAL)


@dataclass(frozen=True)
class _RetryTime:
    at: datetime
    is_known_reset: bool


def _unreadable_text(reading: Reading) -> str:
    if reading.unread_reason is None:
        return reading.account.name
    return f"{reading.account.name} ({reading.unread_reason})"


def _refusal_text(reading: Reading) -> str | None:
    if reading.account.product is not Product.CODEX:
        return None
    return refusal_text(reading.account.name, reading.meters)


def _room_text(reading: Reading, is_spent: bool) -> str:
    if is_spent or reading.meters is None:
        return f"{reading.account.name} spent"
    refusal = _refusal_text(reading)
    if refusal is not None:
        return refusal
    percent_left = reading.meters.tightest_percent_left
    if percent_left is None:
        return f"{reading.account.name} percent left unread"
    return f"{reading.account.name} {percent_left:g}% left"


def _wait_reason(
    all_room_texts: Sequence[str], all_unreadable_names: Sequence[str], is_every_account_unreadable: bool, soonest: _RetryTime
) -> str:
    next_event = "reset" if soonest.is_known_reset else "check"
    next_text = f"next {next_event} at {utc_time_text(soonest.at)}"
    room_text = f" ({', '.join(all_room_texts)})" if all_room_texts else ""
    if not all_unreadable_names:
        return f"no account has room{room_text}; {next_text}"
    unreadable_text = ", ".join(all_unreadable_names)
    if is_every_account_unreadable:
        return f"no account meter could be read ({unreadable_text}); {next_text}"
    return f"no readable account has room{room_text}; meter unreadable for {unreadable_text}; {next_text}"


def _wait_decision(
    all_readings: Sequence[Reading], now: datetime, all_spent_accounts: frozenset[Account], all_spent_resets: Mapping[Account, datetime]
) -> Decision:
    next_check = _RetryTime(now + timedelta(hours=1), is_known_reset=False)
    all_retry_times = []
    for each_reading in all_readings:
        if _refusal_text(each_reading) is not None:
            continue
        is_spent = each_reading.account in all_spent_accounts
        spent_reset = all_spent_resets.get(each_reading.account) if is_spent else None
        known_reset = spent_reset or _account_reset(each_reading, is_spent)
        chosen_reset = known_reset or each_reading.retry_at
        if chosen_reset is not None and chosen_reset > now:
            all_retry_times.append(_RetryTime(chosen_reset, is_known_reset=known_reset is not None))
        else:
            all_retry_times.append(next_check)
    soonest = min(all_retry_times, key=lambda each_retry_time: each_retry_time.at, default=next_check)
    all_unreadable_names = [
        _unreadable_text(each_reading)
        for each_reading in all_readings
        if each_reading.meters is None and each_reading.account not in all_spent_accounts
    ]
    all_room_texts = [
        _room_text(each_reading, each_reading.account in all_spent_accounts)
        for each_reading in all_readings
        if each_reading.meters is not None or each_reading.account in all_spent_accounts
    ]
    is_every_account_unreadable = len(all_unreadable_names) == len(all_readings)
    reason = _wait_reason(all_room_texts, all_unreadable_names, is_every_account_unreadable, soonest)
    return Decision("wait", None, soonest.at, reason, "wait")
