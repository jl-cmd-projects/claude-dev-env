"""Exercise bounded completion review on Codex root and subagent Stop events."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from codex_continuation_review import continuation_review
from hooks_constants.codex_continuation_constants import ALL_CLOSING_PHRASES

HOOK = Path(__file__).with_name("open_tasks_stop_gate.py")


@pytest.mark.parametrize("wording", ALL_CLOSING_PHRASES)
def test_reported_status_triggers_one_review(wording: str) -> None:
    assert continuation_review(f"The work order: {wording.upper()}.", "Finish delivery.", False)


@pytest.mark.parametrize("reply", [
    "The route is NOT YET\nVERIFIED.",
    "The proof was not captured. One activation step remains.",
    "The sweep is complete. The separate caption is still open.",
    "The seal approval is pending. Only the owner can release it. The independent caption is still open.",
    "The archive is unverified. A separate check has a registered wake.",
    "The checks are pending and the separate receipt is unverified. A registered wake covers the checks.",
])
def test_marks_an_unfinished_independent_lane(reply: str) -> None:
    assert continuation_review(reply, "Own the order.", True)


@pytest.mark.parametrize("reply", [
    "The notes say “still open”. No further sign-in is needed.",
    'The status vocabulary includes "unverified" and `pending`.',
    "```text\nThe release is pending.\n```\nAll requested fixtures passed.",
    "> The job is unverified.\n\nThe requested check passed.",
    "All pending checks passed.",
    "No pending items. The run is complete.",
    "The release approval is pending. Only the release owner can approve it.",
    "The release is still blocked. The service returned HTTP 403. Only its owner can grant access.",
    "The upload is awaiting checks. The registered completion wake will resume the assignment.",
    "The checks are still pending. A registered callback will resume the assignment.",
])
def test_quotes_resolutions_and_documented_waits_can_close(reply: str) -> None:
    assert continuation_review(reply, "Handle the requested order.", False) is None


def test_latest_user_stop_and_a_quoted_stop_have_distinct_effects() -> None:
    reply = "The receiving record is still pending."
    assert continuation_review(reply, "Cancel my earlier request and stop work on it now.", False) is None
    assert continuation_review(reply, "The note says ‘stop here’. Finish sending the record.", False)
    assert continuation_review(reply, "Cancel that draft but finish sending the record.", False)


@pytest.mark.parametrize("is_child", [False, True])
def test_protocol_continues_once_and_accepts_a_subsequent_stop(is_child: bool, tmp_path: Path) -> None:
    event = "SubagentStop" if is_child else "Stop"
    command = [sys.executable, str(HOOK), *(["--codex-child-stop"] if is_child else [])]
    payload = {"hook_event_name": event, "turn_id": "synthetic-turn", "cwd": str(tmp_path),
               "stop_hook_active": False, "last_assistant_message": "The requested receiving record is still open."}
    first = subprocess.run(command, input=json.dumps(payload), capture_output=True, text=True, check=False)
    assert first.returncode == 2
    decision = json.loads(first.stdout)
    assert decision["decision"] == "block" and decision["reason"] == first.stderr
    assert "full assignment" in first.stderr and "required approvals" in first.stderr
    second = subprocess.run(command, input=json.dumps({**payload, "stop_hook_active": True}),
                            capture_output=True, text=True, check=False)
    assert second.returncode == 0 and not second.stdout
