"""The always-loaded rules index points at the verified-work guide, and the guide carries the flow and spells out every step."""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = PACKAGE_ROOT / "rules" / "index.md"
GUIDE_PATH = PACKAGE_ROOT / "docs" / "rule-guides" / "verified-work.md"
PR_LIFECYCLE_PATH = PACKAGE_ROOT / ".agents" / "skills" / "pr-lifecycle" / "SKILL.md"


def test_the_index_points_every_session_at_the_verified_work_guide() -> None:
    index_text = INDEX_PATH.read_text(encoding="utf-8")
    assert "- **Verified work** ([guide](../docs/rule-guides/verified-work.md))." in index_text


def test_the_guide_opens_with_the_flow_in_brief() -> None:
    guide_text = GUIDE_PATH.read_text(encoding="utf-8")
    assert "reproduces the issue before it confirms the fix" in guide_text
    assert "Ask before new scope." in guide_text


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


def _delivery_section(guide_text: str) -> str:
    return guide_text.split("## Delivery", 1)[1].split("\n## ", 1)[0]


def test_the_guide_delivers_each_passed_piece_as_its_own_stack_level() -> None:
    delivery_text = _delivery_section(GUIDE_PATH.read_text(encoding="utf-8"))
    assert "When a piece's verifier passes, commit that piece alone, as its own stack level." in delivery_text
    assert "The subject names that one behaviour." in delivery_text
    assert "Start the next piece on top of it." in delivery_text
    assert "A piece that depends on nothing earlier goes on its own branch from trunk." in delivery_text


def test_the_guide_names_the_stacking_command_for_each_setup() -> None:
    delivery_text = _delivery_section(GUIDE_PATH.read_text(encoding="utf-8"))
    assert "`gt create`" in delivery_text
    assert "a plain branch from the previous level" in delivery_text


def test_the_guide_keeps_six_steps_and_sets_delivery_after_them() -> None:
    guide_text = GUIDE_PATH.read_text(encoding="utf-8")
    assert "## The six steps" in guide_text
    assert guide_text.index("6. **Verify the fix.**") < guide_text.index("## Delivery")
    assert guide_text.index("## Delivery") < guide_text.index("## The verifier")


def test_the_guide_sets_no_line_or_file_count_on_a_level() -> None:
    delivery_text = _delivery_section(GUIDE_PATH.read_text(encoding="utf-8")).lower()
    assert "lines" not in delivery_text
    assert "files" not in delivery_text


def test_the_guide_limits_delivery_commits_to_where_the_brief_and_user_allow_them() -> None:
    delivery_text = _delivery_section(GUIDE_PATH.read_text(encoding="utf-8"))
    assert "This applies where the brief and the user allow commits." in delivery_text
    assert "A worker whose brief bars git writes hands the piece back uncommitted and says so." in delivery_text


def test_the_pull_request_skill_points_its_decision_tree_at_the_delivery_section() -> None:
    skill_text = PR_LIFECYCLE_PATH.read_text(encoding="utf-8")
    decision_tree = skill_text.split("### Workflow decision tree", 1)[1].split("\n### ", 1)[0]
    assert "Each planned piece is its own stack level" in decision_tree
    assert "Delivery section of `~/.claude/docs/rule-guides/verified-work.md`" in decision_tree
    assert "`gt create`" not in decision_tree
    assert "a plain branch from the previous level" not in decision_tree


def test_the_enforcement_section_names_the_note_and_keeps_it_non_blocking() -> None:
    enforcement_text = GUIDE_PATH.read_text(encoding="utf-8").split("## Enforcement", 1)[1]
    assert "hooks/advisory/pieces_per_level_note.py" in enforcement_text
    assert "It never denies, delays, or exits non-zero." in enforcement_text
