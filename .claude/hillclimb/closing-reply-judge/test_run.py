"""Check the eval command end to end with a stub claude: calls, resume, and the score lines."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

RUN_PATH = Path(__file__).resolve().parent / "run.py"


def _load_run():
    spec = importlib.util.spec_from_file_location("closing_reply_judge_eval_run", RUN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run = _load_run()


def _arguments(monkeypatch: pytest.MonkeyPatch, *all_options: str):
    monkeypatch.setattr(sys, "argv", ["run.py", *all_options])
    return run.parsed_arguments()


def test_should_default_to_haiku_at_medium_for_three_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    arguments = _arguments(monkeypatch)
    assert (arguments.model, arguments.effort, arguments.runs, arguments.score_bars) == ("haiku", "medium", 3, "eval")


def test_should_call_each_case_once_per_run_and_skip_stored_calls_on_rerun(
    monkeypatch: pytest.MonkeyPatch, stub_claude, make_case, verdict_text, promise_text, tmp_path: Path
) -> None:
    stub_claude(verdict_text(promise_span=promise_text))
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps([make_case("twins/INC1", "hold-promise")]), encoding="utf-8")
    arguments = _arguments(monkeypatch, "--cases", str(cases_path), "--out", str(tmp_path / "out"), "--runs", "2")
    run.make_pending_calls(arguments)
    run.make_pending_calls(arguments)
    assert len((tmp_path / "stub.json.calls").read_text(encoding="utf-8").splitlines()) == 2
    all_lines, is_every_bar_met = run.score_lines(arguments)
    assert "twins: fault held [1, 1] of [1, 1]; wrong holds [0, 0] of [0, 0]" in all_lines
    assert any(each.startswith("MISS incident twins") for each in all_lines)
    assert is_every_bar_met is False
