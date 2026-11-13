"""Tests for the shared Stop hook hold signal."""

from __future__ import annotations

import json

import pytest

from hooks_constants.stop_hook_hold import hold_stop, stop_hold_output

HOLD_REASON = "The task list is stale. Update it, then end the turn."


def test_should_exit_two_with_the_reason_on_both_channels_for_claude_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = hold_stop({"hook_event_name": "Stop", "stop_hook_active": False}, HOLD_REASON)
    captured = capsys.readouterr()
    assert exit_code == 2
    assert json.loads(captured.out) == {"decision": "block", "reason": HOLD_REASON}
    assert captured.err == HOLD_REASON


def test_should_exit_zero_with_a_followup_message_for_a_cursor_payload(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = hold_stop({"hook_event_name": "stop", "conversation_id": "c-1"}, HOLD_REASON)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "decision": "block",
        "reason": HOLD_REASON,
        "followup_message": HOLD_REASON,
    }
    assert captured.err == ""


def test_should_add_a_followup_message_only_for_a_cursor_payload() -> None:
    assert stop_hold_output({}, "why") == {"decision": "block", "reason": "why"}
    assert stop_hold_output({"conversation_id": "c-1"}, "why")["followup_message"] == "why"
