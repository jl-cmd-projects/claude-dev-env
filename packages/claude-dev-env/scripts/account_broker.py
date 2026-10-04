#!/usr/bin/env python3
"""Choose and run Claude or Codex jobs through one account roster."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

import account_broker_support as support
import codex_account_meters
from account_broker_support import (
    all_product_adapters,
    Account,
    BrokerConfigurationError,
    Decision,
    JobOutcome,
    Meters,
    Product,
    ProductAdapter,
    Reading,
    Report,
    _load_state,
    _meter_payload,
    _resume_id,
    _save_state,
    _state_key,
    broker_state_path,
    extract_session_id_from_stdout,
    load_claude_accounts,
    load_codex_accounts,
    override_subprocess_runner,
    read_accounts,
    read_claude_meters,
    read_codex_account_meters,
)
from dev_env_scripts_constants.account_broker_constants import (
    _account_reset,
    _choose_claude,
    _choose_codex,
    _wait_decision,
    COMMAND_MISSING_EXIT_CODE,
    REPORT_INDENT_SPACES,
    WAIT_EXIT_CODE,
    utc_time_text as _time_text,
)
from dev_env_scripts_constants.codex_account_constants import (
    CODEX_HOME_ENVIRONMENT_VARIABLE,
    MAIN_CODEX_HOME_DIRECTORY_NAME,
    NO_ROSTER_ACCOUNT_NAME,
    TIER_NORMAL,
)


def choose_from_readings(
    product: Product,
    all_readings: Sequence[Reading],
    *,
    now: datetime,
    all_spent_accounts: frozenset[Account] = frozenset(),
    preferred_command: str | None = None,
    adapter: ProductAdapter | None = None,
    all_spent_resets: Mapping[Account, datetime] | None = None,
) -> Decision:
    """Choose an account or a wait.

    Args:
        product: Account product.
        all_readings: Roster and meter readings.

    Returns:
        A run or wait decision.
    """
    if product is Product.CODEX and not all_readings:
        home = Path(os.environ.get(CODEX_HOME_ENVIRONMENT_VARIABLE) or Path.home() / MAIN_CODEX_HOME_DIRECTORY_NAME).resolve()
        return Decision("run", Account(product, NO_ROSTER_ACCOUNT_NAME, home, True), None, "no roster is configured", TIER_NORMAL)
    active = adapter or all_product_adapters[product]
    all_available = [each_reading for each_reading in all_readings if each_reading.account not in all_spent_accounts]
    selected = (
        _choose_claude(all_available, now, preferred_command, active.main_guard)
        if product is Product.CLAUDE
        else _choose_codex(all_available)
    )
    return selected or _wait_decision(all_readings, now, all_spent_accounts, all_spent_resets or {})


def decision_payload(decision: Decision) -> dict[str, object]:
    """Serialize a choice.

    Args:
        decision: Account choice.

    Returns:
        JSON-compatible decision fields.
    """
    return {
        "action": decision.action,
        "account": decision.account.name if decision.account else None,
        "home": str(decision.account.home) if decision.account else None,
        "reason": decision.reason,
        "tier": decision.tier,
        "resets_at": _time_text(decision.resets_at),
    }


def readings_payload(all_readings: Sequence[Reading]) -> list[dict[str, object]]:
    """Serialize account readings.

    Args:
        all_readings: Roster and meters.

    Returns:
        JSON-compatible account entries.
    """
    return [
        {
            "name": each_reading.account.name,
            "home": str(each_reading.account.home),
            "is_main": each_reading.account.is_main,
            "meters": _meter_payload(each_reading.meters),
        }
        for each_reading in all_readings
    ]


def _stored_reset(raw: object, now: datetime) -> datetime | None:
    if not isinstance(raw, (int, float)) or raw <= now.timestamp():
        return None
    try:
        return datetime.fromtimestamp(raw, timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def _spent_for_readings(all_readings: Sequence[Reading], all_state: dict[str, object], now: datetime) -> tuple[frozenset[Account], dict[Account, datetime]]:
    marks = all_state["spent"]
    spent = {}
    for each_reading in all_readings:
        reset = _stored_reset(marks.get(_state_key(each_reading.account)), now)
        if reset is not None:
            spent[each_reading.account] = reset
    return frozenset(spent), spent


def _mark_spent(all_state: dict[str, object], reading: Reading, now: datetime, reset: datetime | None = None) -> datetime:
    until = reset or _account_reset(reading, is_spent=True) or now + timedelta(hours=1)
    if until <= now:
        until = now + timedelta(hours=1)
    all_state["spent"][_state_key(reading.account)] = until.timestamp()
    _save_state(broker_state_path(), all_state)
    return until


def _outside_roster_resets(product: Product, all_readings: Sequence[Reading], all_state: Mapping[str, object], now: datetime) -> dict[str, datetime]:
    marks = all_state.get("spent") if isinstance(all_state.get("spent"), dict) else {}
    all_roster_names = {each_reading.account.name for each_reading in all_readings}
    prefix = f"{product.value}:"
    placeholder_suffix = f":{Path()}"
    all_resets_by_name = {}
    for each_key, each_raw in marks.items():
        if not (isinstance(each_key, str) and each_key.startswith(prefix) and each_key.endswith(placeholder_suffix)):
            continue
        name = each_key[len(prefix):-len(placeholder_suffix)]
        reset = _stored_reset(each_raw, now)
        if name not in all_roster_names and reset is not None:
            all_resets_by_name[name] = reset
    return all_resets_by_name


def _with_outside_spent_marks(decision: Decision, all_outside_resets_by_name: Mapping[str, datetime]) -> Decision:
    if not all_outside_resets_by_name:
        return decision
    outside_name, outside_reset = min(all_outside_resets_by_name.items(), key=lambda each_item: each_item[1])
    if decision.action != "wait":
        return Decision("wait", None, outside_reset, f"account {outside_name} outside the roster is spent; next reset at {_time_text(outside_reset)}", "wait")
    if decision.resets_at is not None and decision.resets_at <= outside_reset:
        return decision
    return Decision("wait", None, outside_reset, f"no account has room; next reset at {_time_text(outside_reset)}", "wait")


def _write_report(path: Path, report: Report) -> None:
    payload = {
        "product": report.product.value,
        "command": report.command,
        "events": report.events,
        "final_decision": decision_payload(report.final_decision) if report.final_decision else None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=REPORT_INDENT_SPACES) + "\n", encoding="utf-8", newline="\n")


@dataclass
class _RunContext:
    product: Product
    all_argv: list[str]
    active: ProductAdapter
    now: datetime
    all_state: dict[str, object]
    all_readings: tuple[Reading, ...]
    report: Report
    stdin_bytes: bytes | None
    timeout_seconds: float | None
    cwd: str | Path | None
    encoding: str
    errors: str
    preferred_command: str | None
    all_attempts: list[tuple[str, str]]
    all_spent_accounts: set[Account]
    all_spent_resets: dict[Account, datetime]


def _prepare_run(
    product: Product, all_argv: Sequence[str], now: datetime, timeout_seconds: float | None,
    stdin_text: str | bytes | None, cwd: str | Path | None, encoding: str, errors: str
) -> _RunContext:
    all_state = _load_state(broker_state_path())
    active = all_product_adapters[product]
    all_readings = read_accounts(product, active, all_state=all_state, now=now)
    session_id = _resume_id(all_argv) if product is Product.CLAUDE else None
    preferred = all_state["affinity"].get(session_id) if session_id else None
    spent, all_spent_resets = _spent_for_readings(all_readings, all_state, now)
    stdin_bytes = stdin_text.encode(encoding, errors) if isinstance(stdin_text, str) else stdin_text
    return _RunContext(
        product, list(all_argv), active, now, all_state, all_readings, Report(product, list(all_argv)),
        stdin_bytes, timeout_seconds, cwd, encoding, errors, preferred, [], set(spent), all_spent_resets
    )


def _wait_outcome(context: _RunContext, decision: Decision) -> JobOutcome:
    context.report.final_decision = decision
    status = "exhausted" if context.all_attempts else "wait"
    return JobOutcome(WAIT_EXIT_CODE, "", "", None, tuple(context.all_attempts), status, None, decision.resets_at)


def _record_spent_attempt(context: _RunContext, account: Account, status: str, returncode: int | None) -> None:
    context.all_attempts.append((account.name, status))
    context.report.events.append({"type": "attempt", "account": account.name, "status": status, "exit_code": returncode})
    if context.all_readings:
        reading = next(each_reading for each_reading in context.all_readings if each_reading.account == account)
        context.all_spent_accounts.add(account)
        if status == "usage_limited":
            context.all_spent_resets[account] = _mark_spent(context.all_state, reading, context.now)


def _invoke(context: _RunContext, account: Account) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, context.active.environment_variable: str(account.home)}
    return support.subprocess_runner(
        context.all_argv,
        env=environment,
        input=context.stdin_bytes,
        timeout=context.timeout_seconds,
        cwd=str(context.cwd) if context.cwd is not None else None,
        encoding=context.encoding,
        errors=context.errors,
    )


def _finish_attempt(context: _RunContext, decision: Decision, completion: subprocess.CompletedProcess[str]) -> JobOutcome:
    account = decision.account
    status = "advisor_blocked" if context.product is Product.CLAUDE and completion.returncode != 0 else "served"
    context.all_attempts.append((account.name, status))
    context.report.events.append({"type": "attempt", "account": account.name, "status": status, "exit_code": completion.returncode})
    context.report.final_decision = decision
    session_id = extract_session_id_from_stdout(completion.stdout) if completion.returncode == 0 else None
    if context.product is Product.CLAUDE and session_id:
        context.all_state["affinity"][session_id] = account.command or account.name
        _save_state(broker_state_path(), context.all_state)
    return JobOutcome(completion.returncode, completion.stdout, completion.stderr, account.name, tuple(context.all_attempts), status, session_id, None)


def _attempt_once(context: _RunContext, decision: Decision) -> JobOutcome | None:
    account = decision.account
    try:
        completion = _invoke(context, account)
    except (OSError, subprocess.TimeoutExpired) as error:
        status = "timeout" if isinstance(error, subprocess.TimeoutExpired) else "start_failed"
        _record_spent_attempt(context, account, status, COMMAND_MISSING_EXIT_CODE)
        if isinstance(error, subprocess.TimeoutExpired) or not context.all_readings:
            context.report.final_decision = decision
            final_status = "advisor_blocked" if context.product is Product.CLAUDE else status
            return JobOutcome(COMMAND_MISSING_EXIT_CODE, "", str(error), account.name, tuple(context.all_attempts), final_status, None, None)
        return None
    combined = f"{completion.stdout}{completion.stderr}".casefold()
    is_limited = completion.returncode != 0 and any(
        signature.casefold() in combined for signature in context.active.usage_limit_signatures
    )
    if is_limited:
        _record_spent_attempt(context, account, "usage_limited", completion.returncode)
        if not context.all_readings:
            waiting = Decision("wait", None, context.now + timedelta(hours=1), "no account has room", "wait")
            return _wait_outcome(context, waiting)
        return None
    return _finish_attempt(context, decision, completion)


def _execute(
    product: Product, all_argv: Sequence[str], *, now: datetime,
    timeout_seconds: float | None = None, stdin_text: str | bytes | None = None,
    cwd: str | Path | None = None, encoding: str = "utf-8", errors: str = "replace"
) -> tuple[JobOutcome, Report]:
    context = _prepare_run(product, all_argv, now, timeout_seconds, stdin_text, cwd, encoding, errors)
    while True:
        picked = choose_from_readings(product, context.all_readings, now=now, all_spent_accounts=frozenset(context.all_spent_accounts), preferred_command=context.preferred_command, adapter=context.active, all_spent_resets=context.all_spent_resets)
        decision = _with_outside_spent_marks(picked, _outside_roster_resets(product, context.all_readings, context.all_state, now))
        context.report.events.append({"type": "pick", "decision": decision_payload(decision)})
        if decision.account is None:
            return _wait_outcome(context, decision), context.report
        outcome = _attempt_once(context, decision)
        if outcome is not None:
            return outcome, context.report


def run_job(
    product: Product,
    all_argv: Sequence[str],
    *,
    timeout_seconds: float | None = None,
    stdin_text: str | bytes | None = None,
    cwd: str | Path | None = None,
    encoding: str = "utf-8",
    errors: str = "replace",
) -> JobOutcome:
    return _execute(product, all_argv, now=datetime.now(timezone.utc), timeout_seconds=timeout_seconds, stdin_text=stdin_text, cwd=cwd, encoding=encoding, errors=errors)[0]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for each_action in ("choose", "check", "accounts", "limits", "run"):
        command = commands.add_parser(each_action)
        all_product_choices = [Product.CODEX.value] if each_action == "limits" else [each_product.value for each_product in Product]
        command.add_argument("--product", choices=all_product_choices, required=True)
        if each_action == "choose":
            command.add_argument("--spent", action="append", default=[])
        if each_action == "limits":
            command.add_argument("--home", type=Path, required=True)
            command.add_argument("--codex", type=Path)
        if each_action == "run":
            command.add_argument("--report", type=Path, required=True)
            command.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def _parse_spent_mark(all_accounts_by_name: Mapping[str, Reading], mark: str, product: Product) -> tuple[Reading, datetime | None]:
    name, separator, reset_text = mark.partition(":")
    if not name:
        raise BrokerConfigurationError(f"spent mark {mark!r} needs an account name")
    try:
        reset = datetime.fromtimestamp(float(reset_text), timezone.utc) if separator else None
    except (ValueError, OSError, OverflowError) as error:
        raise BrokerConfigurationError(f"invalid reset for account {name}") from error
    reading = all_accounts_by_name.get(name)
    if reading is None:
        if all_accounts_by_name or name != NO_ROSTER_ACCOUNT_NAME:
            print(f"warning: spent mark names {name}, an account outside the roster; choose waits until its reset", file=sys.stderr)
        return Reading(Account(product, name, Path(), False), None), reset
    return reading, reset


def _save_spent_arguments(all_marks: Sequence[str], all_readings: Sequence[Reading], all_state: dict[str, object], now: datetime, product: Product) -> None:
    all_accounts_by_name = {each_reading.account.name: each_reading for each_reading in all_readings}
    for each_mark in all_marks:
        reading, reset = _parse_spent_mark(all_accounts_by_name, each_mark, product)
        _mark_spent(all_state, reading, now, reset)


def _accounts_cli(product: Product) -> int:
    roster = all_product_adapters[product].load_accounts()
    print(json.dumps({"accounts": [{"name": each_account.name, "home": str(each_account.home), "is_main": each_account.is_main} for each_account in roster]}))
    return 0


def _limits_cli(parsed: argparse.Namespace) -> int:
    try:
        rate_limit_records = codex_account_meters.read_rate_limit_records(
            codex_account_meters.resolve_codex_path(parsed.codex), parsed.home
        )
    except (codex_account_meters.CodexMeterUnreadError, OSError) as error:
        raise BrokerConfigurationError(str(error)) from error
    print(json.dumps({"home": str(parsed.home), "rate_limits": rate_limit_records}))
    return 0


def _run_cli(product: Product, parsed: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    command = list(parsed.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        parser.error("run needs a command after --")
    stdin_bytes = sys.stdin.buffer.read()
    outcome, report = _execute(product, command, stdin_text=stdin_bytes, now=datetime.now(timezone.utc))
    _write_report(parsed.report, report)
    sys.stdout.write(outcome.stdout)
    sys.stderr.write(outcome.stderr)
    return 4 if outcome.status == "advisor_blocked" else outcome.returncode


def _choose_cli(product: Product, parsed: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    all_state = _load_state(broker_state_path())
    all_readings = read_accounts(product, all_state=all_state, now=now)
    if parsed.action == "choose" and parsed.spent:
        _save_spent_arguments(parsed.spent, all_readings, all_state, now, product)
    spent, resets = _spent_for_readings(all_readings, all_state, now)
    decision = choose_from_readings(product, all_readings, now=now, all_spent_accounts=spent, all_spent_resets=resets)
    decision = _with_outside_spent_marks(decision, _outside_roster_resets(product, all_readings, all_state, now))
    if parsed.action == "choose":
        print(json.dumps({"decision": decision_payload(decision), "accounts": readings_payload(all_readings), "state_path": str(broker_state_path())}))
    return WAIT_EXIT_CODE if decision.action == "wait" else 0


def main(all_arguments: Sequence[str]) -> int:
    """Execute a broker command.

    Args:
        all_arguments: Command-line tokens.

    Returns:
        Process exit code.
    """
    parser = _parser()
    parsed = parser.parse_args(all_arguments)
    product = Product(parsed.product)
    try:
        if parsed.action == "accounts":
            return _accounts_cli(product)
        if parsed.action == "limits":
            return _limits_cli(parsed)
        if parsed.action == "run":
            return _run_cli(product, parsed, parser)
        return _choose_cli(product, parsed)
    except BrokerConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
