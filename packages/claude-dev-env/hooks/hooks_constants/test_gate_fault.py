"""Tests for the wording a gate gives when one of its checks raises."""

from __future__ import annotations

from hooks_constants.gate_fault import gate_fault_reason, gate_fault_system_message
from hooks_constants.gate_fault_constants import GATE_FAULT_TEXT_CHARACTER_LIMIT


def test_reason_names_the_gate_the_error_type_and_the_text() -> None:
    reason = gate_fault_reason("merge review", KeyError("head"))
    assert reason.startswith("The merge review gate hit a fault")
    assert "KeyError: 'head'" in reason
    assert "refused" in reason


def test_reason_caps_the_error_text() -> None:
    reason = gate_fault_reason(
        "merge review", ValueError("x" * (GATE_FAULT_TEXT_CHARACTER_LIMIT * 3))
    )
    assert "x" * GATE_FAULT_TEXT_CHARACTER_LIMIT in reason
    assert "x" * (GATE_FAULT_TEXT_CHARACTER_LIMIT + 1) not in reason


def test_system_message_names_the_script_the_error_and_that_the_call_was_not_checked() -> None:
    message = gate_fault_system_message("verify_before_commit_gate.py", RuntimeError("probe broke"))
    assert "verify_before_commit_gate.py" in message
    assert "RuntimeError: probe broke" in message
    assert "did not check this call" in message


def test_system_message_does_not_say_the_call_is_refused() -> None:
    message = gate_fault_system_message("verify_before_commit_gate.py", RuntimeError("probe broke"))
    assert "refused" not in message


def test_system_message_caps_the_error_text() -> None:
    message = gate_fault_system_message(
        "merge_review_gate.py", ValueError("y" * (GATE_FAULT_TEXT_CHARACTER_LIMIT * 3))
    )
    assert "y" * GATE_FAULT_TEXT_CHARACTER_LIMIT in message
    assert "y" * (GATE_FAULT_TEXT_CHARACTER_LIMIT + 1) not in message
