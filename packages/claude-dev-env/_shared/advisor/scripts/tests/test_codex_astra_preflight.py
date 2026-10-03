"""Tests for the Codex Astra account preflight."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS_ROOT / "config"))
sys.path.insert(0, str(SCRIPTS_ROOT))

from codex_astra_preflight import run_astra_preflight


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
                "account": "codex-2",
                "home": str(home),
                "main": False,
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
