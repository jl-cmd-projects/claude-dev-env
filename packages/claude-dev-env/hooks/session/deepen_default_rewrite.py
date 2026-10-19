"""Role-shaped default rewrite for a first task when no rewrite command is set.

``refusal_reason`` in ``deepen_role_gate.py`` refuses a rewrite that pastes the
four question stems back at the worker, and one without the SCOPE, EXAMPLES,
and ZOOM-IN BLOCKER lines. The default rewrite is built to carry those lines,
so a first task deepens on every host with nothing configured: the scope is
the task's own sentences with the marked examples taken out, the examples are
the parts the task marks as examples, and the blocker asks for confirmation
when the scope names one of those examples.
"""

from __future__ import annotations

import re

from hooks_constants.deepen_default_rewrite_constants import (
    ALL_EXAMPLE_END_MARKERS,
    ALL_EXAMPLE_SENTENCE_MARKERS,
    DEFAULT_BLOCKER_TEMPLATE,
    DEFAULT_CLOSING_LINE,
    DEFAULT_SCOPE_MAX_CHARACTERS,
    DEFAULT_TASK_HEADING,
    EXAMPLE_LEAD_PUNCTUATION,
    EXAMPLE_LIST_SEPARATOR,
    EXAMPLE_MARKER_ALTERNATION_SEPARATOR,
    EXAMPLE_MARKER_PATTERN_TEMPLATE,
    SCOPE_CLIPPED_SUFFIX,
    SENTENCE_BREAK_PATTERN,
    WORD_SEPARATOR,
)
from hooks_constants.deepen_first_prompt_constants import (
    DEEPEN_MARKER,
    HARD_CONSTRAINTS_LABEL,
    REFUSAL_EXAMPLE_NOUN_IN_SCOPE,
    ROLE_BLOCKER_LABEL,
    ROLE_BLOCKER_NONE,
    ROLE_EXAMPLES_LABEL,
    ROLE_SCOPE_LABEL,
)
from deepen_role_gate import refusal_reason


def _body_before_constraints(task_text: str) -> str:
    all_body_lines: list[str] = []
    for each_line in task_text.splitlines():
        if each_line.strip().upper().startswith(HARD_CONSTRAINTS_LABEL):
            break
        all_body_lines.append(each_line)
    return WORD_SEPARATOR.join(WORD_SEPARATOR.join(all_body_lines).split())


def _sentences(body_text: str) -> list[str]:
    return [each.strip() for each in re.split(SENTENCE_BREAK_PATTERN, body_text) if each.strip()]


def _example_marker_pattern() -> re.Pattern[str]:
    alternatives = EXAMPLE_MARKER_ALTERNATION_SEPARATOR.join(re.escape(each_marker) for each_marker in ALL_EXAMPLE_SENTENCE_MARKERS)
    return re.compile(EXAMPLE_MARKER_PATTERN_TEMPLATE.format(alternatives=alternatives), re.IGNORECASE)


def _split_example(sentence: str) -> tuple[str, list[str]]:
    """Return the sentence without its marked examples, and the example texts.

    A marker counts only as a whole phrase, so "for examples of" and "such
    assumptions" stay in the scope. The earliest marker splits first, and the
    text after the example is split again for later markers.
    """
    marker_match = _example_marker_pattern().search(sentence)
    if marker_match is None:
        return sentence, []
    head = sentence[: marker_match.start()].rstrip(EXAMPLE_LEAD_PUNCTUATION + "(")
    tail = sentence[marker_match.end() :].lstrip(EXAMPLE_LEAD_PUNCTUATION)
    end_index = min(
        (tail.find(each_end) for each_end in ALL_EXAMPLE_END_MARKERS if tail.find(each_end) >= 0),
        default=len(tail),
    )
    example = tail[:end_index].rstrip(".!? ")
    remainder_scope, all_remainder_examples = _split_example(
        tail[end_index:].lstrip(EXAMPLE_LEAD_PUNCTUATION + ")")
    )
    all_examples = ([example] if example else []) + all_remainder_examples
    scope_part = f"{head} {remainder_scope}".strip() if head else ""
    return scope_part, all_examples


def _clipped(text: str) -> str:
    if len(text) <= DEFAULT_SCOPE_MAX_CHARACTERS:
        return text
    cut = text[:DEFAULT_SCOPE_MAX_CHARACTERS]
    kept = cut[: cut.rfind(" ")] if " " in cut else cut
    return f"{kept} {SCOPE_CLIPPED_SUFFIX}"


def _scope_and_examples(task_text: str) -> tuple[str, str]:
    all_splits = [_split_example(each) for each in _sentences(_body_before_constraints(task_text))]
    all_examples = [each_example for _, all_sentence_examples in all_splits for each_example in all_sentence_examples]
    all_scope_parts = [each_part for each_part, _ in all_splits if each_part]
    scope_text = WORD_SEPARATOR.join(all_scope_parts) or task_text.strip()
    examples_text = EXAMPLE_LIST_SEPARATOR.join(all_examples) if all_examples else ROLE_BLOCKER_NONE
    return _clipped(scope_text), examples_text


def _rewrite_with_blocker(scope: str, examples: str, blocker: str, task_text: str) -> str:
    return (
        f"{DEEPEN_MARKER}\n\n"
        f"{ROLE_SCOPE_LABEL} {scope}\n"
        f"{ROLE_EXAMPLES_LABEL} {examples}\n"
        f"{ROLE_BLOCKER_LABEL} {blocker}\n\n"
        f"{DEFAULT_TASK_HEADING}\n{task_text}\n\n"
        f"{DEFAULT_CLOSING_LINE}"
    )


def role_default_rewrite(task_text: str) -> str:
    """Return the default rewrite: role lines from the task, the task itself, and one closing order.

    Args:
        task_text: The first task with any leading /deepen removed.

    Returns:
        A rewrite that opens with the deepen marker and carries the three role lines.
    """
    scope, examples = _scope_and_examples(task_text)
    rewrite = _rewrite_with_blocker(scope, examples, ROLE_BLOCKER_NONE, task_text)
    if refusal_reason(task_text, rewrite) != REFUSAL_EXAMPLE_NOUN_IN_SCOPE:
        return rewrite
    blocker = DEFAULT_BLOCKER_TEMPLATE.format(examples=examples)
    return _rewrite_with_blocker(scope, examples, blocker, task_text)
