import sys
from pathlib import Path

flow_directory = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(flow_directory), str(flow_directory.parent / "features-start-with-an-eval")]

from rules_eval_support.judge import judge_prompt, parse_verdict


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
