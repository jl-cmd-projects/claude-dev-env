"""Stop hook that blocks until the session title is set with a status emoji."""

import json
import sys
from typing import TextIO

from config.session_title_gate_constants import ALL_TITLE_TOOL_NAMES, INSTRUCTION


def _content_blocks(entry: dict) -> list:
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content if isinstance(content, list) else []


def _is_user_text(entry: dict) -> bool:
    if entry.get("type") != "user":
        return False
    return any(
        block.get("type") == "text" and block.get("text", "").strip()
        for block in _content_blocks(entry)
        if isinstance(block, dict)
    )


def _is_title_call(entry: dict) -> bool:
    if entry.get("type") != "assistant":
        return False
    return any(
        block.get("type") == "tool_use" and block.get("name") in ALL_TITLE_TOOL_NAMES
        for block in _content_blocks(entry)
        if isinstance(block, dict)
    )


def title_set_since_last_user_text(all_transcript_lines: list[str]) -> bool:
    """Report whether a title call follows the newest user text in the transcript.

    Args:
        all_transcript_lines: The transcript's JSONL lines, oldest first.

    Returns:
        True when a set_session_title call comes after the last user text.
    """
    for each_line in reversed(all_transcript_lines):
        if not each_line.strip():
            continue
        entry = json.loads(each_line)
        if _is_title_call(entry):
            return True
        if _is_user_text(entry):
            return False
    return False


def main(decision_stream: TextIO) -> None:
    """Block the stop with the title instruction when no title follows the last user text.

    Args:
        decision_stream: The stream that receives the Stop hook decision.
    """
    try:
        payload = json.load(sys.stdin)
        if payload.get("stop_hook_active"):
            return
        with open(payload["transcript_path"], encoding="utf-8") as transcript_file:
            all_transcript_lines = transcript_file.readlines()
        if title_set_since_last_user_text(all_transcript_lines):
            return
    except (OSError, KeyError, ValueError):
        return
    decision_stream.write(json.dumps({"decision": "block", "reason": INSTRUCTION}))


if __name__ == "__main__":
    main(sys.stdout)
