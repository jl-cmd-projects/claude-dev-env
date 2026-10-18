"""The wording rule cites the first-task gate."""

from __future__ import annotations

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def test_wording_rule_cites_the_gate() -> None:
    rule_text = (_PACKAGE_ROOT / "rules" / "deepstack-wording.md").read_text(encoding="utf-8")
    guide_text = (_PACKAGE_ROOT / "docs" / "rule-guides" / "deepstack-wording.md").read_text(
        encoding="utf-8"
    )
    assert "hooks/session/deepen_first_prompt.py" in rule_text
    assert "hooks/session/deepen_first_prompt.py" in guide_text
    assert "SCOPE (role):" in guide_text
    assert "EXAMPLES (illustration only):" in guide_text
    assert "ZOOM-IN BLOCKER:" in guide_text
    assert "DeepStack" in rule_text
