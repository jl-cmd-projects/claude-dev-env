"""Find the pieces an author's own words name in a subject, a title, or a pull request body.

Three readers, each pure text in and pieces out::

    subject_pieces("fix(x): publish icons, put Tips on the tray")  -> ["publish icons", "put Tips on the tray"]
    subject_pieces("fix(x): darken or lighten the video")          -> []
    topic_bullets(body)       -> bold-led bullets under "What this does"
    proof_pair_count(body)    -> without/with pairs under "Proof in practice"

A subject names several pieces when its description joins two or more verb-led
clauses with commas, semicolons, or "and". An "and" or a comma inside a
"with ..." phrase joins objects, so it opens no clause. "or" never separates.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from blocking.body_flowchart import fenced_line_flags
from hooks_constants.pull_request_proof_constants import (
    NEXT_HEADING_PATTERN,
    PROOF_HEADING_PATTERN,
    WHAT_THIS_DOES_HEADING_PATTERN,
)
from hooks_constants.pieces_per_level_note_constants import (
    ALL_ADJUNCT_WORDS,
    ALL_LABEL_TOPICS,
    ALL_LEADING_ADVERBS,
    ALL_PIECE_VERBS,
    CLAUSE_SEPARATOR_PATTERN,
    CODE_SPAN_PATTERN,
    CONVENTIONAL_SUBJECT_PATTERN,
    DESCRIPTION_GROUP,
    MASKED_TEXT,
    MAXIMUM_PIECE_CHARACTERS,
    MINIMUM_CLAUSE_WORD_COUNT,
    MINIMUM_PIECE_COUNT,
    PARENTHESIS_PATTERN,
    PIECE_TRUNCATION_SUFFIX,
    PROOF_LEAD_CHARACTERS,
    PROOF_NUMBER_PATTERN,
    QUOTED_TEXT_PATTERN,
    REMOVED_TEXT,
    TOPIC_BULLET_PATTERN,
    TOPIC_EDGE_CHARACTERS,
    TOPIC_GROUP,
    WITH_LINE_PATTERN,
    WITH_SAME_LINE_PATTERN,
    WITHOUT_LINE_PATTERN,
    WORD_EDGE_CHARACTERS,
)


def _masked_description(description: str) -> str:
    masked_description = CODE_SPAN_PATTERN.sub(MASKED_TEXT, description)
    masked_description = PARENTHESIS_PATTERN.sub(REMOVED_TEXT, masked_description)
    return QUOTED_TEXT_PATTERN.sub(MASKED_TEXT, masked_description)


def _all_clauses(description: str) -> list[str]:
    all_clauses: list[str] = []
    for each_part in CLAUSE_SEPARATOR_PATTERN.split(_masked_description(description)):
        each_clause = each_part.strip()
        if not each_clause:
            continue
        if all_clauses and _is_unfinished(all_clauses[-1]):
            all_clauses[-1] = f"{all_clauses[-1]} {each_clause}"
            continue
        all_clauses.append(each_clause)
    return all_clauses


def _holds_adjunct(clause: str) -> bool:
    return any(each_word in ALL_ADJUNCT_WORDS for each_word in clause.lower().split())


def _has_only_verb_objects(clause: str) -> bool:
    all_words = [each_word.strip(WORD_EDGE_CHARACTERS) for each_word in clause.lower().split()]
    all_words_after_adverbs = all_words[_adverb_prefix_length(all_words) :]
    return (
        len(all_words_after_adverbs) > 1
        and all_words_after_adverbs[0] in ALL_PIECE_VERBS
        and all(each_word in ALL_PIECE_VERBS for each_word in all_words_after_adverbs[1:])
    )


def _is_unfinished(clause: str) -> bool:
    return _holds_adjunct(clause) or _has_only_verb_objects(clause)


def _is_verb_led(clause: str) -> bool:
    all_words = [each_word.strip(WORD_EDGE_CHARACTERS) for each_word in clause.lower().split()]
    first_index = _adverb_prefix_length(all_words)
    if first_index >= len(all_words) or all_words[first_index] not in ALL_PIECE_VERBS:
        return False
    return len(all_words) > MINIMUM_CLAUSE_WORD_COUNT or first_index > 0


def _adverb_prefix_length(all_words: list[str]) -> int:
    prefix_length = 0
    for each_word in all_words:
        if each_word not in ALL_LEADING_ADVERBS:
            break
        prefix_length += 1
    return prefix_length


def _shortened(piece: str) -> str:
    if len(piece) <= MAXIMUM_PIECE_CHARACTERS:
        return piece
    keep_length = MAXIMUM_PIECE_CHARACTERS - len(PIECE_TRUNCATION_SUFFIX)
    return piece[:keep_length].rstrip() + PIECE_TRUNCATION_SUFFIX


def subject_pieces(subject: str) -> list[str]:
    """Return the verb-led clauses of a conventional subject, or an empty list.

    ::

        "fix(x): always publish icons, put Tips on the tray" -> ["always publish icons", "put Tips on the tray"]
        "feat: add evals with frozen dataset and rerun runs"  -> []
        "publish icons, draw the label"                       -> []

    Args:
        subject: A commit subject line or a pull request title.

    Returns:
        Each verb-led clause in the author's words when there are at least
        two, else an empty list.
    """
    subject_match = CONVENTIONAL_SUBJECT_PATTERN.match(subject.strip())
    if subject_match is None:
        return []
    all_pieces = [
        _shortened(each_clause)
        for each_clause in _all_clauses(subject_match.group(DESCRIPTION_GROUP))
        if _is_verb_led(each_clause)
    ]
    return all_pieces if len(all_pieces) >= MINIMUM_PIECE_COUNT else []


def _heading_level(line: str, heading_pattern: str) -> int | None:
    heading_match = re.match(heading_pattern, line.strip(), re.IGNORECASE)
    return None if heading_match is None else len(heading_match.group(1))


def _is_section_end(line: str, heading_level: int) -> bool:
    next_level = _heading_level(line, NEXT_HEADING_PATTERN)
    return next_level is not None and next_level <= heading_level


def _section_lines(body: str, heading_pattern: str) -> list[str]:
    all_lines = body.splitlines()
    all_fenced_flags = fenced_line_flags(all_lines)
    all_heading_levels = [
        None if is_fenced else _heading_level(each_line, heading_pattern)
        for each_line, is_fenced in zip(all_lines, all_fenced_flags, strict=True)
    ]
    heading_index = next(
        (each_index for each_index, each_level in enumerate(all_heading_levels) if each_level),
        None,
    )
    if heading_index is None:
        return []
    heading_level = all_heading_levels[heading_index] or 0
    all_section_lines: list[str] = []
    for each_line, each_fenced_flag in zip(
        all_lines[heading_index + 1 :], all_fenced_flags[heading_index + 1 :], strict=True
    ):
        if each_fenced_flag:
            continue
        if _is_section_end(each_line, heading_level):
            break
        all_section_lines.append(each_line)
    return all_section_lines


def topic_bullets(body: str) -> list[str]:
    """Return the bold lead of each top-level bullet under "What this does".

    ::

        "## What this does\\n- **Always publish.** x\\n- **Tips.** y" -> ["Always publish", "Tips"]
        "## What this does\\n- **Before:** x\\n- **After:** y"       -> []

    Args:
        body: The pull request body.

    Returns:
        The topic of each bold-led bullet, with labels such as Before and
        After left out. Indented bullets and fenced text do not count.
    """
    all_topics = []
    for each_line in _section_lines(body, WHAT_THIS_DOES_HEADING_PATTERN):
        topic_match = TOPIC_BULLET_PATTERN.match(each_line)
        if topic_match is None:
            continue
        each_topic = topic_match.group(TOPIC_GROUP).strip(TOPIC_EDGE_CHARACTERS)
        if each_topic and each_topic.lower() not in ALL_LABEL_TOPICS:
            all_topics.append(each_topic)
    return all_topics


def _proof_line_text(line: str) -> str:
    stripped_line = line.strip(PROOF_LEAD_CHARACTERS)
    return PROOF_NUMBER_PATTERN.sub("", stripped_line).strip(PROOF_LEAD_CHARACTERS).lower()


def _proof_step(line_text: str, is_without_open: bool) -> tuple[int, bool]:
    if WITHOUT_LINE_PATTERN.match(line_text):
        is_pair_on_one_line = WITH_SAME_LINE_PATTERN.search(line_text) is not None
        return (1, False) if is_pair_on_one_line else (0, True)
    if is_without_open and WITH_LINE_PATTERN.match(line_text):
        return 1, False
    return 0, is_without_open


def proof_pair_count(body: str) -> int:
    """Return how many without/with pairs the "Proof in practice" section holds.

    A pair is a line that opens with "without" and the next line that opens
    with "with", or one line that holds both, such as "Without it x; with it y".
    Fenced text is quoted output and does not count.

    Args:
        body: The pull request body.
    """
    pair_count = 0
    is_without_open = False
    for each_line in _section_lines(body, PROOF_HEADING_PATTERN):
        added_pairs, is_without_open = _proof_step(_proof_line_text(each_line), is_without_open)
        pair_count += added_pairs
    return pair_count
