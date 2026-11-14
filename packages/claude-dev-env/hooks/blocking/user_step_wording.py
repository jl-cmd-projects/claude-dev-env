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
"Nothing on this list" wrapped onto "needs you." is held. A carriage return
counts as a line break. A paragraph that holds another character that ends a
line for ``str.splitlines``, such as a form feed or U+2028, is held at every
match, since readers do not agree on where its lines end.

The clause is read as words. A word is a run of characters with white space,
or an end of the paragraph, on each side. It counts only when all of it sits
inside the clause and it ends before the match. The asterisks and underscores
at its two ends are removed, and the rest must equal a negating word. So
"**No** item needs you." is skipped, and "No-reply inbox needs your record",
"(Nothing here needs you.)", and "Nothing*needs you." are held. Three shapes
negate a match:

- nothing, none, or nobody anywhere in the clause;
- no, neither, or nor as the first word of the clause, also after "there is",
  "there are", "there was", or "there were";
- not, never, without, "no longer", or a word ending in n't (with a straight
  or a curly apostrophe), with up to three words between it and the match.

The first word of a clause is the first one after its markers. A marker is a
word that holds only hyphens, plus signs, hash marks, greater-than signs,
digits, parentheses, and square brackets, or nothing, once the emphasis marks
at its ends are removed, as in "- [ ] No open item needs you." and
"**1)** No reviewer needs your approval." When the 240 characters hold no clause break
and do not reach the start of the paragraph, the clause start is out of view.
Then the second shape does not apply and "say when" does not count.

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
required: no", where a bare no can be an answer or an abbreviation, a
"What needs you" heading over a paragraph that says "Nothing.", and a match
that a line break splits, as in "Action" on one line and "required: none." on
the next.

"Say when" counts only at the start of its clause, where it is an instruction.
The words before it are read with the marker characters, full stops, and
emphasis marks at their ends removed. A word with no letter left is passed
over, and the rest must be nothing, the word please, the word just, or both
in that order, read with case folding. So "- [ ] Say when" counts, and "- [x] Say when" and "The docs
say when" do not. That rule covers "say" with white space right after it. With
an emphasis mark or the closing part of a link right after "say", the phrase
counts wherever it sits, as in "The docs **say** when" and "- [x] [Say](link)
when".

The words of a phrase are joined by white space. Up to three asterisks,
underscores, or opening square brackets may sit on each side of that white
space, so "needs **your** approval" and "waiting on [you](link)" count, and so
does "_needs your_ merge". The closing part of a link may sit before the white
space too. That part is a closing square bracket, alone or with a target in
parentheses or a label in square brackets after it, and then up to three
asterisks or underscores. So "[needs](link) your approval", "[needs][1] your
approval", and "**[You](link)** need to" count. The target or label holds no
white space and at most 256 characters. A target may hold parentheses of its
own, and a label ends at its first closing square bracket. So a link with a
title, as in ``[needs](link "title") your``, breaks the phrase, and so does a
label with square brackets inside it. Every place a phrase can
start is read, also inside another phrase. In Markdown an inline HTML tag or a
character entity between two words of a phrase breaks it.

These shapes read words. They do not read grammar, so a line can hold a
negating word in the same clause and still hand over a step, and that line is
skipped. The gate reads the whole reply and every sent file, and one phrase
outside the shapes is enough to hold the turn.

Fences, HTML blocks, quoted paragraphs, and code spans are left out of Markdown
and plain text first, and each paragraph is read on its own. A code span reads
as a space between the words of a phrase. Everywhere else it reads as U+FFFC,
a character that is no letter and no white space, and one in the text itself
reads the same way. A match is held when a word of its clause holds that
character joined to others, as in ``Not`-`e`` and "api`/`web". The part of a
word after a full stop, a comma, or another clause break counts as a word
there, so ``Done.`x`a No item needs you.`` is held. The label form
does not reach across it, so "Action required: none." with a code span after
it is held.

An HTML file is read as its text, one block at a time, with every tag removed
and the contents of script, style, template, title, textarea, noscript, code,
pre, and blockquote elements left out. White space in the HTML source counts
as one space, a ``br`` as a line break, and an inline ``code`` element as
U+FFFC. Each block is read a second time with that character removed, so a
phrase that a ``code`` element splits still counts. A U+FFFC in the page text
itself is read as U+FFFD, which no reading removes. A hidden attribute and a style that hides an element are not read, so
that text still counts.
"""

from __future__ import annotations

import itertools
import re
import sys
from collections.abc import Iterable
from html.parser import HTMLParser
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from final_reply_gate import prose_paragraphs_with_code_as
from hooks_constants.open_tasks_stop_gate_constants import UTF8_ENCODING
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY
from hooks_constants.user_step_wording_constants import (
    ALL_ABSENCE_WORDS,
    ALL_CLAUSE_OPENING_NEGATORS,
    ALL_CONTRACTED_NEGATOR_ENDINGS,
    ALL_HTML_FILE_SUFFIXES,
    ALL_HTML_HIDDEN_TAGS,
    ALL_HTML_INLINE_TAGS,
    ALL_INSTRUCTION_OPENERS,
    ALL_LATE_NEGATORS,
    ALL_SENT_TEXT_FILE_SUFFIXES,
    ALL_THERE_VERBS,
    BARE_IMPERATIVE_PATTERN,
    BINARY_READ_MODE,
    CLAUSE_BREAK_PATTERN,
    CLAUSE_LEAD_WINDOW_CHARACTERS,
    CLAUSE_WORD_PATTERN,
    CODE_SPAN_SPACE,
    CODE_SPAN_STAND_IN,
    CUT_WORD_PATTERN,
    EMPHASIS_MARKS,
    HTML_BLOCK_SEPARATOR,
    HTML_LINE_BREAK_TAG,
    HTML_LITERAL_STAND_IN_TEXT,
    HTML_SOURCE_SPACE,
    HTML_SOURCE_SPACE_PATTERN,
    LINE_BREAK,
    LINE_ENDING_PATTERN,
    MARKER_WORD_PATTERN,
    MAXIMUM_SENT_FILE_BYTES,
    MAXIMUM_WORDS_AFTER_LATE_NEGATOR,
    OPENER_MARKER_CHARACTERS,
    NEGATED_TAIL_PATTERN,
    ODD_LINE_END_PATTERN,
    PHRASE_GROUP,
    ALL_NO_LONGER_WORDS,
    THERE_WORD,
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
    clause_text = LINE_ENDING_PATTERN.sub(LINE_BREAK, prose_text)
    phrase_text = clause_text.replace(CODE_SPAN_STAND_IN, CODE_SPAN_SPACE)
    has_odd_line_end = ODD_LINE_END_PATTERN.search(clause_text) is not None
    for each_match in USER_STEP_PATTERN.finditer(phrase_text):
        if has_odd_line_end or _hands_over_a_step(clause_text, each_match):
            return each_match.group(PHRASE_GROUP)
    return None


def _clause_start(prose_text: str, phrase_start: int) -> tuple[int, bool]:
    window_start = max(0, phrase_start - CLAUSE_LEAD_WINDOW_CHARACTERS)
    all_break_ends = [
        each_break.end() for each_break in CLAUSE_BREAK_PATTERN.finditer(prose_text, window_start, phrase_start)
    ]
    if all_break_ends:
        return all_break_ends[-1], True
    return window_start, window_start == 0


def _clause_words(prose_text: str, clause_start: int, phrase_start: int) -> list[str]:
    return [
        each_word.group().strip(EMPHASIS_MARKS).lower()
        for each_word in CLAUSE_WORD_PATTERN.finditer(prose_text, clause_start, phrase_start)
        if each_word.end() < phrase_start
    ]


def _cut_word(prose_text: str, clause_start: int, phrase_start: int) -> str:
    cut_word = CUT_WORD_PATTERN.match(prose_text, clause_start, phrase_start)
    return cut_word.group() if cut_word else ""


def _holds_a_negator(all_clause_words: list[str]) -> bool:
    if not ALL_ABSENCE_WORDS.isdisjoint(all_clause_words):
        return True
    all_late_words = all_clause_words[-(MAXIMUM_WORDS_AFTER_LATE_NEGATOR + 1) :]
    if any(
        each_word in ALL_LATE_NEGATORS or each_word.endswith(ALL_CONTRACTED_NEGATOR_ENDINGS)
        for each_word in all_late_words
    ):
        return True
    all_no_longer_reach = all_clause_words[-(MAXIMUM_WORDS_AFTER_LATE_NEGATOR + len(ALL_NO_LONGER_WORDS)) :]
    return ALL_NO_LONGER_WORDS in itertools.pairwise(all_no_longer_reach)


def _opens_with_a_negator(all_clause_words: list[str]) -> bool:
    all_lead_words = itertools.dropwhile(MARKER_WORD_PATTERN.fullmatch, all_clause_words)
    first_word = next(all_lead_words, None)
    if first_word == THERE_WORD and next(all_lead_words, None) in ALL_THERE_VERBS:
        first_word = next(all_lead_words, None)
    return first_word in ALL_CLAUSE_OPENING_NEGATORS


def _opens_an_instruction(all_clause_words: list[str]) -> bool:
    all_bare_words = (each_word.strip(OPENER_MARKER_CHARACTERS).casefold() for each_word in all_clause_words)
    all_lettered_words = tuple(each_word for each_word in all_bare_words if any(map(str.isalpha, each_word)))
    return all_lettered_words in ALL_INSTRUCTION_OPENERS


def _holds_a_joined_code_span(all_clause_words: list[str]) -> bool:
    return any(
        CODE_SPAN_STAND_IN in each_word and each_word.strip(CODE_SPAN_STAND_IN) for each_word in all_clause_words
    )


def _hands_over_a_step(clause_text: str, phrase_match: re.Match[str]) -> bool:
    phrase_start = phrase_match.start(PHRASE_GROUP)
    phrase = phrase_match.group(PHRASE_GROUP)
    is_phrase_on_one_line = LINE_BREAK not in phrase
    if is_phrase_on_one_line and NEGATED_TAIL_PATTERN.match(clause_text, phrase_match.end(PHRASE_GROUP)):
        return False
    clause_start, is_clause_start_in_view = _clause_start(clause_text, phrase_start)
    all_clause_words = _clause_words(clause_text, clause_start, phrase_start)
    cut_word = _cut_word(clause_text, clause_start, phrase_start)
    if _holds_a_joined_code_span([cut_word, *all_clause_words]):
        return True
    if _holds_a_negator(all_clause_words):
        return False
    is_bare_imperative = BARE_IMPERATIVE_PATTERN.match(phrase) is not None
    if not is_clause_start_in_view:
        return not is_bare_imperative
    if _opens_with_a_negator(all_clause_words):
        return False
    return not is_bare_imperative or _opens_an_instruction(all_clause_words)


def waiting_phrase(shown_text: str) -> str | None:
    """Return the first phrase in Markdown or plain text that says something waits on the user, or None."""
    line_fed_text = LINE_ENDING_PATTERN.sub(LINE_BREAK, shown_text)
    return _first_waiting_phrase(prose_paragraphs_with_code_as(line_fed_text, CODE_SPAN_STAND_IN))


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
        if tag in ALL_HTML_HIDDEN_TAGS and tag in ALL_HTML_INLINE_TAGS:
            self.all_text_runs.append(CODE_SPAN_STAND_IN)
        if tag == HTML_LINE_BREAK_TAG:
            self.all_text_runs.append(LINE_BREAK)
        elif tag not in ALL_HTML_INLINE_TAGS:
            self.all_text_runs.append(HTML_BLOCK_SEPARATOR)

    def handle_endtag(self, tag: str) -> None:
        if tag in ALL_HTML_HIDDEN_TAGS and self.hidden_depth:
            self.hidden_depth -= 1
        if tag != HTML_LINE_BREAK_TAG and tag not in ALL_HTML_INLINE_TAGS:
            self.all_text_runs.append(HTML_BLOCK_SEPARATOR)

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            shown_data = data.replace(CODE_SPAN_STAND_IN, HTML_LITERAL_STAND_IN_TEXT)
            self.all_text_runs.append(HTML_SOURCE_SPACE_PATTERN.sub(HTML_SOURCE_SPACE, shown_data))


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
    return _html_text_with_code_marks(page_markup).replace(CODE_SPAN_STAND_IN, "")


def _html_text_with_code_marks(page_markup: str) -> str:
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
        all_blocks = _html_text_with_code_marks(file_text).split(HTML_BLOCK_SEPARATOR)
        return _first_waiting_phrase(
            each_reading for each_block in all_blocks for each_reading in (each_block, each_block.replace(CODE_SPAN_STAND_IN, ""))
        )
    return waiting_phrase(file_text)
