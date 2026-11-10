"""Ask the account broker for a Codex account before an Astra advisor request.

::

    no home exported, or a blank one          ->  choose --product codex --require-tier normal
    paid home exported, whatever its room     ->  choose --product codex --home <home>, runs on that home
    free, unknown, unlisted or unreadable
        home exported                         ->  declined, nothing launches

An exported home keeps its account, in the roster or not, on the ``normal`` or
``luna`` tier, once the broker confirms its plan, whatever its room. The broker's
reason names the account.
"""

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
    ACCOUNT_BROKER_HOME_FLAG,
    ALL_ACCOUNT_BROKER_REQUIRE_TIER_ARGUMENTS,
    ASTRA_ACCOUNT_PICK_TIMEOUT_REASON,
    ALL_ASTRA_EXPORTED_HOME_TIERS,
    ALL_ASTRA_NORMAL_ONLY_TIERS,
    ALL_BROKER_ACCEPTED_EXIT_CODES,
    ALL_BROKER_METER_PERCENT_KEYS,
    ASTRA_ACCOUNT_PICK_TIMEOUT_SECONDS,
    ASTRA_EXPORTED_HOME_REFUSED_REASON_TEMPLATE,
    BROKER_WAIT_EXIT_CODE,
    ASTRA_FALLBACK_KIND_BROKEN,
    ASTRA_FALLBACK_KIND_DECLINED,
    ASTRA_PREFLIGHT_FAILURE_REASON,
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


def _accepted_tiers(exported_home: str | None) -> tuple[str, ...]:
    if exported_home is None:
        return ALL_ASTRA_NORMAL_ONLY_TIERS
    return ALL_ASTRA_EXPORTED_HOME_TIERS


def _declined(broker_reason: object, exported_home: str | None) -> AstraPreflight:
    if exported_home is None:
        reason = f"{ASTRA_PREFLIGHT_FAILURE_REASON}: no Codex account has room ({broker_reason})"
    else:
        reason = ASTRA_EXPORTED_HOME_REFUSED_REASON_TEMPLATE.format(
            home=exported_home, reason=broker_reason
        )
    return _preflight_fallback(reason, None, ASTRA_FALLBACK_KIND_DECLINED)


def _preflight_from_answer(
    field_by_name: dict[str, object], exported_home: str | None
) -> AstraPreflight:
    decision = field_by_name.get("decision")
    if not isinstance(decision, dict) or not isinstance(decision.get("tier"), str):
        return _broken("broker answer is malformed")
    if decision["tier"] not in _accepted_tiers(exported_home):
        return _declined(decision.get("reason"), exported_home)
    codex_home = decision.get("home")
    account = decision.get("account")
    accounts = field_by_name.get("accounts")
    reason = decision.get("reason")
    if not isinstance(codex_home, str) or not codex_home or not isinstance(account, str) or not isinstance(accounts, list):
        return _broken("broker answer names no Codex home with room")
    if not isinstance(reason, str):
        return _broken("broker answer is malformed")
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
    return AstraPreflight(True, min(all_percent_left), reason, codex_home=Path(codex_home))


def _broker_selection_arguments(exported_home: str | None) -> tuple[str, ...]:
    if exported_home is None:
        return ALL_ACCOUNT_BROKER_REQUIRE_TIER_ARGUMENTS
    return (ACCOUNT_BROKER_HOME_FLAG, exported_home)


def _run_broker(
    broker_path: Path,
    process_runner: Callable[..., subprocess.CompletedProcess[str]],
    exported_home: str | None,
) -> subprocess.CompletedProcess[str]:
    return process_runner(
        [
            sys.executable,
            str(broker_path),
            ACCOUNT_BROKER_CHOOSE_COMMAND,
            "--product",
            "codex",
            *_broker_selection_arguments(exported_home),
        ],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=ASTRA_ACCOUNT_PICK_TIMEOUT_SECONDS,
    )


def _preflight_from_broker(
    completed: subprocess.CompletedProcess[str], exported_home: str | None
) -> AstraPreflight:
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
        return _declined(decision.get("reason"), exported_home)
    return _preflight_from_answer(answer, exported_home)


def run_astra_preflight(
    broker_path: Path,
    process_runner: Callable[..., subprocess.CompletedProcess[str]],
    exported_home: str | None = None,
) -> AstraPreflight:
    """Run the Codex account broker and decide whether Astra may bind.

    ::

        exported_home None    ->  the broker chooses an account that reaches the normal tier
        exported_home "H"     ->  the broker judges H alone; normal or luna binds on H

    Args:
        broker_path: Path to ``account_broker.py``.
        process_runner: Callable that runs the broker.
        exported_home: Codex home the caller exported, or None when it exported none.

    Returns:
        Eligibility, the chosen account's percent left and Codex home, reason, and fallback kind.
        A pinned home the broker refuses is declined, with the broker's reason, so nothing launches.
    """
    try:
        return _preflight_from_broker(
            _run_broker(broker_path, process_runner, exported_home), exported_home
        )
    except subprocess.TimeoutExpired as error:
        return _preflight_fallback(
            f"{ASTRA_ACCOUNT_PICK_TIMEOUT_REASON}: {error}", None, ASTRA_FALLBACK_KIND_BROKEN
        )
    except (OSError, subprocess.SubprocessError, TypeError, ValueError) as error:
        return _broken(str(error))
