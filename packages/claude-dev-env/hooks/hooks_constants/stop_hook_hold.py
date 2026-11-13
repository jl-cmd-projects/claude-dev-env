"""Shared hold signal for Stop hooks.

A Stop gate that finds a problem holds the turn so the model tries again. Each
host reads the hold from a different channel, so one call writes all of them::

    Claude Code   exit code 2; the stdout ``reason`` reaches the model
    Codex         exit code 2; stderr reaches the model
    Cursor        exit code 0; ``followup_message`` becomes the next user message

A Cursor payload carries ``conversation_id``. Cursor documents no exit code 2
for its ``stop`` event, so that payload keeps exit code 0. Every other payload
gets exit code 2, with the same text on stderr and in the stdout ``reason``,
so the hold does not depend on which channel the host reads first.
"""

from __future__ import annotations

import json
import sys

from hooks_constants.stop_hook_hold_constants import (
    ALLOW_EXIT_CODE,
    BLOCK_DECISION,
    BLOCK_EXIT_CODE,
    CURSOR_CONVERSATION_ID_KEY,
    CURSOR_FOLLOWUP_MESSAGE_KEY,
    DECISION_KEY,
    REASON_KEY,
)


def stop_hold_output(all_hook_input_fields: dict[str, object], block_reason: str) -> dict[str, str]:
    """Return the stdout object for a hold; a Cursor payload also gets ``followup_message``."""
    hold_output = {DECISION_KEY: BLOCK_DECISION, REASON_KEY: block_reason}
    if all_hook_input_fields.get(CURSOR_CONVERSATION_ID_KEY):
        hold_output[CURSOR_FOLLOWUP_MESSAGE_KEY] = block_reason
    return hold_output


def hold_stop(all_hook_input_fields: dict[str, object], block_reason: str) -> int:
    """Write the hold for this host and return the exit code the hook must exit with.

    Args:
        all_hook_input_fields: The Stop payload the hook read from stdin.
        block_reason: The text the model gets back so it can fix the problem.

    Returns:
        Zero for a Cursor payload, two for every other host.
    """
    sys.stdout.write(json.dumps(stop_hold_output(all_hook_input_fields, block_reason)))
    if all_hook_input_fields.get(CURSOR_CONVERSATION_ID_KEY):
        return ALLOW_EXIT_CODE
    sys.stderr.write(block_reason)
    return BLOCK_EXIT_CODE
