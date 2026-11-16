"""Behavior tests for the auto mode rule flow case runner and its calibration."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

eval_directory = Path(__file__).resolve().parent
if str(eval_directory) not in sys.path:
    sys.path.insert(0, str(eval_directory))
import auto_mode_rule_flow_runner as runner

case_file_path = eval_directory / "auto_mode_rule_flow_cases.json"
allow_stub = eval_directory / "stub_allow_hook.py"
hold_stub = eval_directory / "stub_hold_hook.py"
today_refusal_hook = eval_directory.parent / "auto_mode_denial_quick_fix.py"


def _cases_by_id() -> dict[str, dict[str, object]]:
    return {
        str(each_case["id"]): each_case
        for each_case in runner.load_case_file(case_file_path)["cases"]
    }


def test_should_score_no_should_act_case_when_the_hooks_never_act() -> None:
    all_outcomes = runner.run_all_cases(case_file_path, allow_stub, allow_stub, ())
    summary = runner.score_summary(all_outcomes)
    assert summary["should_act_total"] > 0
    assert summary["should_act_passed"] == 0
    assert summary["errors"] == 0


def test_should_score_no_should_stay_quiet_case_when_the_hooks_always_record_and_hold() -> None:
    all_outcomes = runner.run_all_cases(case_file_path, hold_stub, hold_stub, ())
    summary = runner.score_summary(all_outcomes)
    assert summary["should_stay_quiet_total"] > 0
    assert summary["should_stay_quiet_passed"] == 0
    assert summary["errors"] == 0


def test_should_report_a_missing_stop_gate_as_an_error(tmp_path: Path) -> None:
    outcome = runner.run_case(
        _cases_by_id()["Q1"], today_refusal_hook, tmp_path / "missing_gate.py", {}
    )
    assert outcome.verdict == runner.ERROR_VERDICT


@pytest.mark.parametrize("case_id", ["R11", "R13", "R14"])
def test_should_keep_the_refusal_hook_output_equal_to_todays_output(case_id: str) -> None:
    all_today_outputs = runner.load_case_file(case_file_path)["today_outputs"]
    assert isinstance(all_today_outputs, dict)
    outcome = runner.run_case(
        _cases_by_id()[case_id], today_refusal_hook, allow_stub, all_today_outputs
    )
    assert outcome.verdict == runner.PASS_VERDICT, outcome.all_problems


def test_should_place_the_ledger_folder_under_the_config_directory(tmp_path: Path) -> None:
    assert (
        runner.ledger_directory_for(tmp_path, "s1")
        == tmp_path / "state" / "auto-mode-refusals" / "s1"
    )


def test_should_read_only_ledger_objects_that_carry_an_answer(tmp_path: Path) -> None:
    ledger_directory = runner.ledger_directory_for(tmp_path, "s1")
    ledger_directory.mkdir(parents=True)
    (ledger_directory / "entry.json").write_text(json.dumps({"answer": "kept"}), encoding="utf-8")
    (ledger_directory / "question.json").write_text(json.dumps({"question": "Q"}), encoding="utf-8")
    assert runner.read_ledger_answers(tmp_path, "s1") == {ledger_directory / "entry.json": "kept"}


def test_should_write_an_answered_question_the_way_a_transcript_stores_it() -> None:
    event = {
        "transcript": "ask",
        "questions": [{"question": "Q?", "answer": "Allow it"}],
        "timestamp": None,
    }
    call_record, result_record = runner.transcript_records_for(event, "toolu_1", "s1")
    assert call_record["message"]["content"][0]["name"] == "AskUserQuestion"
    assert result_record["toolUseResult"]["answers"] == {"Q?": "Allow it"}
    assert "timestamp" not in result_record


def test_should_count_passes_per_kind_and_errors_apart() -> None:
    all_outcomes = [
        runner.CaseOutcome("R1", runner.SHOULD_ACT_KIND, runner.PASS_VERDICT, ()),
        runner.CaseOutcome("R8", runner.SHOULD_STAY_QUIET_KIND, runner.FAIL_VERDICT, ()),
        runner.CaseOutcome("Q1", runner.SHOULD_ACT_KIND, runner.ERROR_VERDICT, ()),
    ]
    assert runner.score_summary(all_outcomes) == {
        "should_act_passed": 1,
        "should_act_total": 2,
        "should_stay_quiet_passed": 0,
        "should_stay_quiet_total": 1,
        "errors": 1,
    }


def test_should_report_no_calibration_problem_for_the_shipped_cases() -> None:
    assert runner.calibration_problems(case_file_path) == []


def test_should_report_a_should_act_case_that_a_quiet_hook_passes(tmp_path: Path) -> None:
    loose_case_file = tmp_path / "cases.json"
    loose_case_file.write_text(
        json.dumps(
            {
                "today_outputs": {},
                "cases": [
                    {
                        "id": "L1",
                        "kind": runner.SHOULD_ACT_KIND,
                        "summary": "No expectation, so every hook passes it.",
                        "events": [{"refusal": {"tool_name": "Bash", "tool_input": {}}}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    all_problems = runner.calibration_problems(loose_case_file)
    assert len(all_problems) == 1
    assert all_problems[0].startswith("stub_allow_hook.py is not calibrated")


def test_should_print_each_case_then_the_score_and_problems_only_when_verbose() -> None:
    all_outcomes = [
        runner.CaseOutcome("R1", runner.SHOULD_ACT_KIND, runner.FAIL_VERDICT, ("event 1: x",)),
    ]
    summary = runner.score_summary(all_outcomes)
    quiet_text = runner.report_text_for(all_outcomes, summary, False)
    assert quiet_text.splitlines() == [
        "R1    should act        fail",
        "should act passed 0 of 1; should stay quiet passed 0 of 0; errors 0",
        "A missing hook, an unexpected exit code or output that is not a JSON object counts as an error.",
    ]
    verbose_lines = runner.report_text_for(all_outcomes, summary, True).splitlines()
    assert verbose_lines[1] == "      event 1: x"
