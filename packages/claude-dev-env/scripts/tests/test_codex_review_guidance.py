"""Native guidance has a repository entry point and stays repository-independent."""

from pathlib import Path


def test_native_guidance_is_discoverable() -> None:
    repository = Path(__file__).resolve().parents[4]
    instructions = (repository / "AGENTS.md").read_text(encoding="utf-8")
    assert "# Code Review Rules" in instructions
    assert "docs/review/review.md" in instructions
    guidance = (repository / "docs/review/review.md").read_text(encoding="utf-8")
    assert "Current repository instructions override stale hosted copies." in guidance
    assert "Completed review can contain findings." in guidance
    assert "theme_db_id" not in guidance
    assert "saved-grid" not in guidance
