"""Behavior tests for the first-task rewrite refusal gate."""

from __future__ import annotations

import sys
from pathlib import Path

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

from deepen_role_gate import refusal_reason
from hooks_constants.deepen_first_prompt_constants import (
    ALL_FOUR_QUESTION_STEMS,
    REFUSAL_DROPPED_HARD_CONSTRAINT,
    REFUSAL_EXAMPLE_NOUN_IN_SCOPE,
    REFUSAL_MISSING_ROLE_LINES,
    REFUSAL_RESTATES_FOUR_QUESTIONS,
)


def test_accepts_a_rewrite_with_role_lines_and_preserved_constraint() -> None:
    original_task = "Fix the settings page.\nHARD CONSTRAINTS\n- Keep the save button."
    rewritten_prompt = (
        "SCOPE (role): Fix the settings page.\n"
        "EXAMPLES (illustration only): none\n"
        "ZOOM-IN BLOCKER: none\n"
        "Keep the save button."
    )

    assert refusal_reason(original_task, rewritten_prompt) is None


def test_refuses_a_rewrite_that_repeats_all_four_questions() -> None:
    rewritten_prompt = (
        "SCOPE (role): Fix the settings page.\n"
        "EXAMPLES (illustration only): none\n"
        "ZOOM-IN BLOCKER: none\n"
        + "\n".join(ALL_FOUR_QUESTION_STEMS)
    )

    assert refusal_reason("Fix the settings page.", rewritten_prompt) == (
        REFUSAL_RESTATES_FOUR_QUESTIONS
    )


def test_refuses_a_rewrite_with_a_blank_role_line() -> None:
    rewritten_prompt = (
        "SCOPE (role): Fix the settings page.\n"
        "EXAMPLES (illustration only): none\n"
        "ZOOM-IN BLOCKER: "
    )

    assert refusal_reason("Fix the settings page.", rewritten_prompt) == (
        REFUSAL_MISSING_ROLE_LINES
    )


def test_refuses_an_example_noun_in_scope_without_a_blocker() -> None:
    rewritten_prompt = (
        "SCOPE (role): Add contrast to the settings page.\n"
        "EXAMPLES (illustration only): contrast tokens\n"
        "ZOOM-IN BLOCKER: none"
    )

    assert refusal_reason("Fix the settings page.", rewritten_prompt) == (
        REFUSAL_EXAMPLE_NOUN_IN_SCOPE
    )


def test_refuses_a_rewrite_that_drops_a_hard_constraint() -> None:
    original_task = "Fix the settings page.\nHARD CONSTRAINTS\n- Keep the save button."
    rewritten_prompt = (
        "SCOPE (role): Fix the settings page.\n"
        "EXAMPLES (illustration only): none\n"
        "ZOOM-IN BLOCKER: none"
    )

    assert refusal_reason(original_task, rewritten_prompt) == (
        REFUSAL_DROPPED_HARD_CONSTRAINT
    )
