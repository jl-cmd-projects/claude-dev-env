"""Tests for the role-shaped default rewrite."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from deepen_default_rewrite import role_default_rewrite
from deepen_role_gate import refusal_reason
from hooks_constants.deepen_first_prompt_constants import ALL_FOUR_QUESTION_STEMS, DEEPEN_MARKER


def _role_line(rewrite: str, label: str) -> str:
    return next(each for each in rewrite.splitlines() if each.startswith(label))[len(label) :].strip()


def test_should_pass_the_gate_for_a_plain_task() -> None:
    task = "Add dark mode to the settings page"
    rewrite = role_default_rewrite(task)
    assert rewrite.startswith(DEEPEN_MARKER)
    assert refusal_reason(task, rewrite) is None
    assert _role_line(rewrite, "SCOPE (role):") == task
    assert _role_line(rewrite, "EXAMPLES (illustration only):") == "none"


def test_should_not_paste_the_four_question_stems() -> None:
    rewrite = role_default_rewrite("Add dark mode to the settings page")
    assert not any(each_stem in rewrite for each_stem in ALL_FOUR_QUESTION_STEMS)


def test_should_move_a_marked_example_out_of_the_scope() -> None:
    task = "fix the flaky tests, e.g. test_auth and test_cache, and keep CI fast"
    rewrite = role_default_rewrite(task)
    assert refusal_reason(task, rewrite) is None
    assert _role_line(rewrite, "SCOPE (role):") == "fix the flaky tests and keep CI fast"
    assert _role_line(rewrite, "EXAMPLES (illustration only):") == "test_auth and test_cache"


def test_should_ask_before_narrowing_when_the_scope_names_the_example() -> None:
    task = "Fix the login failure. For example, the login failure on Safari."
    rewrite = role_default_rewrite(task)
    assert refusal_reason(task, rewrite) is None
    assert _role_line(rewrite, "ZOOM-IN BLOCKER:").startswith("the scope names something")


def test_should_keep_every_hard_constraint_line() -> None:
    task = "Keep the build green. For example, the login failure.\n\nHARD CONSTRAINTS\n- Never open a pull request.\n"
    rewrite = role_default_rewrite(task)
    assert refusal_reason(task, rewrite) is None
    assert "- Never open a pull request." in rewrite.splitlines()


def test_should_keep_every_task_sentence_in_scope_when_the_task_opens_with_context() -> None:
    task = "We have a Django app. Add CSV export to the reports page, e.g. the monthly sales report, and keep the existing URLs."
    rewrite = role_default_rewrite(task)
    assert refusal_reason(task, rewrite) is None
    assert _role_line(rewrite, "SCOPE (role):") == (
        "We have a Django app. Add CSV export to the reports page and keep the existing URLs."
    )
    assert _role_line(rewrite, "EXAMPLES (illustration only):") == "the monthly sales report"


def test_should_clip_a_long_scope_and_point_at_the_full_task() -> None:
    task = "Refactor the module. " * 40
    rewrite = role_default_rewrite(task.strip())
    scope = _role_line(rewrite, "SCOPE (role):")
    assert scope.endswith("(the rest is in the task below)")
    assert len(scope) < len(task)
    assert refusal_reason(task.strip(), rewrite) is None


def test_should_keep_a_marker_word_inside_a_longer_word_in_the_scope() -> None:
    task = "Search the codebase for examples of deprecated API calls and replace each one with the new client."
    rewrite = role_default_rewrite(task)
    assert refusal_reason(task, rewrite) is None
    assert _role_line(rewrite, "SCOPE (role):") == task
    assert _role_line(rewrite, "EXAMPLES (illustration only):") == "none"
    assumption_task = "Avoid such assumptions in the parser and add input validation."
    assert _role_line(role_default_rewrite(assumption_task), "SCOPE (role):") == assumption_task


def test_should_move_every_marked_example_in_a_sentence_out_of_the_scope() -> None:
    task = "Speed up the slow pages such as the dashboard, and cache reads, e.g. the user lookup, and keep the API stable."
    rewrite = role_default_rewrite(task)
    assert refusal_reason(task, rewrite) is None
    assert _role_line(rewrite, "SCOPE (role):") == "Speed up the slow pages and cache reads and keep the API stable."
    assert _role_line(rewrite, "EXAMPLES (illustration only):") == "the dashboard; the user lookup"
