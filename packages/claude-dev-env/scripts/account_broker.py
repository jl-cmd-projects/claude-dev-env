#!/usr/bin/env python3
"""Choose and run Claude or Codex jobs through one account roster."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping, Sequence

import claude_account_choice
import claude_chain_runner
import codex_account_choice
import codex_account_meters
from claude_account_worker import extra_config_directories
from claude_chain_usage import AccountUsageMeters
from dev_env_scripts_constants.account_broker_constants import (
    CLAUDE_FLOORS,
    CODEX_FLOORS,
    WAIT_EXIT_CODE,
)
from dev_env_scripts_constants.claude_account_constants import (
    CREDENTIALS_FILE_NAME,
    FULL_PERCENT,
    MAIN_CLAUDE_HOME_DIRECTORY_NAME,
)
from dev_env_scripts_constants.claude_chain_constants import ALL_USAGE_LIMIT_SIGNATURES
from dev_env_scripts_constants.codex_account_constants import (
    CODEX_HOME_ENVIRONMENT_VARIABLE,
    WEEKLY_WINDOW_MINUTES,
)
from dev_env_scripts_constants.shared_tree_constants import CLAUDE_CONFIG_DIR_ENV_VAR


class Product(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"


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
        all_readings = (
            each_percent
            for each_percent in (self.session_percent_left, self.weekly_percent_left)
            if each_percent is not None
        )
        return min(all_readings, default=None)


@dataclass(frozen=True)
class Reading:
    account: Account
    meters: Meters | None


@dataclass(frozen=True)
class Decision:
    action: str
    account: Account | None
    reset_at: datetime | None
    reason: str
    tier: str | None


@dataclass
class Report:
    product: Product
    command: list[str]
    events: list[dict[str, object]] = field(default_factory=list)
    final_decision: Decision | None = None


MeterReader = Callable[[Account], Meters | None]
AccountLoader = Callable[[], Sequence[Account]]
CommandRunner = Callable[[Sequence[str], Mapping[str, str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class ProductAdapter:
    load_accounts: AccountLoader
    read_meters: MeterReader
    environment_variable: str
    usage_limit_signatures: tuple[str, ...]
    main_guard: bool


def _codex_usage_limit_signatures() -> tuple[str, ...]:
    constants_path = (
        Path(__file__).resolve().parent.parent
        / "_shared"
        / "pr-loop"
        / "scripts"
        / "codex_review_scripts_constants"
        / "classifier_constants.py"
    )
    specification = importlib.util.spec_from_file_location(
        "account_broker_codex_classifier_constants", constants_path
    )
    if specification is None or specification.loader is None:
        raise ImportError(f"Cannot import Codex usage markers from {constants_path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.ALL_USAGE_LIMIT_MARKERS


def load_claude_accounts() -> tuple[Account, ...]:
    main_home = Path.home() / MAIN_CLAUDE_HOME_DIRECTORY_NAME
    config_path = claude_chain_runner.chain_config_path()
    chain = claude_chain_runner.load_chain(config_path) if config_path.is_file() else []
    accounts = [Account(Product.CLAUDE, "main", main_home, True, "claude")]
    main_key = str(main_home.resolve()).casefold()
    seen_homes = {main_key}
    for entry in chain:
        home = (
            Path(entry.credentials_path).expanduser().parent
            if entry.credentials_path is not None
            else main_home
        )
        home_key = str(home.resolve()).casefold()
        if home_key == main_key:
            accounts[0] = Account(Product.CLAUDE, "main", main_home, True, entry.command)
        elif home_key not in seen_homes:
            accounts.append(Account(Product.CLAUDE, entry.command, home, command=entry.command))
            seen_homes.add(home_key)
    for home in extra_config_directories(main_home):
        home_key = str(home.resolve()).casefold()
        if home_key not in seen_homes:
            accounts.append(Account(Product.CLAUDE, home.name, home, command=home.name))
            seen_homes.add(home_key)
    return tuple(accounts)


def load_codex_accounts() -> tuple[Account, ...]:
    profiles_root = codex_account_choice.default_profiles_root()
    return tuple(
        Account(Product.CODEX, name, profiles_root / name)
        for name in codex_account_choice.codex_account_names(profiles_root)
    )


def read_claude_meters(account: Account) -> Meters | None:
    usage = claude_account_choice.read_account_meters(
        account.home / CREDENTIALS_FILE_NAME
    )
    if usage is None:
        return None
    return Meters(
        session_percent_left=(
            FULL_PERCENT - usage.session_utilization
            if usage.session_utilization is not None
            else None
        ),
        session_resets_at=usage.session_resets_at,
        weekly_percent_left=(
            FULL_PERCENT - usage.weekly_utilization
            if usage.weekly_utilization is not None
            else None
        ),
        weekly_resets_at=usage.weekly_resets_at,
    )


def read_codex_account_meters(account: Account) -> Meters | None:
    try:
        codex_path = codex_account_meters.resolve_codex_path(None)
        usage = codex_account_meters.read_codex_meters(codex_path, account.home)
    except (codex_account_meters.CodexMeterUnreadError, OSError):
        return None
    weekly_windows = [
        each_window
        for each_window in usage.all_windows
        if each_window.duration_minutes is None
        or each_window.duration_minutes >= WEEKLY_WINDOW_MINUTES
    ]
    weekly_window = (
        max(weekly_windows, key=lambda each_window: each_window.used_percent)
        if weekly_windows
        else None
    )
    short_windows = [
        each_window
        for each_window in usage.all_windows
        if each_window.duration_minutes is not None
        and each_window.duration_minutes < WEEKLY_WINDOW_MINUTES
    ]
    short_window = (
        max(short_windows, key=lambda each_window: each_window.used_percent)
        if short_windows
        else None
    )
    return Meters(
        session_percent_left=usage.short_window_percent_left,
        session_resets_at=short_window.resets_at if short_window else None,
        weekly_percent_left=(
            FULL_PERCENT - weekly_window.used_percent if weekly_window else None
        ),
        weekly_resets_at=weekly_window.resets_at if weekly_window else None,
    )


ADAPTERS = {
    Product.CLAUDE: ProductAdapter(
        load_accounts=load_claude_accounts,
        read_meters=read_claude_meters,
        environment_variable=CLAUDE_CONFIG_DIR_ENV_VAR,
        usage_limit_signatures=ALL_USAGE_LIMIT_SIGNATURES,
        main_guard=True,
    ),
    Product.CODEX: ProductAdapter(
        load_accounts=load_codex_accounts,
        read_meters=read_codex_account_meters,
        environment_variable=CODEX_HOME_ENVIRONMENT_VARIABLE,
        usage_limit_signatures=_codex_usage_limit_signatures(),
        main_guard=False,
    ),
}


def read_accounts(product: Product, adapter: ProductAdapter | None = None) -> tuple[Reading, ...]:
    active_adapter = adapter or ADAPTERS[product]
    return tuple(
        Reading(account, active_adapter.read_meters(account))
        for account in active_adapter.load_accounts()
    )


def _claude_main_reason(meters: Meters | None, now: datetime) -> str | None:
    if meters is None:
        return None
    usage = AccountUsageMeters(
        session_utilization=(
            FULL_PERCENT - meters.session_percent_left
            if meters.session_percent_left is not None
            else None
        ),
        session_resets_at=meters.session_resets_at,
        weekly_utilization=(
            FULL_PERCENT - meters.weekly_percent_left
            if meters.weekly_percent_left is not None
            else None
        ),
        weekly_resets_at=meters.weekly_resets_at,
    )
    return claude_account_choice._main_spendable_reason(usage, now)


def _rank_key(reading: Reading) -> tuple[bool, float]:
    room = reading.meters.tightest_percent_left if reading.meters else None
    return room is None, -(room if room is not None else 0.0)


def _claude_extra_tier(meters: Meters | None) -> str | None:
    if meters is None or meters.tightest_percent_left is None:
        return "normal"
    if (
        meters.weekly_percent_left is not None
        and meters.weekly_percent_left <= FULL_PERCENT - CLAUDE_FLOORS["extra_weekly_used_ceiling"]
    ) or (
        meters.session_percent_left is not None
        and meters.session_percent_left <= FULL_PERCENT - CLAUDE_FLOORS["extra_session_used_ceiling"]
    ):
        return None
    return "normal"


def _codex_tier(meters: Meters | None) -> str | None:
    if meters is None or meters.tightest_percent_left is None:
        return None
    if meters.tightest_percent_left > CODEX_FLOORS["normal_minimum_left"]:
        return "normal"
    if (
        meters.tightest_percent_left > CODEX_FLOORS["luna_stop_left"]
        and (
            meters.session_percent_left is None
            or meters.session_percent_left >= CODEX_FLOORS["luna_short_minimum_left"]
        )
    ):
        return "luna"
    return None


def _account_reset(reading: Reading, spent: bool = False) -> datetime | None:
    meters = reading.meters
    if meters is None:
        return None
    if spent:
        all_resets = [
            reset
            for reset in (meters.session_resets_at, meters.weekly_resets_at)
            if reset is not None
        ]
        return min(all_resets, default=None)
    if reading.account.product is Product.CLAUDE:
        if reading.account.is_main:
            return meters.weekly_resets_at
        blocking = (
            (
                meters.session_percent_left,
                FULL_PERCENT - CLAUDE_FLOORS["extra_session_used_ceiling"],
                meters.session_resets_at,
            ),
            (
                meters.weekly_percent_left,
                FULL_PERCENT - CLAUDE_FLOORS["extra_weekly_used_ceiling"],
                meters.weekly_resets_at,
            ),
        )
    else:
        blocking = (
            (
                meters.session_percent_left,
                CODEX_FLOORS["luna_short_minimum_left"],
                meters.session_resets_at,
            ),
            (
                meters.weekly_percent_left,
                CODEX_FLOORS["luna_stop_left"],
                meters.weekly_resets_at,
            ),
        )
    all_resets = [
        reset
        for room, floor, reset in blocking
        if room is not None and room <= floor and reset is not None
    ]
    return max(all_resets, default=None)


def choose_from_readings(
    product: Product,
    readings: Sequence[Reading],
    *,
    now: datetime,
    spent_accounts: frozenset[Account] = frozenset(),
    preferred_command: str | None = None,
    adapter: ProductAdapter | None = None,
) -> Decision:
    active_adapter = adapter or ADAPTERS[product]
    available = [
        reading for reading in readings if reading.account not in spent_accounts
    ]
    if product is Product.CLAUDE:
        if preferred_command is not None:
            for reading in available:
                if reading.account.command == preferred_command:
                    return Decision("run", reading.account, None, "resume affinity", "normal")
        main = next((reading for reading in available if reading.account.is_main), None)
        main_reason = (
            _claude_main_reason(main.meters, now)
            if main is not None and active_adapter.main_guard
            else None
        )
        if main is not None and main_reason is not None:
            return Decision("run", main.account, None, main_reason, "normal")
        candidates = sorted(
            (reading for reading in available if not reading.account.is_main),
            key=_rank_key,
        )
        for reading in candidates:
            tier = _claude_extra_tier(reading.meters)
            if tier is not None:
                reason = (
                    f"{reading.account.name} has unread meters"
                    if reading.meters is None
                    or reading.meters.tightest_percent_left is None
                    else f"{reading.account.name} has {reading.meters.tightest_percent_left:g}% left"
                )
                return Decision("run", reading.account, None, reason, tier)
    else:
        candidates = sorted(available, key=_rank_key)
        for tier in ("normal", "luna"):
            for reading in candidates:
                if _codex_tier(reading.meters) == tier:
                    return Decision(
                        "run",
                        reading.account,
                        None,
                        f"{reading.account.name} has {reading.meters.tightest_percent_left:g}% left",
                        tier,
                    )
    all_resets = [
        reset
        for reading in readings
        if (reset := _account_reset(reading, reading.account in spent_accounts)) is not None
    ]
    next_reset = min(all_resets, default=None)
    reset_text = next_reset.isoformat() if next_reset else "an unknown time"
    return Decision("wait", None, next_reset, f"no account has room; next reset at {reset_text}", "wait")


def _time_text(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def decision_payload(decision: Decision) -> dict[str, object]:
    return {
        "action": decision.action,
        "account": decision.account.name if decision.account else None,
        "home": str(decision.account.home) if decision.account else None,
        "reset_at": _time_text(decision.reset_at),
        "reason": decision.reason,
        "tier": decision.tier,
    }


def readings_payload(readings: Sequence[Reading]) -> list[dict[str, object]]:
    return [
        {
            "account": reading.account.name,
            "home": str(reading.account.home),
            "main": reading.account.is_main,
            "meters": {
                "session_percent_left": reading.meters.session_percent_left,
                "session_resets_at": _time_text(reading.meters.session_resets_at),
                "weekly_percent_left": reading.meters.weekly_percent_left,
                "weekly_resets_at": _time_text(reading.meters.weekly_resets_at),
            }
            if reading.meters
            else None,
        }
        for reading in readings
    ]


def _run_command(
    command: Sequence[str], environment: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        env=dict(environment),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _preferred_claude_command(command: Sequence[str], readings: Sequence[Reading]) -> str | None:
    session_id = claude_chain_runner.extract_resume_session_id(command)
    if session_id is None:
        return None
    main = next((reading for reading in readings if reading.account.is_main), None)
    if main is None:
        return None
    affinity_path = claude_chain_runner.default_affinity_state_path(main.account.home)
    try:
        store = claude_chain_runner.load_affinity_store(affinity_path)
    except ValueError:
        return None
    return claude_chain_runner.lookup_affinity_command(store, session_id)


def _save_claude_affinity(
    account: Account, stdout: str, readings: Sequence[Reading]
) -> None:
    session_id = claude_chain_runner.extract_session_id_from_stdout(stdout)
    main = next((reading for reading in readings if reading.account.is_main), None)
    if session_id is None or main is None:
        return
    affinity_path = claude_chain_runner.default_affinity_state_path(main.account.home)
    try:
        store = claude_chain_runner.load_affinity_store(affinity_path)
        updated = claude_chain_runner.record_affinity_binding(
            store, session_id=session_id, command=account.command or account.name
        )
        claude_chain_runner.save_affinity_store_atomic(affinity_path, updated)
    except (OSError, ValueError):
        return


def _write_report(path: Path, report: Report) -> None:
    payload = {
        "product": report.product.value,
        "command": report.command,
        "events": report.events,
        "final_decision": decision_payload(report.final_decision)
        if report.final_decision
        else None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def run_job(
    product: Product,
    command: Sequence[str],
    report_path: Path,
    *,
    adapter: ProductAdapter | None = None,
    runner: CommandRunner = _run_command,
    now: datetime | None = None,
) -> int:
    active_adapter = adapter or ADAPTERS[product]
    readings = read_accounts(product, active_adapter)
    report = Report(product, list(command))
    spent: set[Account] = set()
    preferred = (
        _preferred_claude_command(command, readings)
        if product is Product.CLAUDE
        else None
    )
    instant = now or datetime.now().astimezone()
    while True:
        decision = choose_from_readings(
            product,
            readings,
            now=instant,
            spent_accounts=frozenset(spent),
            preferred_command=preferred,
            adapter=active_adapter,
        )
        report.events.append({"type": "pick", "decision": decision_payload(decision)})
        if decision.account is None:
            report.final_decision = decision
            _write_report(report_path, report)
            return WAIT_EXIT_CODE
        environment = {**os.environ, active_adapter.environment_variable: str(decision.account.home)}
        try:
            completion = runner(command, environment)
        except FileNotFoundError:
            report.events.append(
                {"type": "attempt", "account": decision.account.name, "exit_code": 127}
            )
            report.final_decision = decision
            _write_report(report_path, report)
            return 127
        report.events.append(
            {
                "type": "attempt",
                "account": decision.account.name,
                "exit_code": completion.returncode,
            }
        )
        combined_text = f"{completion.stdout}{completion.stderr}".casefold()
        is_usage_limit = completion.returncode != 0 and any(
            signature.casefold() in combined_text
            for signature in active_adapter.usage_limit_signatures
        )
        if is_usage_limit:
            spent.add(decision.account)
            account_reading = next(
                reading for reading in readings if reading.account == decision.account
            )
            report.events.append(
                {
                    "type": "usage_limit",
                    "account": decision.account.name,
                    "reset_at": _time_text(_account_reset(account_reading, spent=True)),
                }
            )
            continue
        report.final_decision = decision
        _write_report(report_path, report)
        if product is Product.CLAUDE and completion.returncode == 0:
            _save_claude_affinity(decision.account, completion.stdout, readings)
        sys.stdout.write(completion.stdout)
        sys.stderr.write(completion.stderr)
        return completion.returncode


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("choose", "check", "run"):
        command_parser = commands.add_parser(action)
        command_parser.add_argument("--product", choices=[p.value for p in Product], required=True)
        if action == "run":
            command_parser.add_argument("--report", type=Path, required=True)
            command_parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parser = _parser()
    parsed = parser.parse_args(arguments)
    product = Product(parsed.product)
    if parsed.action == "run":
        command = list(parsed.command)
        if command and command[0] == "--":
            command.pop(0)
        if not command:
            parser.error("run needs a command after --")
        return run_job(product, command, parsed.report)
    readings = read_accounts(product)
    decision = choose_from_readings(
        product, readings, now=datetime.now().astimezone()
    )
    if parsed.action == "choose":
        print(json.dumps({"decision": decision_payload(decision), "accounts": readings_payload(readings)}))
    return WAIT_EXIT_CODE if decision.action == "wait" else 0


if __name__ == "__main__":
    raise SystemExit(main())
