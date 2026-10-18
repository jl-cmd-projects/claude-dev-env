"""Refusal checks for a first-task rewrite.

The rewriter lives in ``deepen_first_prompt.py``. This module only scores a
candidate. A grader imports ``refusal_reason`` and does not rewrite.
"""

from __future__ import annotations

import re

from hooks_constants.deepen_first_prompt_constants import (
    ALL_EXAMPLE_NOUN_STOPWORDS,
    ALL_FOUR_QUESTION_STEMS,
    EXAMPLE_NOUN_PATTERN,
    HARD_CONSTRAINTS_LABEL,
    REFUSAL_DROPPED_HARD_CONSTRAINT,
    REFUSAL_EXAMPLE_NOUN_IN_SCOPE,
    REFUSAL_MISSING_ROLE_LINES,
    REFUSAL_RESTATES_FOUR_QUESTIONS,
    ROLE_BLOCKER_LABEL,
    ROLE_BLOCKER_NONE,
    ROLE_EXAMPLES_LABEL,
    ROLE_SCOPE_LABEL,
)


def _labeled_text(rewritten_prompt: str, label: str) -> str | None:
    """Return the text after ``label`` on its line, or None when the line is absent."""
    prefix = label
    for each_line in rewritten_prompt.splitlines():
        stripped_line = each_line.strip()
        if stripped_line.startswith(prefix):
            return stripped_line[len(prefix) :].strip()
    return None


def _restates_four_questions(rewritten_prompt: str) -> bool:
    """Return True when the rewrite pastes every canonical question stem."""
    return all(each_stem in rewritten_prompt for each_stem in ALL_FOUR_QUESTION_STEMS)


def _role_lines_are_missing(rewritten_prompt: str) -> bool:
    """Return True when any of the three role lines is absent or blank."""
    for each_label in (ROLE_SCOPE_LABEL, ROLE_EXAMPLES_LABEL, ROLE_BLOCKER_LABEL):
        labeled_text = _labeled_text(rewritten_prompt, each_label)
        if labeled_text is None or not labeled_text:
            return True
    return False


def _example_nouns(examples_text: str) -> frozenset[str]:
    """Return content words from the examples line. ``none`` yields an empty set."""
    if examples_text.strip().rstrip(".").lower() == ROLE_BLOCKER_NONE:
        return frozenset()
    noun_pattern = re.compile(EXAMPLE_NOUN_PATTERN)
    return frozenset(
        each_match.group(0).lower()
        for each_match in noun_pattern.finditer(examples_text)
        if each_match.group(0).lower() not in ALL_EXAMPLE_NOUN_STOPWORDS
    )


def _scope_names_example_noun(scope_text: str, examples_text: str, blocker_text: str) -> bool:
    """Return True when the scope line names an example noun and the blocker is none."""
    if blocker_text.strip().rstrip(".").lower() != ROLE_BLOCKER_NONE:
        return False
    for each_noun in _example_nouns(examples_text):
        if re.search(
            rf"(?i)(?<![A-Za-z0-9]){re.escape(each_noun)}(?![A-Za-z0-9])",
            scope_text,
        ):
            return True
    return False


def _constraint_sentences(original_task: str) -> tuple[str, ...]:
    """Return bullet sentences under the hard-constraints heading."""
    collecting = False
    all_sentences: list[str] = []
    for each_line in original_task.splitlines():
        stripped_line = each_line.strip()
        if not collecting:
            if stripped_line.upper().startswith(HARD_CONSTRAINTS_LABEL):
                collecting = True
            continue
        if stripped_line.startswith("- "):
            all_sentences.append(stripped_line[2:].strip())
            continue
        if stripped_line == "" and not all_sentences:
            continue
        break
    return tuple(all_sentences)


def _rewrite_line_bodies(rewritten_prompt: str) -> frozenset[str]:
    """Return each rewrite line with a leading bullet marker removed."""
    all_bodies: set[str] = set()
    for each_line in rewritten_prompt.splitlines():
        stripped_line = each_line.strip()
        if stripped_line.startswith("- "):
            all_bodies.add(stripped_line[2:].strip())
        elif stripped_line:
            all_bodies.add(stripped_line)
    return frozenset(all_bodies)


def _dropped_hard_constraint(original_task: str, rewritten_prompt: str) -> bool:
    """Return True when a hard-constraint sentence is absent as its own line."""
    rewrite_bodies = _rewrite_line_bodies(rewritten_prompt)
    return any(
        each_sentence not in rewrite_bodies for each_sentence in _constraint_sentences(original_task)
    )


def refusal_reason(original_task: str, rewritten_prompt: str) -> str | None:
    """Return the refusal reason for one candidate rewrite, or None when it can ship.

    Args:
        original_task: The task text the rewrite must keep constraints from.
        rewritten_prompt: The candidate worker prompt.

    Returns:
        A refusal reason string, or None when the candidate passes.
    """
    if _restates_four_questions(rewritten_prompt):
        return REFUSAL_RESTATES_FOUR_QUESTIONS
    if _role_lines_are_missing(rewritten_prompt):
        return REFUSAL_MISSING_ROLE_LINES
    scope_text = _labeled_text(rewritten_prompt, ROLE_SCOPE_LABEL) or ""
    examples_text = _labeled_text(rewritten_prompt, ROLE_EXAMPLES_LABEL) or ""
    blocker_text = _labeled_text(rewritten_prompt, ROLE_BLOCKER_LABEL) or ""
    if _scope_names_example_noun(scope_text, examples_text, blocker_text):
        return REFUSAL_EXAMPLE_NOUN_IN_SCOPE
    if _dropped_hard_constraint(original_task, rewritten_prompt):
        return REFUSAL_DROPPED_HARD_CONSTRAINT
    return None
