"""Find the words in a reply or a sent file that say something waits on the user.

The open tasks Stop gate reads the closing reply and each text file the turn
sent through this module::

    flag: Three items need you.                        -> "need you"
    flag: The docs pull request needs your merge.      -> "needs your"
    flag: Say when the demo sessions may be archived.  -> "Say when"
    flag: It isn't merged yet and needs your approval. -> "needs your"
    ok:   Nothing here needs you.
    ok:   None of the open items needs you.
    ok:   The label reads `needs you`.                 (a code span)
    ok:   > What needs you?                            (a quote)

A match counts unless a negating word sits before it in the same clause. A
clause ends at a sentence mark, a comma, a semicolon, a colon, a line break, or
one of the words and, but, so, then, and while. Fences, HTML blocks, quoted
paragraphs, and code spans are left out of Markdown and plain text first. An
HTML file is read as its text, with every tag removed and the contents of
script, style, template, code, pre, and blockquote elements left out.
"""

from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from final_reply_gate import prose_paragraphs
from hooks_constants.open_tasks_stop_gate_constants import UTF8_ENCODING
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY
from hooks_constants.user_step_wording_constants import (
    ALL_HTML_FILE_SUFFIXES,
    ALL_HTML_HIDDEN_TAGS,
    ALL_HTML_INLINE_TAGS,
    ALL_SENT_TEXT_FILE_SUFFIXES,
    BINARY_READ_MODE,
    CLAUSE_BREAK_PATTERN,
    CLAUSE_LEAD_WINDOW_CHARACTERS,
    HTML_BLOCK_SEPARATOR,
    MAXIMUM_SENT_FILE_BYTES,
    NEGATING_WORD_PATTERN,
    USER_STEP_PATTERN,
)


def waiting_phrase_in_prose(prose_text: str) -> str | None:
    """Return the first phrase in the prose that says something waits on the user, or None.

    ::

        >>> waiting_phrase_in_prose("The key is set. Two items need you.")
        'need you'
        >>> waiting_phrase_in_prose("Nothing else is waiting on you.") is None
        True

    Each match looks back over a fixed window for its clause, so a long text
    reads in time that grows with its length.
    """
    for each_match in USER_STEP_PATTERN.finditer(prose_text):
        window_start = max(0, each_match.start() - CLAUSE_LEAD_WINDOW_CHARACTERS)
        clause_lead = CLAUSE_BREAK_PATTERN.split(prose_text[window_start : each_match.start()])[-1]
        if NEGATING_WORD_PATTERN.search(clause_lead) is None:
            return each_match.group()
    return None


def waiting_phrase(shown_text: str) -> str | None:
    """Return the first phrase in Markdown or plain text that says something waits on the user, or None."""
    all_phrases = (
        waiting_phrase_in_prose(each_paragraph) for each_paragraph in prose_paragraphs(shown_text)
    )
    return next((each_phrase for each_phrase in all_phrases if each_phrase is not None), None)


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.all_text_runs: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, all_attributes: list[tuple[str, str | None]]) -> None:
        if tag in ALL_HTML_HIDDEN_TAGS:
            self.hidden_depth += 1
        if tag not in ALL_HTML_INLINE_TAGS:
            self.all_text_runs.append(HTML_BLOCK_SEPARATOR)

    def handle_endtag(self, tag: str) -> None:
        if tag in ALL_HTML_HIDDEN_TAGS and self.hidden_depth:
            self.hidden_depth -= 1
        if tag not in ALL_HTML_INLINE_TAGS:
            self.all_text_runs.append(HTML_BLOCK_SEPARATOR)

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.all_text_runs.append(data)


def html_visible_text(page_markup: str) -> str:
    """Return the text a reader sees on an HTML page.

    ::

        <h2>What needs you</h2><p>Add the <b>key</b>.</p>  -> "What needs you", "Add the key."
        <script>var needsYou = 1</script>                  -> nothing
        <code>needs you</code>                             -> nothing

    Script, style, template, code, pre, and blockquote contents are left out.
    A tag that is not an inline tag ends the line, so a heading and the
    paragraph after it stay apart.
    """
    text_parser = _VisibleTextParser()
    text_parser.feed(page_markup)
    text_parser.close()
    return "".join(text_parser.all_text_runs)


def file_waiting_phrase(file_path_text: str, working_directory: object) -> str | None:
    """Return the first waiting phrase in a text file the turn sent to the user, or None.

    A path that is not absolute is read from the working directory. A file with
    another suffix, a path that is no regular file (a pipe, a device, a
    directory), a file over the size limit, and a file that cannot be read give
    None. The read stops one byte past the size limit.
    """
    file_path = Path(file_path_text)
    if not file_path.is_absolute() and isinstance(working_directory, str):
        file_path = Path(working_directory) / file_path
    file_suffix = file_path.suffix.lower()
    if file_suffix not in ALL_SENT_TEXT_FILE_SUFFIXES:
        return None
    try:
        if not file_path.is_file():
            return None
        with file_path.open(BINARY_READ_MODE) as sent_file:
            file_bytes = sent_file.read(MAXIMUM_SENT_FILE_BYTES + 1)
    except (OSError, ValueError):
        return None
    if len(file_bytes) > MAXIMUM_SENT_FILE_BYTES:
        return None
    file_text = file_bytes.decode(UTF8_ENCODING, errors=DECODE_ERRORS_POLICY)
    if file_suffix in ALL_HTML_FILE_SUFFIXES:
        return waiting_phrase_in_prose(html_visible_text(file_text))
    return waiting_phrase(file_text)
