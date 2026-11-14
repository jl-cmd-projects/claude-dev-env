"""Find the words in a reply or a sent file that say something waits on the user.

The open tasks Stop gate reads the closing reply and each text file the turn
sent through this module::

    flag: Three items need you.                        -> "need you"
    flag: The docs pull request needs your merge.      -> "needs your"
    flag: Say when the demo sessions may be archived.  -> "Say when"
    ok:   Nothing here needs you.
    ok:   The label reads `needs you`.                 (a code span)
    ok:   > What needs you?                            (a quote)

A match counts unless a negating word sits up to three words before it in the
same sentence. Fences, HTML blocks, quoted paragraphs, and code spans are left
out of Markdown and plain text first. An HTML file is read as its text, with
script and style blocks and every tag removed.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from final_reply_gate import prose_paragraphs
from hooks_constants.open_tasks_stop_gate_constants import UTF8_ENCODING
from hooks_constants.user_step_wording_constants import (
    ALL_HTML_FILE_SUFFIXES,
    ALL_SENT_TEXT_FILE_SUFFIXES,
    HTML_HIDDEN_BLOCK_PATTERN,
    HTML_TAG_PATTERN,
    HTML_TAG_REPLACEMENT,
    MAXIMUM_SENT_FILE_BYTES,
    NEGATED_LEAD_PATTERN,
    SENT_FILE_DECODE_ERRORS,
    SENTENCE_BREAK_PATTERN,
    USER_STEP_PATTERN,
)


def waiting_phrase_in_prose(prose_text: str) -> str | None:
    """Return the first phrase in the prose that says something waits on the user, or None.

    ::

        >>> waiting_phrase_in_prose("The key is set. Two items need you.")
        'need you'
        >>> waiting_phrase_in_prose("Nothing else is waiting on you.") is None
        True
    """
    for each_match in USER_STEP_PATTERN.finditer(prose_text):
        sentence_lead = SENTENCE_BREAK_PATTERN.split(prose_text[: each_match.start()])[-1]
        if NEGATED_LEAD_PATTERN.search(sentence_lead) is None:
            return each_match.group()
    return None


def waiting_phrase(shown_text: str) -> str | None:
    """Return the first phrase in Markdown or plain text that says something waits on the user, or None."""
    all_phrases = (
        waiting_phrase_in_prose(each_paragraph) for each_paragraph in prose_paragraphs(shown_text)
    )
    return next((each_phrase for each_phrase in all_phrases if each_phrase is not None), None)


def html_visible_text(page_markup: str) -> str:
    """Return the text of an HTML page, with script and style blocks and every tag removed."""
    shown_markup = HTML_HIDDEN_BLOCK_PATTERN.sub(HTML_TAG_REPLACEMENT, page_markup)
    return html.unescape(HTML_TAG_PATTERN.sub(HTML_TAG_REPLACEMENT, shown_markup))


def file_waiting_phrase(file_path_text: str, working_directory: object) -> str | None:
    """Return the first waiting phrase in a text file the turn sent to the user, or None.

    A path that is not absolute is read from the working directory. A file with
    another suffix, a file over the size limit, and a file that cannot be read
    give None.
    """
    file_path = Path(file_path_text)
    if not file_path.is_absolute() and isinstance(working_directory, str):
        file_path = Path(working_directory) / file_path
    file_suffix = file_path.suffix.lower()
    if file_suffix not in ALL_SENT_TEXT_FILE_SUFFIXES:
        return None
    try:
        if file_path.stat().st_size > MAXIMUM_SENT_FILE_BYTES:
            return None
        file_text = file_path.read_text(encoding=UTF8_ENCODING, errors=SENT_FILE_DECODE_ERRORS)
    except OSError:
        return None
    if file_suffix in ALL_HTML_FILE_SUFFIXES:
        return waiting_phrase_in_prose(html_visible_text(file_text))
    return waiting_phrase(file_text)
