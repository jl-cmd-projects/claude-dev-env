import sys
from pathlib import Path

flow_directory = Path(__file__).resolve().parent
sys.path[:0] = [
    str(flow_directory),
    str(flow_directory.parent / "features-start-with-an-eval"),
    str(flow_directory.parents[2] / "packages" / "claude-dev-env" / "scripts"),
]

import pytest

import run
from run import RunPlan, _run_pending, _summary
from session_eval_support.session import SessionSettings


def test_run_pending_cancels_queued_runs_after_one_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    all_started: list[str] = []

    def fail_first(case_by_field: dict[str, str], _rep: int, _plan: RunPlan) -> None:
        all_started.append(case_by_field["id"])
        if case_by_field["id"] == "case-a":
            raise OSError("disk full")

    monkeypatch.setattr(run, "_run_one", fail_first)
    all_pending = [({"id": each_id}, 0) for each_id in ("case-a", "case-b", "case-c")]
    plan = RunPlan(Path("."), {}, "aaa", SessionSettings("model", "low", 1, 1), False)

    with pytest.raises(OSError, match="disk full"):
        _run_pending(all_pending, plan, 1)

    assert all_started == ["case-a"]


def test_summary_counts_passes_and_errors() -> None:
    rows = [
        {"tags": ["group", "rule"], "grade": {"followed": 1, "opened_guide": 1}},
        {"tags": ["group", "rule"], "grade": {"followed": 0, "opened_guide": 0}},
    ]

    summary = _summary(rows, 1)

    assert "followed 1/2" in summary
    assert "group 1/2" in summary
    assert "opened a guide 1/2" in summary
    assert "errors 1" in summary


def test_main_refuses_an_unknown_case_id_with_a_usage_error(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(sys, "argv", ["run.py", "--variant", "index", "--cases", "w02,zz9"])

    assert run.main() == 2
    assert "unknown case ids: zz9" in caplog.text


def test_main_refuses_an_unknown_variant_with_a_usage_error(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(sys, "argv", ["run.py", "--variant", "indx"])

    assert run.main() == 2
    assert "unknown variant: indx" in caplog.text


def test_main_refuses_a_case_whose_check_has_no_grader(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    cases_file = tmp_path / "cases.json"
    cases_file.write_text('[{"id": "s02", "check": "no_rm", "prompt": "Delete build."}, {"id": "w01", "check": "judge", "prompt": "Write steps."}]', encoding="utf-8")
    monkeypatch.setattr(run, "CASES_FILE", cases_file)
    monkeypatch.setattr(sys, "argv", ["run.py", "--variant", "index"])

    assert run.main() == 2
    assert "unknown checks in cases.json: no_rm" in caplog.text
