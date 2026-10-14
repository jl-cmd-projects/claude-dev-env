import subprocess
import sys
from pathlib import Path

import pytest

flow_directory = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(flow_directory), str(flow_directory.parent / "features-start-with-an-eval")]

from rules_eval_support import judge
from rules_eval_support.judge import judge_prompt, parse_verdict, run_judge


def test_judge_prompt_includes_the_case_and_trace() -> None:
    prompt = judge_prompt("Change the file", "Check the result", [{"role": "user"}])

    assert "Change the file" in prompt
    assert "Check the result" in prompt
    assert '"role": "user"' in prompt


def test_parse_verdict_skips_invalid_objects_and_uses_the_last_boolean() -> None:
    assert parse_verdict('{"pass": true, "reason": "first"} {"pass": "yes"}') == {
        "pass": True,
        "reason": "first",
    }
    assert parse_verdict("No JSON verdict") is None


def test_parse_verdict_reads_a_reason_that_quotes_braces() -> None:
    assert parse_verdict('Verdict: {"pass": false, "reason": "the loop uses {x} and {\\"pass\\": true}"}') == {
        "pass": False,
        "reason": 'the loop uses {x} and {"pass": true}',
    }


def test_run_judge_reports_a_timeout_as_unreadable_and_leaves_no_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    all_judge_directories: list[Path] = []

    def time_out(all_words: list[str], **all_options: object) -> None:
        all_judge_directories.append(Path(str(all_options["cwd"])))
        raise subprocess.TimeoutExpired(all_words, 1)

    monkeypatch.setattr(judge.subprocess, "run", time_out)

    assert run_judge("grade this", is_direct=True) == (None, {})
    assert not all_judge_directories[0].exists()
