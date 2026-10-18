#!/usr/bin/env python3
"""Score a replay fixture. This script does not rewrite the task."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

from deepen_role_gate import refusal_reason

SCORE_ACCEPT: str = "accept"
SCORE_REFUSE: str = "refuse"
UTF8_ENCODING: str = "utf-8"


def score_replay(task_text: str, rewritten_prompt: str) -> dict[str, str]:
    """Return accept, or refuse plus the gate reason. Never rewrite the task."""
    reason = refusal_reason(task_text, rewritten_prompt)
    if reason is None:
        return {"score": SCORE_ACCEPT}
    return {"score": SCORE_REFUSE, "reason": reason}


def score_fixture(fixture: dict[str, object]) -> list[dict[str, str]]:
    """Score each case in a replay fixture against the task it names."""
    task_text = fixture["task"]
    if not isinstance(task_text, str):
        raise TypeError("fixture task must be a string")
    cases = fixture["cases"]
    if not isinstance(cases, list):
        raise TypeError("fixture cases must be a list")
    all_scores: list[dict[str, str]] = []
    for each_case in cases:
        if not isinstance(each_case, dict):
            raise TypeError("each fixture case must be an object")
        case_name = each_case["name"]
        rewritten_prompt = each_case["rewrittenPrompt"]
        expected_score = each_case["expect"]
        if not isinstance(case_name, str) or not isinstance(rewritten_prompt, str):
            raise TypeError("case name and rewrittenPrompt must be strings")
        if not isinstance(expected_score, str):
            raise TypeError("case expect must be a string")
        scored = score_replay(task_text, rewritten_prompt)
        scored["name"] = case_name
        scored["expect"] = expected_score
        scored["matched"] = "yes" if scored["score"] == expected_score else "no"
        all_scores.append(scored)
    return all_scores


def main(all_arguments: list[str]) -> int:
    """Read one fixture path and print a score line per case."""
    if len(all_arguments) != 1:
        sys.stderr.write("usage: grade_deepstack_replay.py <fixture.json>\n")
        return 2
    fixture_path = Path(all_arguments[0])
    fixture = json.loads(fixture_path.read_text(encoding=UTF8_ENCODING))
    if not isinstance(fixture, dict):
        sys.stderr.write("fixture root must be an object\n")
        return 2
    all_scores = score_fixture(fixture)
    for each_score in all_scores:
        sys.stdout.write(json.dumps(each_score) + "\n")
    if any(each_score["matched"] != "yes" for each_score in all_scores):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
