"""Grader controls for the plain-wording judge eval."""

import json
import sys
from pathlib import Path

flow_directory = Path(__file__).resolve().parent
if str(flow_directory) not in sys.path:
    sys.path.insert(0, str(flow_directory))

from wording_eval_support.config.constants import HOOKS_CONFIG_PATH
from wording_eval_support.grading import fill_prompt, find_judge_prompt, parse_verdict, tally


def test_shipped_hooks_config_holds_the_judge_prompt() -> None:
    prompt = find_judge_prompt(json.loads(HOOKS_CONFIG_PATH.read_text(encoding="utf-8")))
    assert "$ARGUMENTS" in prompt


def test_fill_prompt_places_the_reply_text_as_hook_input() -> None:
    filled = fill_prompt("check $ARGUMENTS", "Ship it.")
    assert '"tool_name": "mcp__hearthbot__reply"' in filled
    assert '"text": "Ship it."' in filled


def test_parse_verdict_reads_deny_allow_and_missing() -> None:
    assert parse_verdict('{"ok": false, "reason": "vague"}') is True
    assert parse_verdict('{"ok": true}') is False
    assert parse_verdict("no verdict here") is None


def test_tally_counts_fails_caught_and_passes_flagged() -> None:
    all_cases = [{"expected": "fail"}, {"expected": "fail"}, {"expected": "pass"}, {"expected": "pass"}]
    run_tally = tally(all_cases, [True, None, True, False])
    assert (run_tally.fails_caught, run_tally.fail_count) == (1, 2)
    assert (run_tally.passes_flagged, run_tally.pass_count) == (1, 2)
    assert run_tally.unreadable_count == 1
