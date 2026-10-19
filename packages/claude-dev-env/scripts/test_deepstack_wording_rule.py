"""The wording rule keeps the three DeepStack labels and cites no retired gate."""

from __future__ import annotations

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def test_wording_rule_keeps_the_labels_and_drops_the_retired_gate() -> None:
    rule_text = (_PACKAGE_ROOT / "rules" / "deepstack-wording.md").read_text(encoding="utf-8")
    guide_text = (_PACKAGE_ROOT / "docs" / "rule-guides" / "deepstack-wording.md").read_text(
        encoding="utf-8"
    )
    for each_text in (rule_text, guide_text):
        assert "deepen_first_prompt.py" not in each_text
        assert "CDE_DEEPEN" not in each_text
    assert "**Enforcement:** none." in rule_text
    assert "SCOPE (role):" in guide_text
    assert "EXAMPLES (illustration only):" in guide_text
    assert "ZOOM-IN BLOCKER:" in guide_text
    assert "DeepStack" in rule_text
