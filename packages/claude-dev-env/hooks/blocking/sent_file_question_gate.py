#!/usr/bin/env python3
"""PreToolUse hook that keeps questions for the user out of the files and pages a session sends.

The user answers a question through the question tool's card. A question
inside a sent file or a published page gets no card, and the user may never
see it. So the gate reads each Markdown, text, or HTML file a SendUserFile
call sends, and the page an Artifact publish sends, and denies the call when
the file asks the user something::

    deny:  ## Questions for you                     (a heading that opens a question section)
    deny:  Should I archive the old branches?       (a request for a go-ahead)
    deny:  Do you want the cache cleared first?     (a question that names the reader)
    deny:  Keep it merged, or revert it?            (a choice)
    allow: ## How do I install it?                  (a heading: the answer sits below it)
    allow: Does it retry? No. It fails at once.     (the text answers its own question)
    allow: Can I use it offline? After a sync.      (a frequently asked question and its answer)
    allow: Do you need admin? Only to install.      (the same, worded to the reader)
    allow: > Should we ship this?                   (a quote)
    allow: an Artifact publish that declares db or artifact, such as option cards that save the answer

A question line is a sentence that ends with a question mark (or a full-width
one) and names the reader (you, your), opens with a request (should I, want
me, okay to, proceed, merge, thoughts, are we good, would it make sense,
...), opens with "can I", "could we", or "may I", or offers a choice with
"or" in ten words or fewer. A list marker and a task box ("- [ ]") before it
are skipped. Headings, a ``summary`` or ``dt`` label, quotes, fenced and
indented code, and preformatted text are not read as questions, except a
heading that opens a question or decision section, such as "Open
questions", "Decisions needed from you", or "Need your input".

A question the next sentence answers with "Yes," "No." and the like passes;
"Yes or no." and "No rush." are no answers. A question that asks for no
wish or go-ahead passes when a statement follows it in the same paragraph or
list item, unless that statement asks for a reply ("Reply yes", "Let me
know"). A wish or go-ahead names the reader with a word such as want,
prefer, like, approve, think, or me, or opens with a request. A "Q:" line
with an "A:" line below it, in the same block or a later one, and a table
cell with an answer cell after it, pass.

A file over 256 KB is read through its first and last 128 KB. A file that
holds a NUL byte or is not UTF-8, and a file the gate cannot read, pass. The
refusal quotes at most 160 characters of the question.
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from final_reply_gate import prose_paragraphs_with_code_as
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.sent_file_question_gate_constants import (
    ALL_ANSWER_SAVING_CAPABILITIES,
    ALL_BOLD_MARKS,
    ALL_FULL_WIDTH_QUESTION_MARKS,
    ALL_QUOTED_QUESTION_ENDINGS,
    ALL_SKIPPED_PUBLISH_INPUT_KEYS,
    ALLOW_EXIT_CODE,
    ANSWER_LABEL_PATTERN,
    ANSWER_OPENER_PATTERN,
    ARTIFACT_ACTION_INPUT_KEY,
    ARTIFACT_CAPABILITIES_INPUT_KEY,
    ARTIFACT_FILE_PATH_INPUT_KEY,
    ARTIFACT_PUBLISH_ACTION,
    ARTIFACT_TOOL_NAME,
    BLOCK_EXIT_CODE,
    BOLD_MARK_COUNT,
    CWD_KEY,
    EMPHASIS_CHARACTERS,
    EMPHASIS_PATTERN,
    GATE_EVENT_NAME,
    HEADING_CLOSE_MARKS,
    HEADING_MARK,
    HEADING_OPENER_PATTERN,
    ALL_INDENTED_CODE_PREFIXES,
    LABEL_COLON,
    LINE_BREAK,
    LIST_MARKER_PATTERN,
    MAXIMUM_CHOICE_WORDS,
    MAXIMUM_QUOTED_CHARACTERS,
    OPEN_ASK_PATTERN,
    QUESTION_FOUND_MESSAGE,
    QUESTION_LABEL_PATTERN,
    QUESTION_MARK,
    QUESTION_SECTION_PATTERN,
    QUOTE_CUT_MARK,
    QUOTED_SPAN_PATTERN,
    READER_ADDRESS_PATTERN,
    READER_CHOICE_PATTERN,
    READER_WISH_PATTERN,
    REQUEST_OPENER_PATTERN,
    RESPONSE_PROMPT_PATTERN,
    SENTENCE_PATTERN,
    SPACE_RUN_PATTERN,
    TABLE_CELL_SEPARATOR,
    TABLE_DIVIDER_CELL_PATTERN,
    TABLE_ROW_PATTERN,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    TRAILING_CLOSERS,
    TRAILING_MARKS,
    UNIT_START_PATTERN,
)
from hooks_constants.user_step_wording_constants import CODE_SPAN_STAND_IN
from open_tasks_transcript_records import send_call_file_paths
from sent_file_scan import sent_file_scan_text
from user_step_wording import html_text_blocks, is_html_file_path


def _plain_words(text: str) -> str:
    return SPACE_RUN_PATTERN.sub(" ", EMPHASIS_PATTERN.sub("", text)).strip()


def _is_question(sentence: str) -> bool:
    if not sentence.rstrip(TRAILING_MARKS).endswith(QUESTION_MARK):
        return False
    return not sentence.rstrip(TRAILING_CLOSERS).endswith(ALL_QUOTED_QUESTION_ENDINGS)


def _is_short_choice(sentence: str) -> bool:
    return (
        READER_CHOICE_PATTERN.search(sentence) is not None
        and len(sentence.split()) <= MAXIMUM_CHOICE_WORDS
    )


def _asks_the_reader(sentence: str) -> bool:
    if not _is_question(sentence):
        return False
    return (
        _is_short_choice(sentence)
        or READER_ADDRESS_PATTERN.search(sentence) is not None
        or REQUEST_OPENER_PATTERN.match(sentence) is not None
        or OPEN_ASK_PATTERN.match(sentence) is not None
    )


def _is_answered(sentence: str, next_sentence: str) -> bool:
    if ANSWER_OPENER_PATTERN.match(next_sentence) is not None:
        return True
    is_wish_ask = (
        READER_ADDRESS_PATTERN.search(sentence) is not None
        and READER_WISH_PATTERN.search(sentence) is not None
    )
    is_open_ask = not is_wish_ask and REQUEST_OPENER_PATTERN.match(sentence) is None
    return (
        is_open_ask
        and bool(next_sentence)
        and not _is_question(next_sentence)
        and RESPONSE_PROMPT_PATTERN.match(next_sentence) is None
    )


def _text_units(block_text: str) -> list[str]:
    all_units: list[str] = []
    for each_line in block_text.split(LINE_BREAK):
        if not each_line.strip():
            continue
        if all_units and UNIT_START_PATTERN.match(each_line) is None:
            all_units[-1] = all_units[-1] + " " + each_line.strip()
            continue
        all_units.append(each_line.strip())
    return all_units


def _heading_text(unit_text: str) -> str | None:
    opener = HEADING_OPENER_PATTERN.match(unit_text)
    if opener is not None:
        return unit_text[opener.end() :].strip().rstrip(HEADING_CLOSE_MARKS).strip()
    label_text = unit_text.rstrip()
    if label_text.endswith(LABEL_COLON):
        label_text = label_text[: -len(LABEL_COLON)].rstrip()
    for each_mark in ALL_BOLD_MARKS:
        is_wrapped = (
            len(label_text) > BOLD_MARK_COUNT * len(each_mark)
            and label_text.startswith(each_mark)
            and label_text.endswith(each_mark)
            and label_text[len(each_mark)] not in EMPHASIS_CHARACTERS
        )
        if is_wrapped:
            return label_text[len(each_mark) : -len(each_mark)]
    return None


def _heading_question(heading_text: str) -> str | None:
    section_name = _plain_words(heading_text).rstrip(LABEL_COLON).strip()
    return section_name if QUESTION_SECTION_PATTERN.fullmatch(section_name) else None


def _table_question(row_text: str) -> str | None:
    all_cells = [
        _plain_words(each_cell)
        for each_cell in row_text.strip().strip(TABLE_CELL_SEPARATOR).split(TABLE_CELL_SEPARATOR)
    ]
    if all(TABLE_DIVIDER_CELL_PATTERN.match(each_cell) for each_cell in all_cells):
        return None
    filled_cells = [each_cell for each_cell in all_cells if each_cell]
    if filled_cells and _asks_the_reader(filled_cells[-1]):
        return filled_cells[-1]
    return None


def _sentence_question(unit_text: str) -> str | None:
    unquoted_text = QUOTED_SPAN_PATTERN.sub(CODE_SPAN_STAND_IN, unit_text)
    all_sentences = [
        _plain_words(each_match.group()) for each_match in SENTENCE_PATTERN.finditer(unquoted_text)
    ]
    for each_index, each_sentence in enumerate(all_sentences):
        next_sentence = all_sentences[each_index + 1] if each_index + 1 < len(all_sentences) else ""
        if _asks_the_reader(each_sentence) and not _is_answered(each_sentence, next_sentence):
            return each_sentence
    return None


def _unit_question(unit_text: str, all_later_units: list[str]) -> str | None:
    heading_text = _heading_text(unit_text)
    if heading_text is not None:
        return _heading_question(heading_text)
    if TABLE_ROW_PATTERN.match(unit_text):
        return _table_question(unit_text)
    if ANSWER_LABEL_PATTERN.match(unit_text):
        return None
    question_label = QUESTION_LABEL_PATTERN.match(unit_text)
    if question_label is not None:
        if any(ANSWER_LABEL_PATTERN.match(each_unit) for each_unit in all_later_units):
            return None
        return _sentence_question(unit_text[question_label.end() :])
    return _sentence_question(LIST_MARKER_PATTERN.sub("", unit_text, count=1))


def _without_indented_code(file_text: str) -> str:
    all_kept_lines: list[str] = []
    is_after_blank_line = True
    is_in_code_block = False
    for each_line in file_text.split(LINE_BREAK):
        if not each_line.strip():
            all_kept_lines.append(each_line)
            is_after_blank_line = True
            continue
        is_indented = each_line.startswith(ALL_INDENTED_CODE_PREFIXES)
        is_in_code_block = is_indented and (is_in_code_block or is_after_blank_line)
        all_kept_lines.append("" if is_in_code_block else each_line)
        is_after_blank_line = False
    return LINE_BREAK.join(all_kept_lines)


def question_for_user(file_text: str, is_html: bool) -> str | None:
    """Return the first question the file asks the user, or None.

    >>> question_for_user("Checks passed. Should I merge it?", is_html=False)
    'Should I merge it?'
    >>> question_for_user("## How do I install it?\\n\\nRun the installer.", is_html=False) is None
    True

    Args:
        file_text: The text of a Markdown or plain text file, or an HTML page source.
        is_html: True for an HTML page, read through its shown text.

    Returns:
        The question sentence or section heading, as plain words, or None.
    """
    for each_mark in ALL_FULL_WIDTH_QUESTION_MARKS:
        file_text = file_text.replace(each_mark, QUESTION_MARK)
    if is_html:
        all_blocks = html_text_blocks(file_text, HEADING_MARK)
    else:
        all_blocks = prose_paragraphs_with_code_as(
            _without_indented_code(file_text), CODE_SPAN_STAND_IN
        )
    all_units = [each_unit for each_block in all_blocks for each_unit in _text_units(each_block)]
    for each_index, each_unit in enumerate(all_units):
        question = _unit_question(each_unit, all_units[each_index + 1 :])
        if question is not None:
            return question
    return None


def _short_quote(question: str) -> str:
    if len(question) <= MAXIMUM_QUOTED_CHARACTERS:
        return question
    return question[: MAXIMUM_QUOTED_CHARACTERS - len(QUOTE_CUT_MARK)].rstrip() + QUOTE_CUT_MARK


def _saves_the_answer(all_tool_input_fields: dict[str, object]) -> bool:
    all_capabilities = all_tool_input_fields.get(ARTIFACT_CAPABILITIES_INPUT_KEY)
    if not isinstance(all_capabilities, dict):
        return False
    return not ALL_ANSWER_SAVING_CAPABILITIES.isdisjoint(all_capabilities)


def _published_page_paths(all_tool_input_fields: dict[str, object]) -> list[str]:
    if (
        all_tool_input_fields.get(ARTIFACT_ACTION_INPUT_KEY, ARTIFACT_PUBLISH_ACTION)
        != ARTIFACT_PUBLISH_ACTION
    ):
        return []
    if any(all_tool_input_fields.get(each_key) for each_key in ALL_SKIPPED_PUBLISH_INPUT_KEYS):
        return []
    if _saves_the_answer(all_tool_input_fields):
        return []
    page_path = all_tool_input_fields.get(ARTIFACT_FILE_PATH_INPUT_KEY)
    return [page_path] if isinstance(page_path, str) else []


def sent_file_paths(tool_name: str, all_tool_input_fields: dict[str, object]) -> list[str]:
    """Return the paths of the files a SendUserFile call or an Artifact page publish hands the user.

    >>> sent_file_paths("SendUserFile", {"files": ["a.md", "b.html"]})
    ['a.md', 'b.html']
    >>> sent_file_paths("Artifact", {"file_path": "page.html", "capabilities": {"db": {}}})
    []
    >>> sent_file_paths("Artifact", {"file_path": "page.html", "capabilities": {"sample": {}}})
    ['page.html']

    Args:
        tool_name: The tool the session called.
        all_tool_input_fields: The tool input.

    Returns:
        The paths in call order. An Artifact call that reads, lists, uploads an
        asset, or starts from a type gives none, and so does a publish that
        declares a capability that saves an answer: db, artifact, or self.
    """
    if tool_name == ARTIFACT_TOOL_NAME:
        return _published_page_paths(all_tool_input_fields)
    return send_call_file_paths(tool_name, all_tool_input_fields)


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    tool_name = hook_input.get(TOOL_NAME_KEY)
    tool_input = hook_input.get(TOOL_INPUT_KEY)
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return ALLOW_EXIT_CODE
    working_directory = hook_input.get(CWD_KEY)
    for each_path in sent_file_paths(tool_name, tool_input):
        file_text = sent_file_scan_text(each_path, working_directory)
        if file_text is None:
            continue
        question = question_for_user(file_text, is_html_file_path(each_path))
        if question is None:
            continue
        block_reason = QUESTION_FOUND_MESSAGE.format(
            file_path=each_path, question=_short_quote(question)
        )
        log_hook_block(
            Path(__file__).name,
            GATE_EVENT_NAME,
            block_reason,
            tool_name=tool_name,
            offending_input_preview=each_path,
        )
        sys.stderr.write(block_reason)
        return BLOCK_EXIT_CODE
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
