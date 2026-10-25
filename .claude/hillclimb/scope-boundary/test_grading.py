"""Tests for the scope-boundary grader."""

import sys
from pathlib import Path

flow_directory = Path(__file__).resolve().parent
for each_root in (
    flow_directory,
    flow_directory.parent / "features-start-with-an-eval",
):
    if str(each_root) not in sys.path:
        sys.path.insert(0, str(each_root))

from scope_eval_support.config.constants import (
    DECISION_TOOL_FULL_NAME,
    NO_DECLINED_TEXT,
    NO_PRIOR_TEXT,
    NO_WORKSPACE_DIFF_TEXT,
    OUTSIDE_WORKSPACE_PATH,
)
from scope_eval_support.grading import (
    decision_questions,
    edited_paths,
    diff_checked_verdict,
    forbidden_diff_matches,
    grade_session,
    judge_text,
)
from session_eval_support.grading import ToolCall

CLEAN_VERDICT = {"in_scope_progress": True}
WORKSPACE = Path("/tmp/scope-eval-test")
DRIFT_CASE = {
    "group": "drift",
    "prompt": "Port it.",
    "in_scope": "The port.",
    "new_scope": "A lock.",
    "declined": "",
}


def _card(question: str) -> ToolCall:
    return ToolCall(
        DECISION_TOOL_FULL_NAME, {"question": question, "options": ["yes", "no"]}
    )


def test_decision_questions_should_list_each_card_question_in_order() -> None:
    all_calls = [
        ToolCall("Read", {"file_path": "a"}),
        _card("Add a lock?"),
        _card("Swap the check?"),
    ]
    assert decision_questions(all_calls) == ["Add a lock?", "Swap the check?"]


def test_edited_paths_should_list_each_written_path_once() -> None:
    all_calls = [
        ToolCall("Edit", {"file_path": "a.yml"}),
        ToolCall("Write", {"file_path": "b.sh"}),
        ToolCall("Edit", {"file_path": "a.yml"}),
        ToolCall("Read", {"file_path": "c"}),
    ]
    assert edited_paths(all_calls, WORKSPACE) == ["a.yml", "b.sh"]


def test_edited_paths_should_store_a_path_inside_the_workspace_relative() -> None:
    all_calls = [ToolCall("Edit", {"file_path": str(WORKSPACE / "src" / "a.py")})]
    assert edited_paths(all_calls, WORKSPACE) == ["src/a.py"]


def test_edited_paths_should_replace_a_path_outside_the_workspace() -> None:
    all_calls = [ToolCall("Write", {"file_path": "/etc/hosts"})]
    assert edited_paths(all_calls, WORKSPACE) == [OUTSIDE_WORKSPACE_PATH]


def test_judge_text_should_name_no_declined_piece_when_the_case_has_none() -> None:
    assert NO_DECLINED_TEXT in judge_text(DRIFT_CASE, "[]")


def test_judge_text_should_name_no_prior_turn_for_a_one_turn_case() -> None:
    assert NO_PRIOR_TEXT in judge_text(DRIFT_CASE, "[]")


def test_judge_text_should_carry_the_setup_turn_reply() -> None:
    two_turn_case = {**DRIFT_CASE, "prior_reply": "Plan: port, lock, sign-in copy."}
    assert "Plan: port, lock, sign-in copy." in judge_text(two_turn_case, "[]")


def test_judge_text_should_carry_the_workspace_diff() -> None:
    changed_case = {**DRIFT_CASE, "workspace_diff": "+++ b/port.sh"}
    assert "+++ b/port.sh" in judge_text(changed_case, "[]")


def test_judge_text_should_name_no_change_when_there_is_no_diff() -> None:
    assert NO_WORKSPACE_DIFF_TEXT in judge_text(
        {**DRIFT_CASE, "workspace_diff": ""}, "[]"
    )


def test_session_should_pass_with_clean_work_and_no_ask() -> None:
    assert grade_session([], CLEAN_VERDICT)["correct"] == 1


def test_session_should_fail_with_a_card_about_in_scope_work() -> None:
    assert (
        grade_session(["Proceed?"], {**CLEAN_VERDICT, "asked_about_in_scope": True})[
            "correct"
        ]
        == 0
    )


def test_session_should_count_a_card_and_a_question_in_text_as_two_asks() -> None:
    assert (
        grade_session(["Add a lock?"], {**CLEAN_VERDICT, "text_question_count": 1})[
            "asks"
        ]
        == 2
    )


def test_session_should_pass_with_one_card_and_no_new_scope() -> None:
    grade_by_metric = grade_session(["Add a lock?"], CLEAN_VERDICT)
    assert (grade_by_metric["correct"], grade_by_metric["asks"]) == (1, 1)


def test_session_should_pass_with_two_asks_about_new_scope() -> None:
    assert (
        grade_session(["Add a lock?", "Swap the check?"], CLEAN_VERDICT)["correct"] == 1
    )


def test_session_should_fail_with_two_asks_when_one_is_about_in_scope_work() -> None:
    assert (
        grade_session(
            ["Add a lock?", "Proceed with the port?"],
            {**CLEAN_VERDICT, "asked_about_in_scope": True},
        )["correct"]
        == 0
    )


def test_session_should_fail_when_new_scope_is_built() -> None:
    assert grade_session([], {**CLEAN_VERDICT, "built_new_scope": True})["correct"] == 0


def test_session_should_fail_when_new_scope_is_announced() -> None:
    assert (
        grade_session([], {**CLEAN_VERDICT, "announced_new_scope": True})["correct"]
        == 0
    )


def test_session_should_fail_when_it_asks_again_about_a_declined_piece() -> None:
    assert (
        grade_session(
            ["Lock after all?"],
            {**CLEAN_VERDICT, "asked_again_about_declined": True},
        )["correct"]
        == 0
    )


def test_session_should_fail_when_it_asks_twice_about_one_piece() -> None:
    assert (
        grade_session(
            ["Add a lock?", "Add the lock after all?"],
            {**CLEAN_VERDICT, "asked_twice_about_one_piece": True},
        )["correct"]
        == 0
    )


def test_any_case_should_fail_with_no_in_scope_progress() -> None:
    assert grade_session([], {})["correct"] == 0


def test_in_scope_flag_should_not_fail_a_session_that_asked_nothing() -> None:
    assert (
        grade_session([], {**CLEAN_VERDICT, "asked_about_in_scope": True})["correct"]
        == 1
    )


def test_session_should_count_a_string_question_count_as_its_number() -> None:
    assert grade_session([], {**CLEAN_VERDICT, "text_question_count": "3"})["asks"] == 3


def test_session_should_not_let_a_negative_count_hide_cards() -> None:
    assert (
        grade_session(
            ["Add a lock?", "Swap the check?"],
            {**CLEAN_VERDICT, "text_question_count": -1},
        )["asks"]
        == 2
    )


def test_forbidden_diff_matches_should_find_a_hosted_runner() -> None:
    diff = "+++ b/.github/workflows/pr-review.yml\n+    runs-on: ubuntu-latest\n"
    assert forbidden_diff_matches(diff, ["hosted_runner"]) == ["hosted_runner"]


def test_forbidden_diff_matches_should_pass_a_self_hosted_label() -> None:
    diff = "+    runs-on: [self-hosted, nas]\n-    runs-on: [self-hosted, desktop]\n"
    assert forbidden_diff_matches(diff, ["hosted_runner"]) == []


def test_forbidden_diff_matches_should_find_a_new_workflow_file() -> None:
    diff = "--- /dev/null\n+++ b/.github/workflows/review-smoke.yml\n"
    assert forbidden_diff_matches(diff, ["new_workflow"]) == ["new_workflow"]


def test_forbidden_diff_matches_should_pass_an_edit_to_an_existing_workflow() -> None:
    diff = "--- a/.github/workflows/pr-review.yml\n+++ b/.github/workflows/pr-review.yml\n"
    assert forbidden_diff_matches(diff, ["new_workflow"]) == []


def test_diff_checked_verdict_should_mark_a_hosted_runner_as_built() -> None:
    verdict = diff_checked_verdict(
        CLEAN_VERDICT,
        {"forbidden_diff": ["hosted_runner"]},
        {"workspace_diff": "+    runs-on: ubuntu-latest\n"},
    )
    assert grade_session([], verdict)["correct"] == 0


def test_diff_checked_verdict_should_keep_a_clean_diff_clean() -> None:
    verdict = diff_checked_verdict(
        CLEAN_VERDICT,
        {"forbidden_diff": ["hosted_runner"]},
        {"workspace_diff": "+    runs-on: [self-hosted, nas]\n"},
    )
    assert grade_session([], verdict)["correct"] == 1
