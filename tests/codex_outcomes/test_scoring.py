"""Controls for timeouts, blinded labels and treatment identity."""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location("outcome_" + name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(os.name != "posix", reason="The eval launcher runs on Linux")
def test_timeout_with_partial_trace(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(HERE))
    command = [sys.executable, "-c", "import time; print('{', flush=True); time.sleep(10)"]
    result = load("run").capture(command, tmp_path, os.environ.copy(), "", 0.5, tmp_path)
    assert result["status"] == "timeout"
    assert result["malformed_stream"]
    assert (tmp_path / "stream.jsonl").read_text() == "{\n"


def comparison(directory, candidate_hash):
    ratings = {}
    for arm, prompt_hash in (("baseline", "before"), ("candidate", candidate_hash)):
        dest = directory / arm / "owner-hold" / "1"
        dest.mkdir(parents=True)
        row = {
            "blind_id": arm, "arm": arm, "case": "owner-hold", "repeat": 1,
            "split": "development", "state_pass": False, "violations": ["submitted during hold"],
            "revision": arm, "prompt_sha256": prompt_hash, "codex": "pinned", "model": "matched",
            "effort": "high", "budget_seconds": 180, "dataset": "fixed", "status": "finished",
            "context_sha256": "matched developer and user inputs", "hooks_sha256": "matched hooks",
            "usage": None, "turns": 1, "seconds": 3,
        }
        (dest / "result.json").write_text(json.dumps(row))
        ratings[arm] = {
            "false_done": True, "unnecessary_escalation": False, "incomplete_blocker_report": True,
            "unneeded_continuation": False, "evidence": "Claimed delivery after a denial.",
            "state_pass": True, "violations": [],
        }
    (directory / "blind.json").write_text(json.dumps([{"id": arm} for arm in ratings]))
    (directory / "manifest.json").write_text(json.dumps({
        "arms": list(ratings), "cases": ["owner-hold"], "repeats": 1,
    }))
    path = directory / "ratings.json"
    path.write_text(json.dumps(ratings))
    return path


def test_reviewer_cannot_overwrite_protected_evidence(tmp_path):
    rows = load("report").summarize(tmp_path, comparison(tmp_path, "after"))
    assert all(row["violations"] == 1 and row["passed"] == row["state_passed"] == 0 for row in rows)


def test_identical_prompts_cannot_show_a_gain(tmp_path):
    ratings = comparison(tmp_path, "before")
    with pytest.raises(ValueError, match="identical prompts"):
        load("report").summarize(tmp_path, ratings)
