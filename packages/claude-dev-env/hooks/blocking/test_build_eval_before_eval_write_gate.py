"""Behavior tests for the eval write build-eval gate."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import build_eval_before_eval_write_gate as gate
from blocking.gate_run_reads import ReadSlice, read_deadlines_started, started_read_deadlines
from hooks_constants.build_eval_before_eval_write_gate_constants import (
    EVAL_WRITE_SCAN_RAN_OUT_SENTENCE,
    MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON,
    UNREADABLE_TRANSCRIPT_BEFORE_EVAL_WRITE_REASON,
)
from hooks_constants.gate_run_reads_constants import EVAL_WRITE_SCAN_SECONDS, STARTUP_AND_OUTPUT_MARGIN_SECONDS

GATE_SCRIPT = Path(gate.__file__)


def _transcript(tmp_path: Path, build_eval: bool) -> Path:
    lines = [json.dumps({"type": "user", "message": {"content": "Add a search flag."}})]
    if build_eval:
        skill_call = {
            "type": "tool_use",
            "name": "Skill",
            "input": {"skill": "claude-api", "args": "build-eval"},
        }
        lines.append(json.dumps({"type": "assistant", "message": {"content": [skill_call]}}))
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return transcript_path


def _payload(file_path: str, transcript_path: Path, tool_name: str = "Write") -> dict[str, object]:
    return {
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path, "content": "[]"},
        "transcript_path": str(transcript_path),
    }


def _reason(decision: dict[str, object] | None) -> object:
    assert decision is not None
    return decision["hookSpecificOutput"]["permissionDecisionReason"]


def test_eval_case_write_without_build_eval_should_be_denied(tmp_path: Path) -> None:
    decision = gate.decision_for(
        _payload("/repo/evals/cases.json", _transcript(tmp_path, build_eval=False))
    )
    assert _reason(decision) == MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON


def test_eval_write_after_build_eval_should_pass(tmp_path: Path) -> None:
    assert (
        gate.decision_for(
            _payload("/repo/evals/cases.json", _transcript(tmp_path, build_eval=True))
        )
        is None
    )


def test_hillclimb_edit_without_build_eval_should_be_denied(tmp_path: Path) -> None:
    payload = _payload(
        "/repo/.claude/hillclimb/search-flag/run.py",
        _transcript(tmp_path, build_eval=False),
        "Edit",
    )
    assert _reason(gate.decision_for(payload)) == MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON


def test_source_write_without_build_eval_should_pass(tmp_path: Path) -> None:
    assert (
        gate.decision_for(_payload("/repo/src/search.py", _transcript(tmp_path, build_eval=False)))
        is None
    )


def test_eval_write_with_unreadable_transcript_should_be_denied(tmp_path: Path) -> None:
    decision = gate.decision_for(_payload("/repo/evals/cases.json", tmp_path / "missing.jsonl"))
    assert _reason(decision) == UNREADABLE_TRANSCRIPT_BEFORE_EVAL_WRITE_REASON


def test_eval_paths_should_be_recognized() -> None:
    assert gate.is_eval_path("evals/cases.json")
    assert gate.is_eval_path("C:\\repo\\eval\\grader.py")
    assert gate.is_eval_path("tools/eval_runner.py")
    assert gate.is_eval_path("tests/search.eval.json")


def test_notebook_edit_of_an_eval_notebook_should_be_denied(tmp_path: Path) -> None:
    payload = {
        "tool_name": "NotebookEdit",
        "tool_input": {"notebook_path": "/repo/evals/grading.ipynb", "new_source": "x = 1"},
        "transcript_path": str(_transcript(tmp_path, build_eval=False)),
    }
    assert _reason(gate.decision_for(payload)) == MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON


def test_multi_edit_of_an_eval_file_should_be_denied(tmp_path: Path) -> None:
    payload = {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": "/repo/evals/cases.json",
            "edits": [{"old_string": "[]", "new_string": "[1]"}],
        },
        "transcript_path": str(_transcript(tmp_path, build_eval=False)),
    }
    assert _reason(gate.decision_for(payload)) == MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON


def test_gate_source_files_should_not_be_recognized() -> None:
    assert not gate.is_eval_path("hooks/blocking/build_eval_before_eval_write_gate.py")
    assert not gate.is_eval_path("hooks/blocking/test_build_eval_before_eval_write_gate.py")
    assert not gate.is_eval_path(
        "hooks/hooks_constants/build_eval_before_eval_write_gate_constants.py"
    )


def test_non_eval_paths_should_not_be_recognized() -> None:
    assert not gate.is_eval_path("src/evaluate_score.py")
    assert not gate.is_eval_path("evals/../src/app.py")
    assert not gate.is_eval_path("docs/rule-guides/features-start-with-an-eval.md")
    assert not gate.is_eval_path("src/retrieval.py")
    assert not gate.is_eval_path("medieval/notes.md")
    assert not gate.is_eval_path("")


def test_script_should_print_a_deny_for_an_eval_write(tmp_path: Path) -> None:
    payload = _payload("/repo/evals/cases.json", _transcript(tmp_path, build_eval=False))
    completed = subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_apply_patch_to_an_eval_file_should_be_denied(tmp_path: Path) -> None:
    patch = "*** Begin Patch\n*** Add File: evals/cases.json\n+[]\n*** End Patch\n"
    payload = {
        "tool_name": "apply_patch",
        "tool_input": {"command": patch},
        "cwd": str(tmp_path),
        "transcript_path": str(_transcript(tmp_path, build_eval=False)),
    }
    assert _reason(gate.decision_for(payload)) == MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON


def test_unparseable_apply_patch_naming_an_eval_file_should_be_denied(tmp_path: Path) -> None:
    patch = "*** Begin Patch\n*** Add File: evals/cases.json\n+[]\n"
    payload = {
        "tool_name": "apply_patch",
        "tool_input": {"command": patch},
        "cwd": str(tmp_path),
        "transcript_path": str(_transcript(tmp_path, build_eval=False)),
    }
    assert _reason(gate.decision_for(payload)) == MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON


EVAL_WRITE_GATE_COMMAND_SUFFIX = "/hooks/blocking/build_eval_before_eval_write_gate.py"
CLOCK_START = 1000.0


class SteppedClock:
    def __init__(self) -> None:
        self.now = CLOCK_START

    def __call__(self) -> float:
        return self.now


def _registered_gate_timeout_seconds() -> int:
    all_registration_fields = json.loads((HOOKS_DIRECTORY / "hooks.json").read_text(encoding="utf-8"))
    all_timeouts = [
        each_hook["timeout"]
        for each_group in all_registration_fields["hooks"]["PreToolUse"]
        for each_hook in each_group["hooks"]
        if each_hook.get("command", "").endswith(EVAL_WRITE_GATE_COMMAND_SUFFIX)
    ]
    assert len(all_timeouts) == 1
    return all_timeouts[0]


def test_registered_timeout_should_outlast_the_eval_write_scan_deadline() -> None:
    assert ReadSlice.EVAL_WRITE.value == EVAL_WRITE_SCAN_SECONDS
    assert _registered_gate_timeout_seconds() >= EVAL_WRITE_SCAN_SECONDS + STARTUP_AND_OUTPUT_MARGIN_SECONDS


def test_scan_the_eval_write_deadline_stopped_should_deny_and_say_to_call_build_eval_again(tmp_path: Path) -> None:
    clock = SteppedClock()
    payload = _payload("/repo/evals/cases.json", _transcript(tmp_path, build_eval=True))
    with read_deadlines_started(clock):
        clock.now = CLOCK_START + EVAL_WRITE_SCAN_SECONDS
        decision = gate.decision_for(payload)
    assert _reason(decision) == MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON + EVAL_WRITE_SCAN_RAN_OUT_SENTENCE


def test_scan_with_time_left_should_deny_without_the_ran_out_sentence(tmp_path: Path) -> None:
    clock = SteppedClock()
    payload = _payload("/repo/evals/cases.json", _transcript(tmp_path, build_eval=False))
    with read_deadlines_started(clock):
        clock.now = CLOCK_START + EVAL_WRITE_SCAN_SECONDS - 1
        assert _reason(gate.decision_for(payload)) == MISSING_BUILD_EVAL_BEFORE_EVAL_WRITE_REASON
        assert gate.decision_for(_payload("/repo/evals/cases.json", _transcript(tmp_path, build_eval=True))) is None


def test_main_should_start_the_read_deadlines_before_it_reads_the_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    all_seen_deadlines: list[object] = []

    def recorded_print(decide: object) -> int:
        all_seen_deadlines.append(started_read_deadlines.get())
        return 0

    monkeypatch.setattr(gate, "print_decision_from_stdin", recorded_print)
    assert gate.main() == 0
    assert all_seen_deadlines[0] is not None
