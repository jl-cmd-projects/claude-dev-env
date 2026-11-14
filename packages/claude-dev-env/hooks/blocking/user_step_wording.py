"""Find the words in a reply or a sent file that say something waits on the user.

The open tasks Stop gate reads the closing reply and each text file the turn
sent through this module::

    flag: Three items need you.                        -> "need you"
    flag: The docs pull request needs your merge.      -> "needs your"
    flag: Say when the demo sessions may be archived.  -> "Say when"
    flag: It isn't merged yet and needs your approval. -> "needs your"
    flag: Pull request 12 (not urgent) needs your approval.
    ok:   Nothing here needs you.
    ok:   None of the open items needs you.
    ok:   This change does not need you.
    ok:   Action required: none.
    ok:   The docs say when the token expires.
    ok:   The label reads `needs you`.                 (a code span)
    ok:   > What needs you?                            (a quote)

The rule behind every shape below: a wrong hold costs the agent one step, and
a wrong skip hides a step from the user. So an unclear line is held, and a
match is skipped only in the shapes this text names.

A match is skipped when its clause negates it. The clause is the text before
the match on the same line, back to a sentence mark, a comma, a semicolon, a
colon, a table bar, or one of the words and, but, so, then, and while. The read
looks 240 characters back for it. A line break always ends a clause, so
"Nothing on this list" wrapped onto "needs you." is held. Three shapes negate a
match:

- nothing, none, or nobody anywhere in the clause;
- no, neither, or nor at the start of the clause, also after "there is",
  "there are", "there was", or "there were";
- not, never, without, "no longer", or a word ending in n't, up to three words
  before the match, where a word is a run of letters, digits, underscores,
  hyphens, apostrophes, and asterisks.

Each of these words counts as a whole word. Asterisk emphasis may wrap it, as
in "does **not** need you". A word joined to a letter, a digit, an underscore,
or a hyphen on either side is another word, so "No-reply inbox needs your
record", "NO_PROXY needs your value", "The do-nothing job needs your
approval", and "_Nothing_ here needs you" are held. A phrase counts inside
emphasis marks too, as in "_needs your_ merge".

The start of a clause may carry markers: white space, a list, heading, or quote
mark, a number, a full stop, a parenthesis, an empty checkbox, or an emphasis
mark, as in "- No open item needs you." and "**No** item needs you." A marker
before no, neither, or nor belongs to the clause start and is no part of that
word, so "_No open item_ needs you." is skipped. When the 240 characters hold
no clause break and do not reach the start of the paragraph, the clause start
is out of view. Then a word the window cuts in two is dropped, the second
shape does not apply, and "say when" does not count.

A match is skipped too when it is a label with nothing under it. The label
form is closed, it sits on one line, and it reads in this order::

    the match                         Action required
    a colon or a dash                 :
    none, nothing, n/a,               none
      "no action", "no actions",
      "no step", or "no steps"
    then, when present: needed,       at this time
      required, "for now",
      "at this time", or "right now"
    then, when present: one full      .
      stop, exclamation mark, or
      question mark
    the end of the line

Up to eight spaces, tabs, or Markdown emphasis marks may sit on each side of
the colon or dash, and up to three emphasis marks on each side of the closing
mark, as in ``**Action required:** none.`` Every other wording after a match is
held: "Action required: NO_PROXY must list the host", "blocked on you - nothing
else is holding it", "Action required: none. Merge item 12 first.", "Action
required: no", where a bare no can be an answer or an abbreviation, and a
"What needs you" heading over a paragraph that says "Nothing."

"Say when" counts only at the start of its clause, where it is an instruction:
after the same markers, and after the word please, the word just, or both in
that order.

These shapes read words. They do not read grammar, so a line can hold a
negating word in the same clause and still hand over a step, and that line is
skipped. The gate reads the whole reply and every sent file, and one phrase
outside the shapes is enough to hold the turn.

Fences, HTML blocks, quoted paragraphs, and code spans are left out of Markdown
and plain text first, and each paragraph is read on its own. An HTML file is
read as its text, one block at a time, with every tag removed and the contents
of script, style, template, title, textarea, noscript, code, pre, and
blockquote elements left out. White space in the HTML source counts as one
space, and a ``br`` as a line break. A hidden attribute and a style that hides
an element are not read, so that text still counts.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
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
    BARE_IMPERATIVE_PATTERN,
    BINARY_READ_MODE,
    CLAUSE_BREAK_PATTERN,
    CLAUSE_LEAD_WINDOW_CHARACTERS,
    CLAUSE_OPENER_PATTERN,
    CUT_WORD_PATTERN,
    HTML_BLOCK_SEPARATOR,
    HTML_LINE_BREAK_TAG,
    HTML_LINE_BREAK_TEXT,
    HTML_SOURCE_SPACE,
    HTML_SOURCE_SPACE_PATTERN,
    LEADING_WORD_PATTERN,
    MAXIMUM_SENT_FILE_BYTES,
    NEGATED_CLAUSE_PATTERN,
    NEGATED_CLAUSE_START_PATTERN,
    NEGATED_TAIL_PATTERN,
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
        clause_lead, is_clause_start_in_view = _clause_lead(prose_text, each_match.start())
        is_tail_negated = NEGATED_TAIL_PATTERN.match(prose_text, each_match.end()) is not None
        if not is_tail_negated and _hands_over_a_step(each_match.group(), clause_lead, is_clause_start_in_view):
            return each_match.group()
    return None


def _clause_lead(prose_text: str, phrase_start: int) -> tuple[str, bool]:
    window_start = max(0, phrase_start - CLAUSE_LEAD_WINDOW_CHARACTERS)
    lead_window = prose_text[window_start:phrase_start]
    if window_start and CUT_WORD_PATTERN.match(prose_text, window_start - 1):
        lead_window = LEADING_WORD_PATTERN.sub("", lead_window, count=1)
    all_lead_clauses = CLAUSE_BREAK_PATTERN.split(lead_window)
    return all_lead_clauses[-1], window_start == 0 or len(all_lead_clauses) > 1


def _hands_over_a_step(phrase: str, clause_lead: str, is_clause_start_in_view: bool) -> bool:
    if NEGATED_CLAUSE_PATTERN.search(clause_lead):
        return False
    if not is_clause_start_in_view:
        return not BARE_IMPERATIVE_PATTERN.match(phrase)
    if NEGATED_CLAUSE_START_PATTERN.match(clause_lead):
        return False
    if BARE_IMPERATIVE_PATTERN.match(phrase):
        return CLAUSE_OPENER_PATTERN.fullmatch(clause_lead) is not None
    return True


def waiting_phrase(shown_text: str) -> str | None:
    """Return the first phrase in Markdown or plain text that says something waits on the user, or None."""
    return _first_waiting_phrase(prose_paragraphs(shown_text))


def _first_waiting_phrase(all_blocks: Iterable[str]) -> str | None:
    all_phrases = (waiting_phrase_in_prose(each_block) for each_block in all_blocks)
    return next((each_phrase for each_phrase in all_phrases if each_phrase is not None), None)


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.all_text_runs: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, all_attributes: list[tuple[str, str | None]]) -> None:
        if tag in ALL_HTML_HIDDEN_TAGS:
            self.hidden_depth += 1
        if tag == HTML_LINE_BREAK_TAG:
            self.all_text_runs.append(HTML_LINE_BREAK_TEXT)
        elif tag not in ALL_HTML_INLINE_TAGS:
            self.all_text_runs.append(HTML_BLOCK_SEPARATOR)

    def handle_endtag(self, tag: str) -> None:
        if tag in ALL_HTML_HIDDEN_TAGS and self.hidden_depth:
            self.hidden_depth -= 1
        if tag != HTML_LINE_BREAK_TAG and tag not in ALL_HTML_INLINE_TAGS:
            self.all_text_runs.append(HTML_BLOCK_SEPARATOR)

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.all_text_runs.append(HTML_SOURCE_SPACE_PATTERN.sub(HTML_SOURCE_SPACE, data))


def html_visible_text(page_markup: str) -> str:
    """Return the text of an HTML page, with its tags removed.

    ::

        <h2>What needs you</h2><p>Add the <b>key</b>.</p>  -> "What needs you", "Add the key."
        <script>var needsYou = 1</script>                  -> nothing
        <code>needs you</code>                             -> nothing

    Script, style, template, title, textarea, noscript, code, pre, and
    blockquote contents are left out. A tag that is not an inline tag leaves a
    blank line, so a heading and the paragraph after it stay apart, and
    ``file_waiting_phrase`` reads each such block on its own. White space in
    the source becomes one space, and a ``br`` leaves a line break. Text under
    a hidden attribute or a hiding style is kept.
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
        return _first_waiting_phrase(html_visible_text(file_text).split(HTML_BLOCK_SEPARATOR))
    return waiting_phrase(file_text)
