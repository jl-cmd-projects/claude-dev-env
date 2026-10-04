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
    SECOND_SESSION_USED_CEILING_PERCENT,
    SECOND_WEEKLY_USED_CEILING_PERCENT,
)
from dev_env_scripts_constants.codex_account_constants import (
    CODEX_HOME_ENVIRONMENT_VARIABLE,
    LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT,
    LUNA_TIER_STOP_PERCENT_LEFT,
    MAIN_CODEX_HOME_DIRECTORY_NAME,
    NORMAL_TIER_MINIMUM_PERCENT_LEFT,
    TIER_LUNA,
    TIER_NORMAL,
)
from dev_env_scripts_constants.shared_tree_constants import (
    CODEX_CLASSIFIER_CONSTANTS_RELATIVE_PATH,
    CONSTANTS_PACKAGE_ANCHOR_DEPTH,
    PR_LOOP_DIRECTORY_NAME,
)
from shared_tree_paths import resolve_shared_scripts_directory

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

WAIT_EXIT_CODE = 3
COMMAND_MISSING_EXIT_CODE = 127
TIMEOUT_EXIT_CODE = 124
REPORT_INDENT_SPACES = 2
BROKER_STATE_DIRECTORY_NAME = "account-broker"
BROKER_STATE_FILE_NAME = "state.json"
BROKER_STATE_TEMP_SUFFIX = ".json"
BROKER_STATE_LOCK_SUFFIX = ".lock"
ALL_BATCH_FILE_EXTENSIONS = frozenset({".bat", ".cmd"})
CMD_SHELL_METACHARACTERS = "&|<>^%!\"\r\n"
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


@dataclass(frozen=True)
class Meters:
    session_percent_left: float | None
    session_resets_at: datetime | None
    weekly_percent_left: float | None
    weekly_resets_at: datetime | None

    @property
    def tightest_percent_left(self) -> float | None:
        all_percentages = (self.session_percent_left, self.weekly_percent_left)
        return min((each_percent for each_percent in all_percentages if each_percent is not None), default=None)


@dataclass(frozen=True)
class Reading:
    account: Account
    meters: Meters | None


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


def _claude_extra_tier(meters: Meters | None) -> str | None:
    if meters is None or meters.tightest_percent_left is None:
        return None
    if (
        meters.weekly_percent_left is not None
        and meters.weekly_percent_left <= FULL_PERCENT - ALL_CLAUDE_FLOORS["extra_weekly_used_ceiling"]
    ) or (
        meters.session_percent_left is not None
        and meters.session_percent_left <= FULL_PERCENT - ALL_CLAUDE_FLOORS["extra_session_used_ceiling"]
    ):
        return None
    return "normal"


def _codex_tier(meters: Meters | None) -> str | None:
    if meters is None or meters.tightest_percent_left is None:
        return None
    if meters.tightest_percent_left > ALL_CODEX_FLOORS["normal_minimum_left"]:
        return "normal"
    if (
        meters.tightest_percent_left > ALL_CODEX_FLOORS["luna_stop_left"]
        and (
            meters.session_percent_left is None
            or meters.session_percent_left >= ALL_CODEX_FLOORS["luna_short_minimum_left"]
        )
    ):
        return "luna"
    return None


def _account_reset(reading: Reading, is_spent: bool = False) -> datetime | None:
    meters = reading.meters
    if meters is None:
        return None
    if is_spent:
        return min((reset for reset in (meters.session_resets_at, meters.weekly_resets_at) if reset is not None), default=None)
    is_claude_main = reading.account.product is Product.CLAUDE and reading.account.is_main
    if is_claude_main:
        blocking = (
            (meters.session_percent_left, FULL_PERCENT - ALL_CLAUDE_FLOORS["main_session_used_ceiling"], meters.session_resets_at),
            (meters.weekly_percent_left, FULL_PERCENT - ALL_CLAUDE_FLOORS["main_weekly_used_ceiling"], meters.weekly_resets_at),
        )
    elif reading.account.product is Product.CLAUDE:
        blocking = (
            (meters.session_percent_left, FULL_PERCENT - ALL_CLAUDE_FLOORS["extra_session_used_ceiling"], meters.session_resets_at),
            (meters.weekly_percent_left, FULL_PERCENT - ALL_CLAUDE_FLOORS["extra_weekly_used_ceiling"], meters.weekly_resets_at),
        )
    else:
        blocking = (
            (meters.session_percent_left, ALL_CODEX_FLOORS["luna_short_minimum_left"], meters.session_resets_at),
            (meters.weekly_percent_left, ALL_CODEX_FLOORS["luna_stop_left"], meters.weekly_resets_at),
        )
    all_blocking_resets = [reset for room, floor, reset in blocking if room is not None and room <= floor and reset is not None]
    return max(all_blocking_resets, default=None)


def _rank_key(reading: Reading) -> float:
    room = reading.meters.tightest_percent_left if reading.meters else None
    return -(room if room is not None else -1.0)


def _main_has_room(meters: Meters | None) -> bool:
    return bool(
        meters is not None
        and meters.session_percent_left is not None
        and meters.weekly_percent_left is not None
        and meters.session_percent_left > FULL_PERCENT - ALL_CLAUDE_FLOORS["main_session_used_ceiling"]
        and meters.weekly_percent_left > FULL_PERCENT - ALL_CLAUDE_FLOORS["main_weekly_used_ceiling"]
    )


def _claude_has_room(reading: Reading) -> bool:
    if reading.account.is_main:
        return _main_has_room(reading.meters)
    return _claude_extra_tier(reading.meters) is not None


def _choose_claude(all_available: Sequence[Reading], preferred_command: str | None) -> Decision | None:
    all_with_room = [each_reading for each_reading in all_available if _claude_has_room(each_reading)]
    for each_reading in all_with_room:
        is_bound = preferred_command in (each_reading.account.command, each_reading.account.name)
        if preferred_command is not None and is_bound:
            return Decision("run", each_reading.account, None, "resume affinity", TIER_NORMAL)
    roomiest = min(all_with_room, key=_rank_key, default=None)
    if roomiest is None:
        return None
    return Decision("run", roomiest.account, None, f"{roomiest.account.name} has {roomiest.meters.tightest_percent_left:g}% left", TIER_NORMAL)


def _choose_codex(all_available: Sequence[Reading]) -> Decision | None:
    all_candidates = sorted(all_available, key=_rank_key)
    for each_tier in (TIER_NORMAL, TIER_LUNA):
        chosen = _choose_codex_tier(all_candidates, each_tier)
        if chosen is not None:
            return chosen
    return None


def _choose_codex_tier(all_candidates: Sequence[Reading], tier: str) -> Decision | None:
    for each_reading in all_candidates:
        if _codex_tier(each_reading.meters) == tier:
            return Decision("run", each_reading.account, None, f"{each_reading.account.name} has {each_reading.meters.tightest_percent_left:g}% left", tier)
    return None


@dataclass(frozen=True)
class _RetryTime:
    at: datetime
    is_known_reset: bool


def _wait_reason(all_unreadable_names: Sequence[str], is_every_account_unreadable: bool, soonest: _RetryTime) -> str:
    next_event = "reset" if soonest.is_known_reset else "check"
    next_text = f"next {next_event} at {utc_time_text(soonest.at)}"
    if not all_unreadable_names:
        return f"no account has room; {next_text}"
    unreadable_text = ", ".join(all_unreadable_names)
    if is_every_account_unreadable:
        return f"no account meter could be read ({unreadable_text}); {next_text}"
    return f"no readable account has room; meter unreadable for {unreadable_text}; {next_text}"


def _wait_decision(
    all_readings: Sequence[Reading], now: datetime, all_spent_accounts: frozenset[Account], all_spent_resets: Mapping[Account, datetime]
) -> Decision:
    next_check = _RetryTime(now + timedelta(hours=1), is_known_reset=False)
    all_retry_times = []
    for each_reading in all_readings:
        is_spent = each_reading.account in all_spent_accounts
        reset = all_spent_resets.get(each_reading.account) if is_spent else None
        reset = reset or _account_reset(each_reading, is_spent)
        all_retry_times.append(_RetryTime(reset, is_known_reset=True) if reset is not None and reset > now else next_check)
    soonest = min(all_retry_times, key=lambda each_retry_time: each_retry_time.at, default=next_check)
    all_unreadable_names = [
        each_reading.account.name
        for each_reading in all_readings
        if each_reading.meters is None and each_reading.account not in all_spent_accounts
    ]
    is_every_account_unreadable = len(all_unreadable_names) == len(all_readings)
    return Decision("wait", None, soonest.at, _wait_reason(all_unreadable_names, is_every_account_unreadable, soonest), "wait")
