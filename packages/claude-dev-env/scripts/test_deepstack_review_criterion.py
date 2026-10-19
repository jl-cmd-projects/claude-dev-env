"""A new instruction names the trigger that covers it."""

from __future__ import annotations

from pathlib import Path

_RULES = Path(__file__).resolve().parent.parent / "docs" / "CODE_RULES.md"


def test_new_instruction_criterion_names_the_manifest() -> None:
    text = _RULES.read_text(encoding="utf-8")
    assert "## 11.7 A NEW INSTRUCTION NAMES THE TRIGGER THAT COVERS IT" in text
    assert "rules-archived/ARCHIVE-MANIFEST.md" in text
    assert "deepen_first_prompt.py" not in text
