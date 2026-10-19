"""Trim the user's typed messages to their substance, with no model call.

::

    #1 "Could you please add the retry to the deploy script"
    #2 "ok"
    #3 "Change of plan, drop the retry from the deploy script"
    -> #1 add retry to deploy script (overruled by #3)
       #3 Change of plan, drop retry from deploy script

The trim drops filler phrases, articles, and HTML comments, and drops a
message that only acknowledges, such as ``ok`` or ``thanks``. An artifact
comment keeps its link, its anchor, and the quoted comment, and loses the
relay text around them. Text inside backticks and tokens
that hold a path, a link, or a version stay as typed. A message that reverses
an earlier one marks the earlier line it shares the most words with.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)
_session_directory = str(Path(__file__).resolve().parent)
if _session_directory not in sys.path:
    sys.path.insert(0, _session_directory)

from compaction_user_messages import TypedMessage
from hooks_constants.compaction_user_messages_constants import (
    ACKNOWLEDGMENT_WORD_PATTERN,
    ALL_ACKNOWLEDGMENT_WORDS,
    ALL_STOP_WORDS,
    ARTICLE_PATTERN,
    ARTIFACT_COMMENT_MARKER,
    ARTIFACT_COMMENT_TEMPLATE,
    ARTIFACT_LOCATION_PATTERN,
    ARTIFACT_LOCATION_TEMPLATE,
    ARTIFACT_QUOTE_GROUP,
    ARTIFACT_QUOTE_PATTERN,
    ARTIFACT_URL_PATTERN,
    CODE_SPAN_PATTERN,
    CONTENT_WORD_EDGE_PUNCTUATION,
    CONTENT_WORD_PATTERN,
    CUT_MESSAGE_SUFFIX_TEMPLATE,
    DANGLING_COMMA_PATTERN,
    FILLER_PATTERN,
    HTML_COMMENT_PATTERN,
    INTERRUPT_PATTERN,
    LEFT_OUT_LINES_TEMPLATE,
    LINE_SEPARATOR,
    MAXIMUM_ACKNOWLEDGMENT_WORDS,
    MAXIMUM_MESSAGE_CHARACTERS,
    MAXIMUM_RECALL_CHARACTERS,
    OVERRULED_SUFFIX_TEMPLATE,
    QUOTE_PREFIX_PATTERN,
    REVERSAL_PATTERN,
    SPACE_BEFORE_PUNCTUATION_PATTERN,
    TRIMMED_EDGE_CHARACTERS,
    TRIMMED_LINE_TEMPLATE,
    WHITESPACE_RUN_PATTERN,
)


def _is_acknowledgment(text: str) -> bool:
    if INTERRUPT_PATTERN.match(text.strip()):
        return True
    all_words = ACKNOWLEDGMENT_WORD_PATTERN.findall(text.casefold())
    return 0 < len(all_words) <= MAXIMUM_ACKNOWLEDGMENT_WORDS and set(all_words) <= (
        ALL_ACKNOWLEDGMENT_WORDS
    )


def _artifact_comment(text: str) -> str:
    if ARTIFACT_COMMENT_MARKER not in text:
        return text
    quote = ARTIFACT_QUOTE_PATTERN.search(text)
    url = ARTIFACT_URL_PATTERN.search(text)
    if quote is None or url is None:
        return text
    location = ARTIFACT_LOCATION_PATTERN.search(text)
    return ARTIFACT_COMMENT_TEMPLATE.format(
        url=url.group(1),
        location=(
            ARTIFACT_LOCATION_TEMPLATE.format(location=location.group(1).strip())
            if location
            else ""
        ),
        comment=QUOTE_PREFIX_PATTERN.sub("", quote.group(ARTIFACT_QUOTE_GROUP)).strip(),
    )


def _substance(text: str) -> str:
    return HTML_COMMENT_PATTERN.sub("", _artifact_comment(text))


def _trimmed_prose(prose: str) -> str:
    if CODE_SPAN_PATTERN.fullmatch(prose):
        return prose
    return ARTICLE_PATTERN.sub("", FILLER_PATTERN.sub("", prose))


def caveman_text(text: str) -> str:
    """Return the text without filler phrases and articles, spacing tidied.

    ::

        "Could you please add the retry to `the deploy.sh`"
        -> "add retry to `the deploy.sh`"

    Args:
        text: One typed message.

    Returns:
        The trimmed text; backtick spans and path-like tokens unchanged.
    """
    trimmed_text = "".join(
        _trimmed_prose(each_part) for each_part in CODE_SPAN_PATTERN.split(text)
    )
    single_spaced = WHITESPACE_RUN_PATTERN.sub(" ", trimmed_text)
    punctuated = SPACE_BEFORE_PUNCTUATION_PATTERN.sub(r"\1", single_spaced)
    return DANGLING_COMMA_PATTERN.sub("", punctuated).strip(TRIMMED_EDGE_CHARACTERS)


def _content_words(text: str) -> set[str]:
    all_words = {
        each_word.casefold().rstrip(CONTENT_WORD_EDGE_PUNCTUATION)
        for each_word in CONTENT_WORD_PATTERN.findall(text)
    }
    return all_words - ALL_STOP_WORDS


def _closest_earlier_position(
    all_later_words: set[str], all_earlier_words_by_position: list[tuple[int, set[str]]]
) -> int | None:
    best_position, best_overlap = None, 0
    for each_position, each_earlier_words in all_earlier_words_by_position:
        overlap = len(all_later_words & each_earlier_words)
        if overlap > best_overlap:
            best_position, best_overlap = each_position, overlap
    return best_position


def _overruled_by(all_kept_messages: list[TypedMessage]) -> dict[int, int]:
    later_position_by_earlier: dict[int, int] = {}
    all_words_by_position = [
        (each_message.position, _content_words(each_message.text))
        for each_message in all_kept_messages
    ]
    for each_index, each_message in enumerate(all_kept_messages):
        if not REVERSAL_PATTERN.search(each_message.text):
            continue
        earlier_position = _closest_earlier_position(
            all_words_by_position[each_index][1], all_words_by_position[:each_index]
        )
        if earlier_position is not None:
            later_position_by_earlier[earlier_position] = each_message.position
    return later_position_by_earlier


def _capped_text(text: str) -> str:
    if len(text) <= MAXIMUM_MESSAGE_CHARACTERS:
        return text
    cut_count = len(text) - MAXIMUM_MESSAGE_CHARACTERS
    return text[:MAXIMUM_MESSAGE_CHARACTERS] + CUT_MESSAGE_SUFFIX_TEMPLATE.format(
        cut_count=cut_count
    )


def _messages_with_content(all_messages: list[TypedMessage]) -> list[TypedMessage]:
    all_substance_messages = [
        replace(each_message, text=_substance(each_message.text)) for each_message in all_messages
    ]
    return [
        each_message
        for each_message in all_substance_messages
        if each_message.text.strip() and not _is_acknowledgment(each_message.text)
    ]


def _trimmed_line(message: TypedMessage, later_position: int | None) -> str:
    line = TRIMMED_LINE_TEMPLATE.format(
        position=message.position, text=_capped_text(caveman_text(message.text))
    )
    if later_position is None:
        return line
    return line + OVERRULED_SUFFIX_TEMPLATE.format(later_position=later_position)


def trimmed_lines(all_messages: list[TypedMessage]) -> list[str]:
    """Return one trimmed line per message that carries content, oldest first.

    ::

        [#1 "use Postgres", #2 "thanks", #3 "change of plan, SQLite over Postgres"]
        -> ["#1 use Postgres (overruled by #3)", "#3 change of plan, SQLite over Postgres"]

    Args:
        all_messages: Every typed message, oldest first.

    Returns:
        Lines that start with the message number; a reversed line ends with its marker.
    """
    all_kept_messages = _messages_with_content(all_messages)
    later_position_by_earlier = _overruled_by(all_kept_messages)
    return [
        _trimmed_line(each_message, later_position_by_earlier.get(each_message.position))
        for each_message in all_kept_messages
    ]


def _newest_lines_within(all_later_lines: list[str], character_budget: int) -> list[str]:
    all_kept_lines: list[str] = []
    remaining_characters = character_budget
    for each_line in reversed(all_later_lines):
        line_size = len(each_line) + len(LINE_SEPARATOR)
        if line_size > remaining_characters:
            break
        remaining_characters -= line_size
        all_kept_lines.append(each_line)
    return list(reversed(all_kept_lines))


def recall_text(all_messages: list[TypedMessage]) -> str | None:
    """Return the trimmed lines that fit the recall budget, or None when none exist.

    ::

        5 short messages          -> all 5 lines
        #1 plus 400 long messages -> #1, a left-out note, then the newest that fit

    The first line keeps the session's original ask. The newest lines carry
    the latest corrections, which override older asks.

    Args:
        all_messages: Every typed message, oldest first.

    Returns:
        The lines joined by newlines, at most ``MAXIMUM_RECALL_CHARACTERS`` long
        apart from the left-out note, or None.
    """
    all_lines = trimmed_lines(all_messages)
    if not all_lines:
        return None
    first_line, *all_later_lines = all_lines
    all_kept_later_lines = _newest_lines_within(
        all_later_lines, MAXIMUM_RECALL_CHARACTERS - len(first_line)
    )
    left_out_count = len(all_later_lines) - len(all_kept_later_lines)
    all_left_out_notes = (
        [LEFT_OUT_LINES_TEMPLATE.format(left_out_count=left_out_count)] if left_out_count else []
    )
    return LINE_SEPARATOR.join([first_line, *all_left_out_notes, *all_kept_later_lines])
