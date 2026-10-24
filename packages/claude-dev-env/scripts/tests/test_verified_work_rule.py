"""The always-loaded rules index carries the verified-work flow, and its guide spells out every step."""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = PACKAGE_ROOT / "rules" / "index.md"
GUIDE_PATH = PACKAGE_ROOT / "docs" / "rule-guides" / "verified-work.md"


def test_the_index_points_every_session_at_the_verified_work_guide() -> None:
    index_text = INDEX_PATH.read_text(encoding="utf-8")
    assert "- **Verified work** ([guide](../docs/rule-guides/verified-work.md))." in index_text
    assert "reproduces the issue before it confirms the fix" in index_text
    assert "Ask before new scope." in index_text


def test_the_guide_runs_six_steps_in_order() -> None:
    guide_text = GUIDE_PATH.read_text(encoding="utf-8")
    all_step_markers = (
        "1. **Research.**",
        "2. **Verify the research.**",
        "3. **Plan.**",
        "4. **Verify the plan.**",
        "5. **Implement.**",
        "6. **Verify the fix.**",
    )
    all_positions = [guide_text.index(each_marker) for each_marker in all_step_markers]
    assert all_positions == sorted(all_positions)


def test_the_guide_keeps_the_verifier_apart_and_asks_before_new_scope() -> None:
    guide_text = GUIDE_PATH.read_text(encoding="utf-8")
    assert "The verifier is never the agent that did the work." in guide_text
    assert "A fix whose issue did not reproduce does not pass." in guide_text
    assert "New scope goes to the user as one question before any of it is built" in guide_text
    assert "In-scope work runs with no ask." in guide_text
