"""Check scoring boundaries that could otherwise inflate evaluation results."""

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "review_eval", Path(__file__).with_name("run.py")
)
RUN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN)


def finding(line=2, category="falsy-zero"):
    return {
        "line": line,
        "category": category,
        "failure_scenario": "zero gets replaced by three",
    }


def test_duplicate_findings_do_not_inflate_recall():
    case = RUN.cases()[0]
    result = RUN.grade(case, {"findings": [finding(), finding()]})
    assert result == {"tp": 1, "fp": 1, "fn": 0, "pass": False, "clean": False}


def test_wrong_location_counts_as_miss_and_false_alarm():
    result = RUN.grade(RUN.cases()[0], {"findings": [finding(line=1)]})
    assert (result["tp"], result["fp"], result["fn"]) == (0, 1, 1)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"findings": [finding(line=True)]},
        {"findings": [finding(category="style")]},
        {"findings": [{**finding(), "failure_scenario": " "}]},
    ],
)
def test_invalid_output_is_not_scored(response):
    with pytest.raises(ValueError):
        RUN.grade(RUN.cases()[0], response)


def test_infrastructure_failure_is_not_a_task_failure():
    summary = RUN.summarize([{"status": "infra_error"}])
    assert summary["scored"] == 0
    assert summary["pass_rate"] is None
    assert summary["infra_errors"] == 1


def test_heldout_groups_and_witnesses():
    values = RUN.cases()
    assert len(values) == 16
    for case in values:
        RUN.verify_witness(case)
        assert (
            json.dumps(case["expected"]) not in RUN.prompt(case, "review")
            or not case["expected"]
        )


def test_clean_controls_expose_false_positives():
    case = RUN.cases()[1]
    row = {"status": "scored", "grade": RUN.grade(case, {"findings": [finding()]})}
    summary = RUN.summarize([row])
    assert summary["false_positive_rate"] == 1
    assert summary["specificity"] == 0


@pytest.mark.parametrize(
    "events",
    [
        [],
        [{"type": "thread.started"}],
        [
            {"type": "thread.started"},
            {"type": "turn.completed"},
            {"item": {"type": "command_execution"}},
        ],
    ],
)
def test_incomplete_or_tool_using_trace_is_rejected(events):
    with pytest.raises(ValueError):
        RUN.validate_trace(events, {"findings": []})


def test_trace_and_saved_response_must_match():
    events = [
        {"type": "thread.started"},
        {"type": "turn.completed"},
        {"item": {"type": "agent_message", "text": '{"findings":[]}'}},
    ]
    RUN.validate_trace(events, {"findings": []})
    with pytest.raises(ValueError):
        RUN.validate_trace(events, {"findings": [finding()]})


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"status": "infra_error"}],
        [{"status": "output_error"}],
        [{"status": "scored", "grade": {"pass": False}}],
    ],
)
def test_unsuccessful_evaluation_exits_nonzero(rows):
    assert RUN.evaluation_exit_code(rows) == 1
