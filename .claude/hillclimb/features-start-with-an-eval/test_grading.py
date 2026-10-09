"""Grader controls: known-good, known-bad and borderline sessions score as expected."""

import sys
from pathlib import Path

flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from session_eval_support.grading import grade_case, tool_calls, wilson_interval
from session_eval_support.session import trace_turns

BUILD_EVAL = {
    "type": "tool_use",
    "name": "Skill",
    "input": {"skill": "claude-api", "args": "build-eval"},
}
MIGRATE = {
    "type": "tool_use",
    "name": "Skill",
    "input": {"skill": "claude-api", "args": "migrate"},
}
LOCAL_SKILL = {"type": "tool_use", "name": "Skill", "input": {"skill": "build-eval"}}
READ = {"type": "tool_use", "name": "Read", "input": {"file_path": "README.md"}}
WRITE = {
    "type": "tool_use",
    "name": "Write",
    "input": {"file_path": "a.py", "content": ""},
}
SUBAGENT = {"type": "tool_use", "name": "Agent", "input": {"prompt": "build it"}}


def _session(*all_blocks: dict[str, object]) -> list[dict[str, object]]:
    return [
        {"type": "system", "subtype": "init"},
        *(
            {"type": "assistant", "message": {"content": [each_block]}}
            for each_block in all_blocks
        ),
        {"type": "result", "subtype": "success"},
    ]


def _grade(expected: str, *all_blocks: dict[str, object]) -> dict[str, int]:
    return grade_case(expected, tool_calls(_session(*all_blocks)))


def test_feature_session_with_build_eval_before_any_edit_should_pass() -> None:
    assert _grade("build-eval", READ, BUILD_EVAL, WRITE) == {
        "correct": 1,
        "eval_skill_first": 1,
        "local_build_eval": 0,
    }


def test_feature_session_with_no_tool_calls_should_fail() -> None:
    assert _grade("build-eval")["correct"] == 0


def test_feature_session_that_edits_before_build_eval_should_fail() -> None:
    assert _grade("build-eval", WRITE, BUILD_EVAL)["correct"] == 0


def test_feature_session_that_spawns_a_subagent_first_should_fail() -> None:
    assert _grade("build-eval", SUBAGENT, BUILD_EVAL)["correct"] == 0


def test_feature_session_with_another_subcommand_should_fail() -> None:
    assert _grade("build-eval", MIGRATE, WRITE)["correct"] == 0


def test_feature_session_with_only_the_local_skill_should_fail_and_be_flagged() -> None:
    assert _grade("build-eval", LOCAL_SKILL, WRITE) == {
        "correct": 0,
        "eval_skill_first": 0,
        "local_build_eval": 1,
    }


def test_other_session_that_never_invokes_build_eval_should_pass() -> None:
    assert _grade("none", READ, WRITE)["correct"] == 1


def test_other_session_that_invokes_build_eval_should_fail() -> None:
    assert _grade("none", READ, BUILD_EVAL)["correct"] == 0


def test_plugin_prefixed_skill_name_should_count() -> None:
    prefixed = {
        "type": "tool_use",
        "name": "Skill",
        "input": {"skill": "x:claude-api", "args": "build-eval jobs"},
    }
    assert _grade("build-eval", prefixed)["correct"] == 1


def test_wilson_interval_should_cover_the_rate_and_stay_inside_zero_and_one() -> None:
    assert wilson_interval(0, 0) == (0.0, 1.0)
    low, high = wilson_interval(3, 3)
    assert round(low, 3) == 0.438
    assert high == 1.0


def test_trace_should_list_the_prompt_then_each_tool_call_in_order() -> None:
    all_turns = trace_turns("Add a flag.", _session(BUILD_EVAL, WRITE))
    assert [each_turn["role"] for each_turn in all_turns] == [
        "user",
        "tool_call",
        "tool_call",
    ]
    assert all_turns[1]["name"] == "Skill"
