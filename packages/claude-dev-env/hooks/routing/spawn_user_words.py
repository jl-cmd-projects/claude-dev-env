"""Check that a spawn brief quotes the user's own words from this session.

The brief opens a fenced block with the ``User's words:`` marker and puts the
user's message in it, word for word. The quote passes when it appears in the
user text of the session transcript, after HTML unescaping and whitespace
collapse. A paraphrase fails that match.

::

    "User's words:\\n```\\nAdd X.\\n```\\nOutcome: ..."  with "Add X." in the transcript -> []
    "Outcome: ..." with no marker                                    -> missing
    quote "Add X, please." when the transcript says "Add X."         -> mismatch
"""

from __future__ import annotations

import html
import json
import sys
from collections.abc import Iterator
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.spawn_oversight_hook_constants import (
    MISMATCHED_USER_WORDS_REASON,
    MISSING_USER_WORDS_REASON,
    USER_WORDS_BLOCK_PATTERN,
)
from hooks_constants.spawn_readiness_hook_constants import (
    BLOCK_TYPE_KEY,
    CONTENT_KEY,
    ENTRY_TYPE_KEY,
    IS_COMPACT_SUMMARY_KEY,
    IS_META_KEY,
    MESSAGE_KEY,
    TEXT_BLOCK_TYPE,
    TEXT_KEY,
    TRANSCRIPT_DECODE_ERRORS,
    TRANSCRIPT_ENCODING,
    USER_ENTRY_TYPE,
)

TRANSCRIPT_LINE_SEPARATOR = "\n"
TEXT_JOIN_SEPARATOR = " "


def _normalized(text: str) -> str:
    return TEXT_JOIN_SEPARATOR.join(html.unescape(text).split())


def _parsed_entry(transcript_line: str) -> dict[object, object]:
    try:
        parsed_entry = json.loads(transcript_line)
    except json.JSONDecodeError:
        return {}
    return parsed_entry if isinstance(parsed_entry, dict) else {}


def _entry_texts(all_entry_fields: dict[object, object]) -> Iterator[str]:
    message = all_entry_fields.get(MESSAGE_KEY)
    content = message.get(CONTENT_KEY) if isinstance(message, dict) else None
    if isinstance(content, str):
        yield content
        return
    all_blocks = content if isinstance(content, list) else []
    for each_block in all_blocks:
        if not isinstance(each_block, dict) or each_block.get(BLOCK_TYPE_KEY) != TEXT_BLOCK_TYPE:
            continue
        block_text = each_block.get(TEXT_KEY)
        if isinstance(block_text, str):
            yield block_text


def _user_texts(all_transcript_lines: list[str]) -> Iterator[str]:
    for each_line in all_transcript_lines:
        all_entry_fields = _parsed_entry(each_line)
        if all_entry_fields.get(ENTRY_TYPE_KEY) != USER_ENTRY_TYPE:
            continue
        if all_entry_fields.get(IS_META_KEY) or all_entry_fields.get(IS_COMPACT_SUMMARY_KEY):
            continue
        yield from _entry_texts(all_entry_fields)


def quoted_user_words(brief: str) -> str | None:
    """Return the words in the brief's ``User's words:`` block, or None when it has none.

    ::

        "User's words:\\n```\\nAdd X.\\n```"  -> "Add X.\\n"
        "**User's words:**\\n```\\nAdd X.\\n```" -> "Add X.\\n"
        "Outcome: X is done."                 -> None

    Args:
        brief: The text the spawn hands its agents.

    Returns:
        The text inside the first fenced block after the marker, or None.
    """
    match = USER_WORDS_BLOCK_PATTERN.search(brief)
    return match.group(1) if match else None


def session_user_text(transcript_path: object) -> str:
    """Return the user text of a session transcript, normalized, or "" when unreadable.

    The text covers user entries only. Assistant entries, tool results, meta
    entries, and compaction summaries stay out, so a brief cannot match its
    own text.

    ::

        a user entry "it&#39;s fine"  -> "it's fine"
        an assistant entry "Add X."   -> nothing from that entry

    Args:
        transcript_path: The ``transcript_path`` value from the hook payload.

    Returns:
        The normalized user text, joined in transcript order, or "".
    """
    if not isinstance(transcript_path, str) or not transcript_path:
        return ""
    try:
        all_transcript_lines = (
            Path(transcript_path)
            .read_text(encoding=TRANSCRIPT_ENCODING, errors=TRANSCRIPT_DECODE_ERRORS)
            .splitlines()
        )
    except OSError:
        return ""
    return _normalized(TRANSCRIPT_LINE_SEPARATOR.join(_user_texts(all_transcript_lines)))


def user_words_gaps(brief: str, transcript_path: object) -> list[str]:
    """Return the refusal reason when the brief's user words are missing or do not match.

    A transcript that cannot be read or holds no user text gives no mismatch,
    because nothing can be compared against it. The marker check still applies.

    ::

        "Outcome: X."                                  -> [missing reason]
        "User's words:\\n```\\nAdd X, please.\\n```"  with "Add X." in the transcript
                                                       -> [mismatch reason]
        "User's words:\\n```\\nAdd X.\\n```"          with "Add X." in the transcript
                                                       -> []

    Args:
        brief: The text the spawn hands its agents.
        transcript_path: The ``transcript_path`` value from the hook payload.

    Returns:
        An empty list when the brief passes, else one refusal reason.
    """
    quote = quoted_user_words(brief)
    if quote is None or not _normalized(quote):
        return [MISSING_USER_WORDS_REASON]
    all_session_text = session_user_text(transcript_path)
    if not all_session_text or _normalized(quote) in all_session_text:
        return []
    return [MISMATCHED_USER_WORDS_REASON]
