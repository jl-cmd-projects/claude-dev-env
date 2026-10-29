"""The visual reply mode rule list and the checks the reply length gate runs from it.

One JSON file, ``rules/visual-reply-rules.json``, holds the rules. The gate,
the reminder and the evaluation read the same file, so all three name each
rule with the same label and the same reminder text.

The mode is off unless ``~/.claude/visual-reply-mode.json`` holds
``{"enabled": true}``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from json_file_reader import read_json_object
from hooks_constants.visual_reply_rules_constants import (
    ABBREVIATION_MESSAGE,
    VIOLATION_LINE_SEPARATOR,
    ABBREVIATIONS_RULE_KEY,
    ALL_REPLY_TOOL_NAME_SUFFIXES,
    ALL_VISUAL_TOOL_NAME_SUFFIXES,
    ALLOWED_CAPITALIZED_WORDS_KEY,
    ASSISTANT_ENTRY_TYPE,
    BLOCK_ID_KEY,
    BLOCK_NAME_KEY,
    BLOCK_TEXT_KEY,
    BLOCK_TYPE_KEY,
    CAPITALIZED_ABBREVIATION_PATTERN,
    CONTENT_KEY,
    ENTRY_TYPE_KEY,
    IS_ERROR_KEY,
    IS_META_KEY,
    LOWERCASE_ABBREVIATION_TEMPLATE,
    LOWERCASE_ABBREVIATIONS_KEY,
    MAXIMUM_REPLIES_PER_TURN,
    MAXIMUM_SENTENCES_WITHOUT_VISUAL,
    MESSAGE_KEY,
    MODE_SWITCH_ENABLED_KEY,
    MODE_SWITCH_FILE_NAME,
    NO_PICTURE_RULE_KEY,
    NO_VISUAL_MESSAGE,
    ONE_ITEM_RULE_KEY,
    RULE_KEY_FIELD,
    RULE_LABEL_FIELD,
    RULE_REMINDER_FIELD,
    RESULT_TEXT_SEPARATOR,
    RULES_FILE_ENCODING,
    RULES_FILE_PATH,
    RULES_LIST_KEY,
    SECOND_REPLY_MESSAGE,
    TEXT_BLOCK_TYPE,
    TOOL_RESULT_BLOCK_TYPE,
    TOOL_USE_BLOCK_TYPE,
    TOOL_USE_ID_KEY,
    TRACKER_NUMBER_MESSAGE,
    TRACKER_NUMBER_PATTERN,
    TRANSCRIPT_ENCODING,
    USER_ENTRY_TYPE,
    WIDGET_ANCHOR_MESSAGE,
    FLOWCHART_ARROW_PATTERN,
    FLOWCHART_DIAMOND_PATTERN,
    FLOWCHART_MARKER_BLOCK_PATTERN,
    FLOWCHART_RULE_KEY,
    FLOWCHART_SVG_PATTERN,
    NOT_FLOWCHART_MESSAGE,
    WIDGET_CODE_KEY,
    WIDGET_INPUT_KEY,
    WIDGET_ANCHOR_PATTERN,
    WIDGET_TOOL_NAME_SUFFIX,
    ALL_PICTURE_SUFFIXES,
    ATTACHED_OUTPUTS_KEY,
    FIGURE_PATTERN,
    LIST_NUMBER_PATTERN,
    MARKDOWN_PICTURE_PATTERN,
    MAXIMUM_FIGURES_WITHOUT_PICTURE,
    OUTPUT_FILE_KIND,
    OUTPUT_KIND_KEY,
    OUTPUT_REF_KEY,
    RESULTS_PICTURE_MESSAGE,
    RESULTS_PICTURE_RULE_KEY,
    TABLE_SEPARATOR_PATTERN,
)
from hooks_constants.reply_length_gate_constants import FENCED_BLOCK_PATTERN, INLINE_CODE_PATTERN


@dataclass(frozen=True)
class ReplyRule:
    """One rule of the mode: its key, the label a flag shows, and the reminder text."""

    key: str
    label: str
    reminder: str


@dataclass(frozen=True)
class VisualReplyRules:
    """The parsed rule file."""

    all_rules: tuple[ReplyRule, ...]
    all_allowed_capitalized_words: frozenset[str]
    all_lowercase_abbreviations: tuple[str, ...]

    def reminder(self, rule_key: str) -> str:
        """Return the reminder text for one rule key."""
        return next(each.reminder for each in self.all_rules if each.key == rule_key)


def _string_list(field_value: object) -> list[object]:
    return field_value if isinstance(field_value, list) else []


def load_rules(rules_path: Path = RULES_FILE_PATH) -> VisualReplyRules | None:
    """Parse the rule file, or return None when it is missing or malformed."""
    document = read_json_object(rules_path, RULES_FILE_ENCODING)
    if document is None:
        return None
    all_rule_entries = document.get(RULES_LIST_KEY)
    if not isinstance(all_rule_entries, list):
        return None
    all_rules = tuple(
        ReplyRule(
            key=str(each[RULE_KEY_FIELD]),
            label=str(each[RULE_LABEL_FIELD]),
            reminder=str(each[RULE_REMINDER_FIELD]),
        )
        for each in all_rule_entries
        if isinstance(each, dict)
        and all(field in each for field in (RULE_KEY_FIELD, RULE_LABEL_FIELD, RULE_REMINDER_FIELD))
    )
    all_needed_keys = {ONE_ITEM_RULE_KEY, NO_PICTURE_RULE_KEY, ABBREVIATIONS_RULE_KEY}
    if not all_needed_keys <= {each.key for each in all_rules}:
        return None
    return VisualReplyRules(
        all_rules=all_rules,
        all_allowed_capitalized_words=frozenset(
            str(each) for each in _string_list(document.get(ALLOWED_CAPITALIZED_WORDS_KEY))
        ),
        all_lowercase_abbreviations=tuple(
            str(each) for each in _string_list(document.get(LOWERCASE_ABBREVIATIONS_KEY))
        ),
    )


def mode_enabled(claude_home: Path) -> bool:
    """Return True only when the switch file turns the mode on."""
    switch_document = read_json_object(claude_home / MODE_SWITCH_FILE_NAME, RULES_FILE_ENCODING)
    if switch_document is None:
        return False
    return switch_document.get(MODE_SWITCH_ENABLED_KEY) is True


def abbreviation_violation(prose_text: str, rules: VisualReplyRules) -> str | None:
    """Return the deny reason naming each abbreviation and tracker number in prose with links and code removed.

    Each one gets its own line, so one refusal names them all.
    """
    reminder = rules.reminder(ABBREVIATIONS_RULE_KEY)
    all_abbreviations = [
        each_match.group(0)
        for each_match in CAPITALIZED_ABBREVIATION_PATTERN.finditer(prose_text)
        if each_match.group(0) not in rules.all_allowed_capitalized_words
    ] + [
        each_abbreviation
        for each_abbreviation in rules.all_lowercase_abbreviations
        if re.search(
            LOWERCASE_ABBREVIATION_TEMPLATE.format(abbreviation=re.escape(each_abbreviation)),
            prose_text,
            re.IGNORECASE,
        )
    ]
    all_violations = [
        *(
            ABBREVIATION_MESSAGE.format(abbreviation=each_abbreviation, reminder=reminder)
            for each_abbreviation in dict.fromkeys(all_abbreviations)
        ),
        *(
            TRACKER_NUMBER_MESSAGE.format(reference=each_match.group(0), reminder=reminder)
            for each_match in TRACKER_NUMBER_PATTERN.finditer(prose_text)
        ),
    ]
    return VIOLATION_LINE_SEPARATOR.join(all_violations) if all_violations else None


def widget_anchor_violation(tool_name: str, all_tool_input: dict[str, object]) -> str | None:
    """Return the deny reason for an anchor link inside widget code."""
    if not tool_name.endswith(WIDGET_TOOL_NAME_SUFFIX):
        return None
    serialized_input = json.dumps(all_tool_input)
    return WIDGET_ANCHOR_MESSAGE if WIDGET_ANCHOR_PATTERN.search(serialized_input) else None


def widget_flowchart_advice(
    tool_name: str, all_tool_input: dict[str, object], rules: VisualReplyRules
) -> str | None:
    """Return the advice for widget code that is not a flowchart, else None.

    The gate passes this advice to the session and still allows the call.

    A flowchart widget is one SVG with at least one arrow marker and one
    diamond shape for a yes or no check. Shapes inside a ``<marker>`` block
    are arrowheads, so they never count as the diamond::

        <svg><path d="M0 0L9 5L0 9L-9 5Z"/><path marker-end="url(#a)"/></svg>
    """
    all_rule_keys = {each.key for each in rules.all_rules}
    if not tool_name.endswith(WIDGET_TOOL_NAME_SUFFIX) or FLOWCHART_RULE_KEY not in all_rule_keys:
        return None
    widget_code = all_tool_input.get(WIDGET_CODE_KEY)
    if widget_code is None:
        widget_input = all_tool_input.get(WIDGET_INPUT_KEY)
        widget_code = widget_input.get(WIDGET_CODE_KEY) if isinstance(widget_input, dict) else None
    code_text = FLOWCHART_MARKER_BLOCK_PATTERN.sub(
        "", widget_code if isinstance(widget_code, str) else ""
    )
    all_shape_patterns = (FLOWCHART_SVG_PATTERN, FLOWCHART_ARROW_PATTERN, FLOWCHART_DIAMOND_PATTERN)
    if all(each_pattern.search(code_text) for each_pattern in all_shape_patterns):
        return None
    return NOT_FLOWCHART_MESSAGE.format(reminder=rules.reminder(FLOWCHART_RULE_KEY))


def _parsed_entries(all_transcript_lines: Iterable[str]) -> list[dict[str, object]]:
    all_entries = []
    for each_line in all_transcript_lines:
        try:
            parsed_entry = json.loads(each_line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed_entry, dict):
            all_entries.append(parsed_entry)
    return all_entries


def _is_prompt_entry(all_entry_fields: dict[str, object]) -> bool:
    if all_entry_fields.get(ENTRY_TYPE_KEY) != USER_ENTRY_TYPE or all_entry_fields.get(IS_META_KEY):
        return False
    message = all_entry_fields.get(MESSAGE_KEY)
    content = message.get(CONTENT_KEY) if isinstance(message, dict) else None
    if isinstance(content, str):
        return bool(content.strip())
    return isinstance(content, list) and any(
        isinstance(each_block, dict) and each_block.get(BLOCK_TYPE_KEY) == TEXT_BLOCK_TYPE
        for each_block in content
    )


def _content_blocks(all_entry_fields: dict[str, object], entry_type: str) -> list[dict[str, object]]:
    if all_entry_fields.get(ENTRY_TYPE_KEY) != entry_type:
        return []
    message = all_entry_fields.get(MESSAGE_KEY)
    content = message.get(CONTENT_KEY) if isinstance(message, dict) else None
    return [each for each in (content if isinstance(content, list) else []) if isinstance(each, dict)]


def _tool_uses(all_entry_fields: dict[str, object]) -> list[dict[str, object]]:
    return [
        each_block
        for each_block in _content_blocks(all_entry_fields, ASSISTANT_ENTRY_TYPE)
        if each_block.get(BLOCK_TYPE_KEY) == TOOL_USE_BLOCK_TYPE
    ]


def _entries_this_turn(all_transcript_lines: Iterable[str]) -> list[dict[str, object]]:
    all_entries = _parsed_entries(all_transcript_lines)
    last_prompt_index = max(
        (index for index, each in enumerate(all_entries) if _is_prompt_entry(each)), default=-1
    )
    return all_entries[last_prompt_index + 1 :]


def _read_transcript_lines(transcript_path: object) -> list[str] | None:
    if not isinstance(transcript_path, str):
        return None
    try:
        return Path(transcript_path).read_text(encoding=TRANSCRIPT_ENCODING).splitlines()
    except OSError:
        return None


def _result_blocks(all_entries: Iterable[dict[str, object]], is_error: bool) -> Iterator[dict[str, object]]:
    return (
        each_block
        for each_entry in all_entries
        for each_block in _content_blocks(each_entry, USER_ENTRY_TYPE)
        if each_block.get(BLOCK_TYPE_KEY) == TOOL_RESULT_BLOCK_TYPE
        and bool(each_block.get(IS_ERROR_KEY)) is is_error
    )


def _result_ids(all_entries: list[dict[str, object]], is_error: bool) -> set[object]:
    return {each_block.get(TOOL_USE_ID_KEY) for each_block in _result_blocks(all_entries, is_error)}


def _result_texts(result_content: object) -> list[str]:
    if isinstance(result_content, str):
        return [result_content]
    return [
        each_block[BLOCK_TEXT_KEY]
        for each_block in (result_content if isinstance(result_content, list) else [])
        if isinstance(each_block, dict) and isinstance(each_block.get(BLOCK_TEXT_KEY), str)
    ]


def successful_result_text(transcript_path: object) -> str | None:
    """Join the text of every tool result in the session that came back without an error.

    A subagent's report is the result of its Agent call, so it counts. Returns None
    when the transcript cannot be read.
    """
    all_lines = _read_transcript_lines(transcript_path)
    if all_lines is None:
        return None
    return RESULT_TEXT_SEPARATOR.join(
        each_text
        for each_block in _result_blocks(_parsed_entries(all_lines), is_error=False)
        for each_text in _result_texts(each_block.get(CONTENT_KEY))
    )


def visual_shown_this_turn(all_transcript_lines: Iterable[str]) -> bool:
    """Return True when a widget or page call after the last prompt did not come back with an error."""
    all_entries = _entries_this_turn(all_transcript_lines)
    all_errored_ids = _result_ids(all_entries, is_error=True)
    return any(
        str(each_use.get(BLOCK_NAME_KEY)).endswith(ALL_VISUAL_TOOL_NAME_SUFFIXES)
        and each_use.get(BLOCK_ID_KEY) not in all_errored_ids
        for each_entry in all_entries
        for each_use in _tool_uses(each_entry)
    )


def replies_sent_this_turn(all_transcript_lines: Iterable[str]) -> int:
    """Count the reply calls after the last prompt that came back without an error."""
    all_entries = _entries_this_turn(all_transcript_lines)
    all_delivered_ids = _result_ids(all_entries, is_error=False)
    return sum(
        1
        for each_entry in all_entries
        for each_use in _tool_uses(each_entry)
        if str(each_use.get(BLOCK_NAME_KEY)).endswith(ALL_REPLY_TOOL_NAME_SUFFIXES)
        and each_use.get(BLOCK_ID_KEY) in all_delivered_ids
    )


def second_reply_violation(transcript_path: object, rules: VisualReplyRules) -> str | None:
    """Return the deny reason for a reply when this turn already delivered one."""
    all_lines = _read_transcript_lines(transcript_path)
    if all_lines is None or replies_sent_this_turn(all_lines) < MAXIMUM_REPLIES_PER_TURN:
        return None
    return SECOND_REPLY_MESSAGE.format(reminder=rules.reminder(ONE_ITEM_RULE_KEY))


def visual_violation(
    sentence_count: int, transcript_path: object, rules: VisualReplyRules
) -> str | None:
    """Return the deny reason for a reply of several sentences with no visual this turn."""
    if sentence_count <= MAXIMUM_SENTENCES_WITHOUT_VISUAL:
        return None
    all_lines = _read_transcript_lines(transcript_path)
    if all_lines is None or visual_shown_this_turn(all_lines):
        return None
    return NO_VISUAL_MESSAGE.format(
        sentence_count=sentence_count, reminder=rules.reminder(NO_PICTURE_RULE_KEY)
    )


def reports_results(prose_text: str) -> bool:
    """Return True when the prose holds a markdown table or more figures than a reply may state without a picture.

    The caller removes code spans, links, and URLs first, so figures inside them do not count.
    """
    if TABLE_SEPARATOR_PATTERN.search(prose_text):
        return True
    all_figures = FIGURE_PATTERN.findall(LIST_NUMBER_PATTERN.sub(" ", prose_text))
    return len(all_figures) > MAXIMUM_FIGURES_WITHOUT_PICTURE


def attaches_picture(reply_text: str, all_tool_input: dict[str, object]) -> bool:
    """Return True when the call attaches an image file or embeds a markdown picture outside code."""
    all_attached_outputs = all_tool_input.get(ATTACHED_OUTPUTS_KEY)
    has_attached_picture = isinstance(all_attached_outputs, list) and any(
        isinstance(each_output, dict)
        and each_output.get(OUTPUT_KIND_KEY) == OUTPUT_FILE_KIND
        and str(each_output.get(OUTPUT_REF_KEY, "")).casefold().endswith(ALL_PICTURE_SUFFIXES)
        for each_output in all_attached_outputs
    )
    without_code = INLINE_CODE_PATTERN.sub(" ", FENCED_BLOCK_PATTERN.sub(" ", reply_text))
    return has_attached_picture or MARKDOWN_PICTURE_PATTERN.search(without_code) is not None


def results_picture_violation(
    prose_text: str,
    reply_text: str,
    all_tool_input: dict[str, object],
    rules: VisualReplyRules | None,
) -> str | None:
    """Return the deny reason for a reply that reports results with no picture attached, or None."""
    if rules is None or not reports_results(prose_text) or attaches_picture(reply_text, all_tool_input):
        return None
    return RESULTS_PICTURE_MESSAGE.format(reminder=rules.reminder(RESULTS_PICTURE_RULE_KEY))
