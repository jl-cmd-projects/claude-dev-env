"""Stop hook that checks the closing chat reply for an unvalidated claim.

The reply length gate checks the chat tools. This gate checks the reply the
session ends its turn with, which reaches the user with no tool call::

    flag: My guess is one to two hours.
    flag: I didn't confirm this one.
    flag: Run 18239174012 passed.        (no tool result shows the run)
    ok:   Run 18239174012 took 39 minutes. (a tool result shows the run)

It applies the banned words, the unvalidated claim pattern, and the cited
run, job, check, and pull request numbers from ``reply_length_gate.py``. The
citation check is skipped when the transcript cannot be read. A block sends
the reason back so the model rewrites the reply. Claude Code ends the turn
after eight blocks in a row.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from reply_length_gate import (
    banned_word_violation,
    configured_banned_words,
    unseen_citation_violation,
    unvalidated_claim_violation,
)
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.final_reply_gate_constants import (
    ALLOW_EXIT_CODE,
    BLOCK_DECISION,
    DECISION_KEY,
    HOOK_EVENT_NAME,
    LAST_ASSISTANT_MESSAGE_KEY,
    REASON_KEY,
    REWRITE_INSTRUCTION,
    TRANSCRIPT_PATH_KEY,
)


def final_reply_violation(reply_text: str, transcript_path: object) -> str | None:
    """Return the block reason for the closing reply, or None when it passes."""
    return (
        banned_word_violation(reply_text, configured_banned_words())
        or unvalidated_claim_violation(reply_text)
        or unseen_citation_violation(reply_text, transcript_path)
    )


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    reply_text = hook_input.get(LAST_ASSISTANT_MESSAGE_KEY)
    if not isinstance(reply_text, str):
        return ALLOW_EXIT_CODE
    violation = final_reply_violation(reply_text, hook_input.get(TRANSCRIPT_PATH_KEY))
    if violation is None:
        return ALLOW_EXIT_CODE
    block_reason = violation + REWRITE_INSTRUCTION
    log_hook_block(
        Path(__file__).name, HOOK_EVENT_NAME, block_reason, offending_input_preview=reply_text
    )
    sys.stdout.write(json.dumps({DECISION_KEY: BLOCK_DECISION, REASON_KEY: block_reason}))
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
