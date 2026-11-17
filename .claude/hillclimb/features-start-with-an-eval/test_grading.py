"""Grader controls: known-good, known-bad and borderline sessions score as expected."""

import sys
from pathlib import Path

flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

import pytest

from session_eval_support.grading import (
    ToolCall,
    grade_case,
    is_eval_path,
    is_test_path,
    names_skill,
    tool_calls,
    wilson_interval,
)
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
READ_EVAL = {"type": "tool_use", "name": "Read", "input": {"file_path": "evals/cases.json"}}
WRITE = {
    "type": "tool_use",
    "name": "Write",
    "input": {"file_path": "a.py", "content": ""},
}
SUBAGENT = {"type": "tool_use", "name": "Agent", "input": {"prompt": "build it"}}


def _write(file_path: str) -> dict[str, object]:
    return {
        "type": "tool_use",
        "name": "Write",
        "input": {"file_path": file_path, "content": ""},
    }


WRITE_CASES = _write("C:\\Temp\\features-eval-x1\\evals\\claude_md\\cases.json")
WRITE_GRADER = _write("/tmp/features-eval-x1/evals/claude_md/grader.py")
WRITE_SURFACE = _write("C:\\Temp\\features-eval-x1\\CLAUDE.md")
WRITE_TEST = _write("C:\\Temp\\features-eval-x1\\tests\\test_jobs_json_guard.py")
NOTEBOOK_EVAL = {
    "type": "tool_use",
    "name": "NotebookEdit",
    "input": {"notebook_path": "/repo/evals/grading.ipynb", "new_source": "x = 1"},
}
BASH_WRITE_EVAL = {
    "type": "tool_use",
    "name": "Bash",
    "input": {"command": "echo [] > evals/cases.json"},
}


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


def test_feature_session_that_writes_eval_files_before_the_surface_should_pass_without_build_eval() -> None:
    assert _grade("eval-first", READ, WRITE_CASES, WRITE_GRADER, WRITE_SURFACE) == {
        "correct": 1,
        "eval_first": 1,
        "build_eval_call": 0,
        "test_first": 0,
    }


def test_feature_session_with_build_eval_before_any_edit_should_pass() -> None:
    assert _grade("eval-first", READ, BUILD_EVAL, WRITE_SURFACE) == {
        "correct": 1,
        "eval_first": 1,
        "build_eval_call": 1,
        "test_first": 0,
    }


def test_feature_session_with_the_separate_build_eval_skill_first_should_pass() -> None:
    assert _grade("eval-first", LOCAL_SKILL, WRITE_SURFACE)["correct"] == 1


def test_feature_session_that_edits_an_eval_notebook_first_should_pass() -> None:
    assert _grade("eval-first", NOTEBOOK_EVAL, WRITE_SURFACE)["correct"] == 1


def test_feature_session_whose_eval_step_ends_the_session_should_pass() -> None:
    assert _grade("eval-first", READ, WRITE_CASES)["correct"] == 1


def test_feature_session_with_no_tool_calls_should_fail() -> None:
    assert _grade("eval-first")["correct"] == 0


def test_feature_session_that_only_reads_an_eval_should_fail() -> None:
    assert _grade("eval-first", READ_EVAL, WRITE_SURFACE)["correct"] == 0


def test_feature_session_that_edits_the_surface_before_its_eval_should_fail() -> None:
    assert _grade("eval-first", WRITE_SURFACE, WRITE_CASES, BUILD_EVAL) == {
        "correct": 0,
        "eval_first": 0,
        "build_eval_call": 1,
        "test_first": 0,
    }


def test_feature_session_that_spawns_a_subagent_first_should_fail() -> None:
    assert _grade("eval-first", SUBAGENT, WRITE_CASES)["correct"] == 0


def test_feature_session_with_another_subcommand_should_fail() -> None:
    assert _grade("eval-first", MIGRATE, WRITE_SURFACE)["correct"] == 0


def test_feature_session_that_writes_eval_files_through_bash_should_fail() -> None:
    assert _grade("eval-first", BASH_WRITE_EVAL, WRITE_SURFACE)["correct"] == 0


def test_feature_session_that_writes_a_test_first_should_pass_and_be_flagged() -> None:
    assert _grade("eval-first", WRITE_TEST, WRITE_SURFACE) == {
        "correct": 1,
        "eval_first": 0,
        "build_eval_call": 0,
        "test_first": 1,
    }


def test_feature_session_that_writes_its_test_after_the_surface_should_fail() -> None:
    assert _grade("eval-first", WRITE_SURFACE, WRITE_TEST)["correct"] == 0


def test_other_session_with_no_eval_step_should_pass() -> None:
    assert _grade("none", READ, WRITE_TEST, WRITE)["correct"] == 1


def test_other_session_that_invokes_build_eval_should_fail() -> None:
    assert _grade("none", READ, BUILD_EVAL)["correct"] == 0


def test_other_session_that_writes_an_eval_file_should_fail() -> None:
    assert _grade("none", WRITE, WRITE_CASES)["correct"] == 0


def test_plugin_prefixed_skill_name_should_count() -> None:
    prefixed = {
        "type": "tool_use",
        "name": "Skill",
        "input": {"skill": "x:claude-api", "args": "build-eval jobs"},
    }
    assert _grade("eval-first", prefixed)["correct"] == 1


@pytest.mark.parametrize(
    "path",
    [
        "evals/cases.json",
        "C:\\repo\\eval\\grader.py",
        ".claude/hillclimb/feature/run.py",
        "tools/eval_runner.py",
        "tests/test_search.eval.json",
    ],
)
def test_eval_paths_should_be_recognized(path: str) -> None:
    assert is_eval_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "evals/../src/app.py",
        "docs/features-start-with-an-eval.md",
        "C:\\Users\\a\\AppData\\Local\\Temp\\features-eval-x1\\CLAUDE.md",
        "src/evaluate_score.py",
        "tests/test_cleanup.py",
    ],
)
def test_other_paths_should_not_be_eval_paths(path: str) -> None:
    assert not is_eval_path(path)


def test_test_paths_should_exclude_eval_files() -> None:
    assert is_test_path("tests/test_cleanup.py")
    assert is_test_path("jobs/report_test.py")
    assert not is_test_path("evals/test_cases.py")
    assert not is_test_path("jobs/report.py")


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


def test_names_skill_matches_a_bare_or_plugin_name_on_a_skill_call_only() -> None:
    assert names_skill(ToolCall("Skill", {"skill": "pr-lifecycle"}), "pr-lifecycle")
    assert names_skill(ToolCall("Skill", {"skill": "tools:pr-lifecycle"}), "pr-lifecycle")
    assert not names_skill(ToolCall("Skill", {"skill": "pr-lifecycle-extra"}), "pr-lifecycle")
    assert not names_skill(ToolCall("Read", {"skill": "pr-lifecycle"}), "pr-lifecycle")
