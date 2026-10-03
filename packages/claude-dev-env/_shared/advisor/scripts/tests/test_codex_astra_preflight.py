"""Tests for the Codex Astra account preflight."""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPTS_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS_ROOT / "config"))
sys.path.insert(0, str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT.parents[2] / "scripts"))

from account_broker import choose_from_readings, decision_payload, readings_payload
from codex_astra_preflight import run_astra_preflight
from dev_env_scripts_constants.account_broker_constants import (
    Account,
    Decision,
    Meters,
    Product,
    Reading,
)


def test_should_accept_broker_normal_answer_and_use_tighter_meter(tmp_path: Path) -> None:
    broker_path = tmp_path / "account_broker.py"
    home = tmp_path / "codex-2"
    answer = {
        "decision": {
            "action": "run",
            "account": "codex-2",
            "home": str(home),
            "resets_at": None,
            "reason": "codex-2 has 42% left",
            "tier": "normal",
        },
        "accounts": [
            {
                "name": "codex-2",
                "home": str(home),
                "is_main": False,
                "meters": {
                    "session_percent_left": 72,
                    "session_resets_at": None,
                    "weekly_percent_left": 42,
                    "weekly_resets_at": None,
                },
            }
        ],
    }
    calls: list[list[str]] = []

    def process_runner(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, json.dumps(answer), "")

    preflight = run_astra_preflight(broker_path, process_runner)

    assert calls == [[sys.executable, str(broker_path), "choose", "--product", "codex"]]
    assert preflight.eligible
    assert preflight.percent_left == 42
    assert preflight.codex_home == home


def test_should_decline_broker_wait_answer_on_exit_three(tmp_path: Path) -> None:
    broker_path = tmp_path / "account_broker.py"
    answer = {
        "decision": {
            "action": "wait",
            "account": None,
            "home": None,
            "resets_at": None,
            "reason": "no account has room",
            "tier": "wait",
        },
        "accounts": [],
    }

    def process_runner(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 3, json.dumps(answer), "")

    preflight = run_astra_preflight(broker_path, process_runner)

    assert not preflight.eligible
    assert preflight.fallback_kind == "declined"
    assert "no account has room" in preflight.reason


def test_should_reject_malformed_broker_answer_on_exit_three(tmp_path: Path) -> None:
    broker_path = tmp_path / "account_broker.py"

    def process_runner(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 3, "not json", "")

    preflight = run_astra_preflight(broker_path, process_runner)

    assert not preflight.eligible
    assert preflight.fallback_kind == "broken"


def test_should_reject_broker_failure(tmp_path: Path) -> None:
    broker_path = tmp_path / "account_broker.py"

    def process_runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, json.dumps({}), "")

    preflight = run_astra_preflight(broker_path, process_runner)

    assert not preflight.eligible
    assert preflight.fallback_kind == "broken"


def test_should_accept_the_answer_the_broker_serializes(tmp_path: Path) -> None:
    account = Account(Product.CODEX, "codex-2", tmp_path / "codex-2")
    reading = Reading(account, Meters(72.0, None, 42.0, None))
    decision = Decision("run", account, None, "codex-2 has 42% left", "normal")
    answer = {"decision": decision_payload(decision), "accounts": readings_payload([reading])}

    def process_runner(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 0, json.dumps(answer), "")

    preflight = run_astra_preflight(tmp_path / "account_broker.py", process_runner)

    assert preflight.eligible
    assert preflight.percent_left == 42
    assert preflight.codex_home == tmp_path / "codex-2"


def test_should_bind_the_default_home_when_no_roster_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    default_home = tmp_path / ".codex"
    monkeypatch.setenv("CODEX_HOME", str(default_home))
    decision = choose_from_readings(Product.CODEX, [], now=datetime.now(timezone.utc))
    answer = {"decision": decision_payload(decision), "accounts": readings_payload([])}

    def process_runner(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 0, json.dumps(answer), "")

    preflight = run_astra_preflight(tmp_path / "account_broker.py", process_runner)

    assert preflight.eligible
    assert preflight.percent_left is None
    assert preflight.codex_home == default_home.resolve()
