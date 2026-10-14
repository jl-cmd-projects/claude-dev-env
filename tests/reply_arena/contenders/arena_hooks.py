#!/usr/bin/env python3
"""Hook entry points for the chat reply arena contenders.

Run as ``arena_hooks.py <role>``. Each role reads one hook payload on stdin::

    display-log     MessageDisplay   record the text as shown, change nothing
    display-gate    MessageDisplay   show a passing reply as is, a failing one as a helper draft
    capped-gate     UserPromptSubmit, Stop   chat_reply_gate with the cap from ARENA_REWRITE_CAP
    drafting-gate   UserPromptSubmit, Stop   chat_reply_gate whose block reason carries a helper draft
    strong-reminder UserPromptSubmit full rule list, no Stop block
    seen-reminder   UserPromptSubmit baseline reminder plus the condensed text the user last saw

Every role writes what the user sees to ``$ARENA_RUN_DIR/display.jsonl``
when that variable is set, so the scorer reads one log for all contenders.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

contenders_directory = Path(__file__).resolve().parent
hooks_directory = Path(__file__).resolve().parents[3] / "packages" / "claude-dev-env" / "hooks"
for each_path in (contenders_directory, hooks_directory, hooks_directory / "blocking"):
    if str(each_path) not in sys.path:
        sys.path.insert(0, str(each_path))

import chat_reply_gate
from hooks_constants.chat_reply_gate_constants import REPLY_LIMIT_REMINDER
from hooks_constants.reply_length_gate_constants import (
    MAXIMUM_SENTENCE_COUNT,
    MAXIMUM_WORDS_PER_SENTENCE,
)
from reply_drafter import (
    ARENA_RUN_DIRECTORY_ENV_VAR,
    DRAFTER_GUARD_ENV_VAR,
    draft_compliant_reply,
)
from reply_length_gate import reply_violation

DISPLAY_LOG_FILE_NAME = "display.jsonl"
REWRITE_CAP_ENV_VAR = "ARENA_REWRITE_CAP"
BUFFER_FILE_PREFIX = "claude-chat-reply-display-"
SEEN_FILE_PREFIX = "claude-chat-reply-seen-"
TEXT_FILE_SUFFIX = ".txt"
DRAFT_INSTRUCTION = (
    " A rewrite that passes is below. Send it as your whole reply, word for word,"
    " unless a fact in it is wrong. Then fix only that fact.\n\n"
)
STRONG_REMINDER = (
    f"Your reply to the user is final and gets no second pass. Keep it to {MAXIMUM_SENTENCE_COUNT}"
    f" sentences or fewer, each {MAXIMUM_WORDS_PER_SENTENCE} words or fewer."
    " Each line and each list item counts as one sentence, so prefer short prose over lists."
    " Lead with the outcome and cut detail the user did not ask for."
    " No colon in the middle of a sentence, and no em dash."
    " Put any pull request number inside a markdown link."
    " A sentence with so, because, caused, due to, therefore, or means needs inline code, a URL, or a link in it."
    " Never write real, really, genuine, actual, actually, likely, probably, seems, maybe, perhaps, may be, or might be."
    " Count your sentences before you send."
)
SEEN_PREFIX = (
    " The user saw your last reply condensed to this text, so build on it:\n\n"
)


def read_payload() -> dict[str, object]:
    """Return the hook payload, or an empty dictionary when stdin holds no JSON object."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def log_display(
    payload: dict[str, object], original_text: str, shown_text: str
) -> None:
    """Append the original and the shown text of one message to the arena run log."""
    run_directory = os.environ.get(ARENA_RUN_DIRECTORY_ENV_VAR)
    if not run_directory:
        return
    record = {
        "message_id": payload.get("message_id"),
        "original": original_text,
        "shown": shown_text,
    }
    with open(
        Path(run_directory) / DISPLAY_LOG_FILE_NAME, "a", encoding="utf-8"
    ) as log_file:
        log_file.write(json.dumps(record) + "\n")


def session_text_path(prefix: str, key: object) -> Path:
    """Return the temp file for one session or message key."""
    safe_key = "".join(
        each_character
        for each_character in str(key)
        if each_character.isalnum() or each_character == "-"
    )
    return (
        Path(tempfile.gettempdir())
        / f"{prefix}{safe_key or 'default'}{TEXT_FILE_SUFFIX}"
    )


def write_display(shown_text: str) -> None:
    """Print the MessageDisplay replacement text."""
    hook_output = {"hookEventName": "MessageDisplay", "displayContent": shown_text}
    sys.stdout.write(json.dumps({"hookSpecificOutput": hook_output}))


def write_prompt_context(context_text: str) -> None:
    """Print UserPromptSubmit additionalContext."""
    hook_output = {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": context_text,
    }
    sys.stdout.write(json.dumps({"hookSpecificOutput": hook_output}))


def run_display_log(payload: dict[str, object]) -> int:
    """Record the message as shown, unchanged."""
    delta_text = str(payload.get("delta") or "")
    log_display(payload, delta_text, delta_text)
    return 0


def run_display_gate(payload: dict[str, object]) -> int:
    """Hold each batch until the message ends, then show it as is or as a passing draft."""
    buffer_path = session_text_path(BUFFER_FILE_PREFIX, payload.get("message_id"))
    held_text = buffer_path.read_text(encoding="utf-8") if buffer_path.exists() else ""
    full_text = held_text + str(payload.get("delta") or "")
    if not payload.get("final"):
        buffer_path.write_text(full_text, encoding="utf-8")
        write_display("")
        return 0
    buffer_path.unlink(missing_ok=True)
    violation = reply_violation(full_text, None, None)
    shown_text = full_text
    if violation is not None:
        shown_text = draft_compliant_reply(full_text, violation) or full_text
        if shown_text != full_text:
            session_text_path(SEEN_FILE_PREFIX, payload.get("session_id")).write_text(
                shown_text, encoding="utf-8"
            )
    log_display(payload, full_text, shown_text)
    if shown_text != full_text or held_text:
        write_display(shown_text)
    return 0


def run_capped_gate() -> int:
    """Run chat_reply_gate with its rewrite cap taken from ARENA_REWRITE_CAP."""
    chat_reply_gate.MAXIMUM_REWRITES_PER_TURN = int(
        os.environ.get(REWRITE_CAP_ENV_VAR, "3")
    )
    return chat_reply_gate.main()


def run_drafting_gate(payload: dict[str, object]) -> int:
    """Run chat_reply_gate, and on a Stop block hand the agent a passing draft."""
    if payload.get("hook_event_name") != "Stop":
        chat_reply_gate.write_rewrite_count(
            chat_reply_gate.rewrite_count_path(payload.get("session_id")), 0
        )
        chat_reply_gate.write_reply_limit_reminder()
        return 0
    block_reason = chat_reply_gate.stop_block_reason(payload)
    if block_reason is None:
        return 0
    reply_text = str(payload.get("last_assistant_message") or "")
    violation = reply_violation(reply_text, None, None) or ""
    draft_text = draft_compliant_reply(reply_text, violation)
    if draft_text is not None:
        block_reason = violation + DRAFT_INSTRUCTION + draft_text
    sys.stderr.write(block_reason)
    return 2


def run_seen_reminder(payload: dict[str, object]) -> int:
    """Print the baseline reminder plus the condensed text the user saw last turn."""
    seen_path = session_text_path(SEEN_FILE_PREFIX, payload.get("session_id"))
    context_text = REPLY_LIMIT_REMINDER
    if seen_path.exists():
        context_text += SEEN_PREFIX + seen_path.read_text(encoding="utf-8")
        seen_path.unlink(missing_ok=True)
    write_prompt_context(context_text)
    return 0


def main() -> int:
    if os.environ.get(DRAFTER_GUARD_ENV_VAR):
        return 0
    role = sys.argv[1] if len(sys.argv) > 1 else ""
    if role == "capped-gate":
        return run_capped_gate()
    payload = read_payload()
    if role == "display-log":
        return run_display_log(payload)
    if role == "display-gate":
        return run_display_gate(payload)
    if role == "drafting-gate":
        return run_drafting_gate(payload)
    if role == "strong-reminder":
        write_prompt_context(STRONG_REMINDER)
        return 0
    if role == "seen-reminder":
        return run_seen_reminder(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
