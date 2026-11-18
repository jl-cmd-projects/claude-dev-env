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
    "North approval is pending, and the separate east receipt is still open.",
    "North approval is pending, and the east receipt is still open.",
    "The east receipt is still pending. The north check has a registered wake.",
    "The north check has a registered wake, and the east receipt is still pending.",
    "The checks are pending and the separate receipt is unverified. A registered wake covers the checks.",
])
def test_marks_an_unfinished_independent_lane(reply: str) -> None:
    assert continuation_review(reply, "Own the order.", True)


@pytest.mark.parametrize("reply", [
    "The notes say “still open”. No further sign-in is needed.",
    "Example: “The release\nis still open.”",
    "The upload is still pending. A registered completion wake will resume the assignment.",
    "The upload remains open. Only the owner can release it.",
    "The release is still blocked. You declined approval for the destination.",
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
    assert continuation_review(reply, "Give me a status update only.", False) is None
    assert continuation_review(reply, "Cancel the release.", False) is None
    assert continuation_review(reply, "Please cancel the warehouse release.", False) is None
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


@pytest.mark.parametrize("is_child", [False, True])
@pytest.mark.parametrize(("instruction", "close", "expected"), [
    ("Stop.", "The transfer is pending.", 0),
    ("Cancel the transfer.", "The transfer is pending.", 0),
    ("Report only.", "The transfer is pending.", 0),
    ("Finish the transfer.", "The transfer is pending.", 2),
    ("Verify the transfer.", "The receiving ledger confirms the transfer.", 0),
])
def test_completed_native_user_message_governs_each_stop(
    is_child: bool, instruction: str, close: str, expected: int, tmp_path: Path,
) -> None:
    record = {"type": "event_msg", "payload": {"type": "item_completed", "turn_id": "latest",
        "item": {"type": "UserMessage", "id": "request",
                 "content": [{"type": "text", "text": instruction, "text_elements": []}]}}}
    transcript = tmp_path / "turn.jsonl"
    transcript.write_text(json.dumps(record) + "\n", encoding="utf-8")
    parent = tmp_path / "parent.jsonl"
    parent.write_text("", encoding="utf-8")
    event = {"hook_event_name": "SubagentStop" if is_child else "Stop", "turn_id": "latest",
             "transcript_path": str(parent if is_child else transcript), "agent_transcript_path": str(transcript),
             "cwd": str(tmp_path), "last_assistant_message": close, "stop_hook_active": False}
    argv = [sys.executable, str(HOOK), *(["--codex-child-stop"] if is_child else [])]
    first = subprocess.run(argv, input=json.dumps(event), text=True, capture_output=True)
    assert first.returncode == expected
    repeated = subprocess.run(argv, input=json.dumps({**event, "stop_hook_active": True}), text=True, capture_output=True)
    assert repeated.returncode == 0 and not repeated.stdout
