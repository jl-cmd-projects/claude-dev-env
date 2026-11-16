"""Find a question for the user in the text of a sent file or page.

The sent file question gate reads a file and calls ``question_for_user`` on
its text. The rules for what counts as a question live here, and the gate
module keeps the tool call, the file read, and the refusal::

    "Checks passed. Should I merge it?"           -> "Should I merge it?"
    "## How do I install it?\n\nRun the installer." -> None
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
from hooks_constants.sent_file_question_gate_constants import (
    SPACE,
    MAXIMUM_SENTENCE_CHARACTERS,
    REPLY_REQUEST_PATTERN,
    CHECK_BLOCK_WORD_PATTERN,
    CHOICE_COMMAND_PATTERN,
    LABEL_CHOICE_PATTERN,
    YES_OR_NO_REQUEST_PATTERN,
    TASK_BOX_MARK,
    REPLY_OPTION_PATTERN,
    SENTENCE_EDGE_CHARACTERS,
    SENTENCE_EDGE_JOIN,
    TASK_CHECK_PATTERN,
    WRITER_VOICE_HEADING_PATTERN,
    ALL_BOLD_MARKS,
    ALL_FULL_WIDTH_QUESTION_MARKS,
    ALL_INDENTED_CODE_PREFIXES,
    ALL_QUOTED_QUESTION_ENDINGS,
    ANSWER_LABEL_PATTERN,
    ANSWER_OPENER_PATTERN,
    BOLD_MARK_COUNT,
    EMPHASIS_CHARACTERS,
    EMPHASIS_PATTERN,
    HEADING_CLOSE_MARKS,
    HEADING_MARK,
    HEADING_OPENER_PATTERN,
    LABEL_COLON,
    LINE_BREAK,
    LIST_MARKER_PATTERN,
    MAXIMUM_CHOICE_WORDS,
    OPEN_ASK_PATTERN,
    QUESTION_LABEL_PATTERN,
    QUESTION_MARK,
    QUESTION_SECTION_PATTERN,
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
    TASK_BOX_PATTERN,
    TRAILING_CLOSERS,
    TRAILING_MARKS,
    UNIT_START_PATTERN,
    WH_CHOICE_PATTERN,
)
from hooks_constants.user_step_wording_constants import (
    CODE_SPAN_STAND_IN,
)
from user_step_wording import html_text_blocks


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
        or WH_CHOICE_PATTERN.match(sentence) is not None
    )


def _is_wish_ask(sentence: str) -> bool:
    return (
        READER_ADDRESS_PATTERN.search(sentence) is not None
        and READER_WISH_PATTERN.search(sentence) is not None
    )


def _sentence_edges(sentence: str) -> str:
    if len(sentence) <= MAXIMUM_SENTENCE_CHARACTERS:
        return sentence
    return (
        sentence[:SENTENCE_EDGE_CHARACTERS]
        + SENTENCE_EDGE_JOIN
        + sentence[-SENTENCE_EDGE_CHARACTERS:]
    )


def _is_reply_request(sentence: str) -> bool:
    if REPLY_REQUEST_PATTERN.match(sentence) is not None:
        return True
    if YES_OR_NO_REQUEST_PATTERN.search(sentence) is not None:
        return True
    if CHOICE_COMMAND_PATTERN.match(sentence) is None or sentence.endswith(LABEL_COLON):
        return False
    return (
        REPLY_OPTION_PATTERN.search(sentence) is not None
        or LABEL_CHOICE_PATTERN.search(sentence) is not None
    )


def _is_check(sentence: str) -> bool:
    return (
        TASK_CHECK_PATTERN.match(sentence) is not None
        and CHECK_BLOCK_WORD_PATTERN.search(sentence) is None
        and not _is_wish_ask(sentence)
        and not _is_short_choice(sentence)
    )


def _is_answered(sentence: str, next_sentence: str) -> bool:
    if ANSWER_OPENER_PATTERN.match(next_sentence) is not None:
        return True
    is_open_ask = not _is_wish_ask(sentence) and REQUEST_OPENER_PATTERN.match(sentence) is None
    return (
        is_open_ask
        and bool(next_sentence)
        and not _is_question(next_sentence)
        and RESPONSE_PROMPT_PATTERN.match(next_sentence) is None
    )


def _text_units(block_text: str) -> list[str]:
    all_unit_lines: list[list[str]] = []
    for each_line in block_text.split(LINE_BREAK):
        if not each_line.strip():
            continue
        if all_unit_lines and UNIT_START_PATTERN.match(each_line) is None:
            all_unit_lines[-1].append(each_line.strip())
            continue
        all_unit_lines.append([each_line.strip()])
    return [SPACE.join(each_lines) for each_lines in all_unit_lines]


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


def _sentence_question(unit_text: str, is_checklist_item: bool) -> str | None:
    unquoted_text = QUOTED_SPAN_PATTERN.sub(CODE_SPAN_STAND_IN, unit_text)
    all_sentences = [
        _sentence_edges(_plain_words(each_match.group()))
        for each_match in SENTENCE_PATTERN.finditer(unquoted_text)
    ]
    for each_index, each_sentence in enumerate(all_sentences):
        if _is_reply_request(each_sentence):
            return each_sentence
        next_sentence = all_sentences[each_index + 1] if each_index + 1 < len(all_sentences) else ""
        if is_checklist_item and _is_check(each_sentence):
            continue
        if _asks_the_reader(each_sentence) and not _is_answered(each_sentence, next_sentence):
            return each_sentence
    return None


def _is_question_list_item(unit_text: str | None) -> bool:
    return (
        unit_text is not None
        and LIST_MARKER_PATTERN.match(unit_text) is not None
        and _is_question(unit_text)
    )


def _is_checklist_item(unit_text: str, earlier_unit: str | None, later_unit: str | None) -> bool:
    if LIST_MARKER_PATTERN.match(unit_text) is None:
        return False
    return (
        TASK_BOX_PATTERN.match(unit_text) is not None
        or _is_question_list_item(earlier_unit)
        or _is_question_list_item(later_unit)
    )


def _asking_heading(heading_text: str, later_unit: str | None) -> str | None:
    heading_words = _sentence_edges(_plain_words(heading_text))
    if _is_question(heading_words) and WRITER_VOICE_HEADING_PATTERN.search(heading_words):
        return heading_words
    if not _asks_the_reader(heading_words):
        return None
    is_answered_below = (
        later_unit is not None
        and _heading_text(later_unit) is None
        and LIST_MARKER_PATTERN.match(later_unit) is None
    )
    return None if is_answered_below else heading_words


def _unit_question(
    unit_text: str, earlier_unit: str | None, later_unit: str | None, has_later_answer: bool
) -> str | None:
    heading_text = _heading_text(unit_text)
    if heading_text is not None:
        return _heading_question(heading_text) or _asking_heading(heading_text, later_unit)
    if TABLE_ROW_PATTERN.match(unit_text):
        return _table_question(unit_text)
    if ANSWER_LABEL_PATTERN.match(unit_text):
        return None
    question_label = QUESTION_LABEL_PATTERN.match(unit_text)
    if question_label is not None:
        if has_later_answer:
            return None
        return _sentence_question(unit_text[question_label.end() :], is_checklist_item=False)
    return _sentence_question(
        LIST_MARKER_PATTERN.sub("", unit_text, count=1),
        _is_checklist_item(unit_text, earlier_unit, later_unit),
    )


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
        all_blocks = html_text_blocks(file_text, HEADING_MARK, task_box_mark=TASK_BOX_MARK)
    else:
        all_blocks = prose_paragraphs_with_code_as(
            _without_indented_code(file_text), CODE_SPAN_STAND_IN
        )
    all_units = [each_unit for each_block in all_blocks for each_unit in _text_units(each_block)]
    all_later_answer_flags = _later_answer_flags(all_units)
    for each_index, each_unit in enumerate(all_units):
        earlier_unit = all_units[each_index - 1] if each_index else None
        later_unit = all_units[each_index + 1] if each_index + 1 < len(all_units) else None
        question = _unit_question(
            each_unit, earlier_unit, later_unit, all_later_answer_flags[each_index]
        )
        if question is not None:
            return question
    return None


def _later_answer_flags(all_units: list[str]) -> list[bool]:
    all_flags = [False] * len(all_units)
    has_answer_after = False
    for each_index in range(len(all_units) - 1, -1, -1):
        all_flags[each_index] = has_answer_after
        has_answer_after = has_answer_after or bool(
            ANSWER_LABEL_PATTERN.match(all_units[each_index])
        )
    return all_flags
