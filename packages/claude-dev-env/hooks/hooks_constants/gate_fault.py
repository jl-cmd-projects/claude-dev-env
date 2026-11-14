"""Word the decision a gate gives when one of its checks raises."""

from __future__ import annotations

from hooks_constants.gate_fault_constants import (
    GATE_FAULT_REASON_TEMPLATE,
    GATE_FAULT_SYSTEM_MESSAGE_TEMPLATE,
    GATE_FAULT_TEXT_CHARACTER_LIMIT,
)


def gate_fault_reason(gate_name: str, error: BaseException) -> str:
    """Return the deny reason for a call whose check raised.

    ::

        "merge review", KeyError("head")  -> "The merge review gate hit a fault ... KeyError: 'head'. ..."

    Args:
        gate_name: The gate's name as the reader knows it, without the word gate.
        error: The error the check raised.

    Returns:
        The permissionDecisionReason text for the gate's deny.
    """
    return GATE_FAULT_REASON_TEMPLATE.format(
        gate_name=gate_name,
        error_type=type(error).__name__,
        error_text=str(error)[:GATE_FAULT_TEXT_CHARACTER_LIMIT],
    )


def gate_fault_system_message(gate_script_name: str, error: BaseException) -> str:
    """Return the warning the user sees when a gate's check raised and the gate let the call pass.

    ::

        "verify_before_commit_gate.py", KeyError("head")
            -> "verify_before_commit_gate.py hit a fault and did not check this call: KeyError: 'head'. ..."

    Args:
        gate_script_name: The file name of the gate script that raised.
        error: The error the check raised.

    Returns:
        The warning text for the hook output's top-level systemMessage field.
    """
    return GATE_FAULT_SYSTEM_MESSAGE_TEMPLATE.format(
        gate_script_name=gate_script_name,
        error_type=type(error).__name__,
        error_text=str(error)[:GATE_FAULT_TEXT_CHARACTER_LIMIT],
    )
