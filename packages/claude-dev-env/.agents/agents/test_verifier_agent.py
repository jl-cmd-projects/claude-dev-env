"""The verifier agent carries the verified-work contract: three modes, reproduce first, and no pass without a reproduction."""

from pathlib import Path

VERIFIER_PATH = Path(__file__).resolve().parent / "verifier.md"


def _verifier_text() -> str:
    return VERIFIER_PATH.read_text(encoding="utf-8")


def test_the_verifier_names_a_mode_for_research_plan_and_fix() -> None:
    verifier_text = _verifier_text()
    assert "**Research.**" in verifier_text
    assert "CONFIRMED or REFUTED" in verifier_text
    assert "**Plan.**" in verifier_text
    assert "SOUND or GAP" in verifier_text
    assert "**Fix.**" in verifier_text


def test_the_fix_mode_reproduces_on_the_old_state_before_it_confirms_on_the_new() -> None:
    verifier_text = _verifier_text()
    reproduce_position = verifier_text.index("1. Reproduce. On the old state")
    confirm_position = verifier_text.index("2. Confirm. On the new state")
    undo_position = verifier_text.index("3. Undo.")
    assert reproduce_position < confirm_position < undo_position


def test_a_fix_whose_issue_did_not_reproduce_never_passes() -> None:
    assert "NOT REPRODUCED is never a pass" in _verifier_text()


def test_the_verifier_leaves_the_work_under_review_untouched() -> None:
    assert "Do not edit, create, or delete any file in the work under review" in _verifier_text()


def test_the_brief_template_carries_the_spawn_oversight_clauses() -> None:
    verifier_text = _verifier_text()
    assert "Outcome: <" in verifier_text
    assert "On a blocker: <" in verifier_text
    assert "leaves out the worker's conclusion" in verifier_text
