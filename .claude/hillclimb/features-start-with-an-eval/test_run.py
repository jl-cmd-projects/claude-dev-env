import importlib.util
import sys
from pathlib import Path

import pytest

flow_directory = Path(__file__).resolve().parent
if str(flow_directory) not in sys.path:
    sys.path.insert(0, str(flow_directory))

from session_eval_support.rows import read_rows
from session_eval_support.session import SessionRun, SessionSettings

run_specification = importlib.util.spec_from_file_location("features_run", flow_directory / "run.py")
features_run = importlib.util.module_from_spec(run_specification)
run_specification.loader.exec_module(features_run)

FINISHED_EVENTS = [
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "README.md"}}]}},
    {"type": "result", "subtype": "success", "num_turns": 2, "duration_ms": 1530, "modelUsage": {"claude-opus-5-5": {}}},
]


def test_scored_row_carries_the_grade_duration_and_digest() -> None:
    session = SessionRun(FINISHED_EVENTS, 3.21, 0, {"final_decision": {"account": "org-a"}})
    settings = SessionSettings("claude-opus-5-5", "low", 6, 600)

    row = features_run._scored_row({"id": "n02", "prompt": "ask", "group": "question", "expected": "none"}, 0, session, "aaa", settings)

    assert row["grade"]["correct"] == 1
    assert row["latency_s"] == 3.2
    assert row["meta"]["duration_s"] == 1.5
    assert row["meta"]["run_digest"] == "aaa"
    assert row["meta"]["broker_account"] == "org-a"


def test_run_one_scores_the_session_with_the_run_digest_and_removes_the_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    all_workspaces: list[Path] = []

    def finish(workspace: Path, prompt: str, settings: SessionSettings) -> SessionRun:
        all_workspaces.append(workspace)
        return SessionRun(FINISHED_EVENTS, 1.0, 0, {})

    monkeypatch.setattr(features_run, "run_session", finish)
    (tmp_path / "traces").mkdir()
    case = {"id": "n02", "prompt": "ask", "group": "question", "expected": "none"}

    features_run._run_one(case, 0, tmp_path, {".claude/rules/index.md": b"Index.\n"}, "aaa", SessionSettings("claude-opus-5-5", "low", 6, 600))

    assert [each_row["meta"]["run_digest"] for each_row in read_rows(tmp_path / "results.jsonl")] == ["aaa"]
    assert (tmp_path / "traces/n02_rep0.json").is_file()
    assert not all_workspaces[0].exists()


def test_run_pending_cancels_queued_runs_after_one_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    all_started: list[str] = []

    def fail_first(case_by_field: dict[str, str], *_arguments: object) -> None:
        all_started.append(case_by_field["id"])
        if case_by_field["id"] == "case-a":
            raise OSError("disk full")

    monkeypatch.setattr(features_run, "_run_one", fail_first)
    all_pending = [({"id": each_id}, 0) for each_id in ("case-a", "case-b", "case-c")]

    with pytest.raises(OSError, match="disk full"):
        features_run._run_pending(
            all_pending,
            tmp_path,
            {},
            "aaa",
            SessionSettings("claude-opus-5-5", "low", 1, 1),
            1,
        )

    assert all_started == ["case-a"]
