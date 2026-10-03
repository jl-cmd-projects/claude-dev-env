"""Ask the account broker for a Codex account before an Astra advisor request."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from advisor_scripts_constants.astra_advisor_constants import (
    ACCOUNT_BROKER_CHOOSE_COMMAND,
    ASTRA_ACCOUNT_PICK_TIMEOUT_REASON,
    ALL_BROKER_ACCEPTED_EXIT_CODES,
    ALL_BROKER_METER_PERCENT_KEYS,
    ASTRA_ACCOUNT_PICK_TIMEOUT_SECONDS,
    BROKER_WAIT_EXIT_CODE,
    ASTRA_FALLBACK_KIND_BROKEN,
    ASTRA_FALLBACK_KIND_DECLINED,
    ASTRA_PREFLIGHT_FAILURE_REASON,
    CODEX_TIER_NORMAL,
)


@dataclass(frozen=True)
class AstraPreflight:
    eligible: bool
    percent_left: float | None
    reason: str
    fallback_kind: str | None = None
    codex_home: Path | None = None


def _preflight_fallback(
    reason: str, percent_left: float | None, fallback_kind: str
) -> AstraPreflight:
    return AstraPreflight(False, percent_left, reason, fallback_kind)


def _broken(detail: str) -> AstraPreflight:
    return _preflight_fallback(
        f"{ASTRA_PREFLIGHT_FAILURE_REASON}: {detail}", None, ASTRA_FALLBACK_KIND_BROKEN
    )


def _finite_percent(raw_percent: object) -> float | None:
    if isinstance(raw_percent, bool) or not isinstance(raw_percent, (int, float)):
        return None
    return float(raw_percent) if math.isfinite(raw_percent) else None


def _preflight_from_answer(field_by_name: dict[str, object]) -> AstraPreflight:
    decision = field_by_name.get("decision")
    if not isinstance(decision, dict) or not isinstance(decision.get("tier"), str):
        return _broken("broker answer is malformed")
    if decision["tier"] != CODEX_TIER_NORMAL:
        reason = f"{ASTRA_PREFLIGHT_FAILURE_REASON}: no Codex account has room ({decision.get('reason')})"
        return _preflight_fallback(reason, None, ASTRA_FALLBACK_KIND_DECLINED)
    codex_home = decision.get("home")
    account = decision.get("account")
    accounts = field_by_name.get("accounts")
    if not isinstance(codex_home, str) or not codex_home or not isinstance(account, str) or not isinstance(accounts, list):
        return _broken("broker answer names no Codex home with room")
    chosen = next(
        (
            entry
            for entry in accounts
            if isinstance(entry, dict)
            and entry.get("name") == account
            and entry.get("home") == codex_home
        ),
        None,
    )
    meters = chosen.get("meters") if isinstance(chosen, dict) else None
    if not isinstance(meters, dict):
        return _broken("broker answer names no Codex home with room")
    all_percent_left = [
        percent
        for key in ALL_BROKER_METER_PERCENT_KEYS
        if (percent := _finite_percent(meters.get(key))) is not None
    ]
    if not all_percent_left:
        return _broken("broker answer names no Codex home with room")
    percent_left = min(all_percent_left)
    reason = decision.get("reason")
    if not isinstance(reason, str):
        return _broken("broker answer is malformed")
    return AstraPreflight(True, percent_left, reason, codex_home=Path(codex_home))


def _run_broker(
    broker_path: Path,
    process_runner: Callable[..., subprocess.CompletedProcess[str]],
) -> subprocess.CompletedProcess[str]:
    return process_runner(
        [sys.executable, str(broker_path), ACCOUNT_BROKER_CHOOSE_COMMAND, "--product", "codex"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=ASTRA_ACCOUNT_PICK_TIMEOUT_SECONDS,
    )


def _preflight_from_broker(completed: subprocess.CompletedProcess[str]) -> AstraPreflight:
    if completed.returncode not in ALL_BROKER_ACCEPTED_EXIT_CODES:
        return _broken(f"broker exit {completed.returncode}")
    try:
        answer = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        return _broken("broker answer is malformed")
    if not isinstance(answer, dict):
        return _broken("broker answer is malformed")
    if completed.returncode == BROKER_WAIT_EXIT_CODE:
        decision = answer.get("decision")
        if not isinstance(decision, dict) or not isinstance(decision.get("tier"), str):
            return _broken("broker answer is malformed")
        reason = f"{ASTRA_PREFLIGHT_FAILURE_REASON}: no Codex account has room ({decision.get('reason')})"
        return _preflight_fallback(reason, None, ASTRA_FALLBACK_KIND_DECLINED)
    return _preflight_from_answer(answer)


def run_astra_preflight(
    broker_path: Path,
    process_runner: Callable[..., subprocess.CompletedProcess[str]],
) -> AstraPreflight:
    """Run the Codex account broker and decide whether Astra may bind.

    Args:
        broker_path: Path to ``account_broker.py``.
        process_runner: Callable that runs the broker.

    Returns:
        Eligibility, the chosen account's percent left and Codex home, reason, and fallback kind.
    """
    try:
        return _preflight_from_broker(_run_broker(broker_path, process_runner))
    except subprocess.TimeoutExpired as error:
        return _preflight_fallback(
            f"{ASTRA_ACCOUNT_PICK_TIMEOUT_REASON}: {error}", None, ASTRA_FALLBACK_KIND_BROKEN
        )
    except (OSError, subprocess.SubprocessError, TypeError, ValueError) as error:
        return _broken(str(error))
