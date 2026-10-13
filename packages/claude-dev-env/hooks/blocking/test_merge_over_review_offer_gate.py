"""Behavior tests for the merge-over-review decision card gate."""

import json
import subprocess
import sys
from pathlib import Path

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import merge_over_review_offer_gate as gate

GATE_SCRIPT = Path(gate.__file__)


def _card(context: str, *options: tuple[str, str]) -> dict[str, object]:
    return {
        "question": "What next for the pull request?",
        "context": context,
        "options": [{"label": label, "consequence": consequence} for label, consequence in options],
    }


def test_merge_option_over_open_findings_should_be_offered_over_review() -> None:
    card = _card("The review found 9 findings.", ("Merge now", "It lands today."), ("Keep looping", "I rerun."))
    assert gate.offers_merge_over_review(card)


def test_merge_option_that_overrides_a_status_should_be_offered_over_review() -> None:
    card = _card("Tests pass.", ("Merge now", "You override the status."))
    assert gate.offers_merge_over_review(card)


def test_card_without_a_merge_option_should_pass() -> None:
    card = _card("The review found 9 findings.", ("Keep looping", "I rerun."), ("Drop shell checks", "Smaller diff."))
    assert not gate.offers_merge_over_review(card)


def test_merge_option_after_a_clean_review_should_pass() -> None:
    card = _card("The review pass on the head came back clean.", ("Merge", "It lands."), ("Hold", "It waits."))
    assert not gate.offers_merge_over_review(card)


def test_script_should_print_a_deny_for_a_merge_over_findings_card() -> None:
    payload = {
        "tool_name": "mcp__hearthbot__ask_decision",
        "tool_input": _card("9 findings remain.", ("Merge now", "It lands.")),
    }
    completed = subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
