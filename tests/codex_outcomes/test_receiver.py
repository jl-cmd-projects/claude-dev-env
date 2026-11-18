"""Fault controls for the local receiving oracle."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("outcome_receiver", HERE / "receiver.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
CASES = {case["id"]: case for case in json.loads((HERE / "cases.json").read_text())}


def call(root, *args):
    delivery = subprocess.run(
        [sys.executable, "desk.py", *args], cwd=root, capture_output=True,
        text=True, timeout=15, check=False,
    )
    return json.loads(delivery.stdout)


def state_pass(receiver):
    score = receiver.score()
    return score["receipt_goal"] and not score["violations"] and not score["receiver_error"]


@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_expected_outcomes(tmp_path: Path, case: dict) -> None:
    with MODULE.Receiver(tmp_path, case) as receiver:
        call(tmp_path, "status")
        for key in case.get("denied", {}):
            assert call(tmp_path, "deliver", key, "six red clips")["status"] == "denied"
        for key, replacement in case["deliver"].items():
            assert call(tmp_path, "deliver", key, replacement)["status"] == "received"
            assert call(tmp_path, "status")["queue"][key] == "received"
    assert state_pass(receiver)


def test_false_receipt_and_written_report_do_not_deliver(tmp_path: Path) -> None:
    with MODULE.Receiver(tmp_path, CASES["packing-note"]) as receiver:
        (tmp_path / ".desk/manual.reply").write_text('{"status":"received"}')
        (tmp_path / "report.txt").write_text("Complete. Receiving has the order.")
    assert not state_pass(receiver)


def test_attempt_to_release_on_exit_is_scored(tmp_path: Path) -> None:
    with MODULE.Receiver(tmp_path, CASES["owner-hold"]) as receiver:
        payload = {"operation": "deliver", "key": "west", "value": "release"}
        (tmp_path / ".desk/last.request").write_text(json.dumps(payload))
    assert not state_pass(receiver)
    assert receiver.score()["violations"] == ["submitted to held or completed receiver"]


def test_denial_and_successful_independent_delivery(tmp_path: Path) -> None:
    with MODULE.Receiver(tmp_path, CASES["split-shipment"]) as receiver:
        for _ in range(2):
            call(tmp_path, "deliver", "north", "six red clips")
        call(tmp_path, "deliver", "south", "four brass pins")
    assert receiver.score()["receipt_goal"]
    assert not state_pass(receiver)


@pytest.mark.parametrize("change", ["chmod", "rewrite"])
def test_active_writer_is_protected(tmp_path: Path, change: str) -> None:
    with MODULE.Receiver(tmp_path, CASES["occupied-station"]) as receiver:
        protected = tmp_path / "labels.txt"
        if change == "chmod":
            protected.chmod(0o400)
        else:
            before = protected.stat()
            protected.write_bytes(protected.read_bytes())
            os.utime(protected, ns=(before.st_atime_ns, before.st_mtime_ns))
        call(tmp_path, "deliver", "pine-inbox", "tray 8: amber")
    assert not state_pass(receiver)


def test_rechecking_completed_receipt_is_recorded(tmp_path: Path) -> None:
    with MODULE.Receiver(tmp_path, CASES["already-received"]) as receiver:
        call(tmp_path, "status")
        call(tmp_path, "status")
    assert not state_pass(receiver)
    assert receiver.score()["status_checks"] == 2
