"""File findings, the CI ratchet, and the findings an edit introduces."""

from __future__ import annotations

from context_budget.tests.budget_support import SKILL_PATH, policy_text, section_text
from context_budget.findings import edit_findings, file_findings
from context_budget.policy_file import default_policy, parse_policy


def test_unlisted_file_reports_line_limit_and_eachsection_text() -> None:
    policy = parse_policy(policy_text())
    text = section_text("Alpha", 7) + "\n" * 200

    all_findings = file_findings(policy, SKILL_PATH, text, None)

    assert [each.scope for each in all_findings] == ["file", "Alpha"]
    assert "file has 208 lines (skill entry limit 200)" in all_findings[0].message


def test_listed_file_may_hold_recorded_sections_and_may_not_grow() -> None:
    text = section_text("Alpha", 7) + section_text("Alpha", 8) + section_text("Beta", 7)
    line_count = len(text.splitlines())
    policy = parse_policy(
        policy_text({SKILL_PATH: {"lines": line_count, "sections": ["Alpha", "Alpha"]}})
    )

    assert [each.scope for each in file_findings(policy, SKILL_PATH, text, None)] == ["Beta"]
    grown_findings = file_findings(policy, SKILL_PATH, text + "one more\n", None)
    assert f"grew from {line_count} to {line_count + 1} lines" in grown_findings[0].message


def test_ratchet_asks_to_lower_or_remove_the_entry_of_a_changed_listed_file() -> None:
    prior_text = section_text("Alpha", 7) + section_text("Beta", 7)
    policy = parse_policy(policy_text({SKILL_PATH: {"lines": 16, "sections": ["Alpha", "Beta"]}}))
    shrunk_text = section_text("Alpha", 7) + section_text("Beta", 3, "[b](reference/beta.md)")

    lowered = file_findings(policy, SKILL_PATH, shrunk_text, prior_text)
    removed = file_findings(policy, SKILL_PATH, "short\n", prior_text)

    assert len(lowered) == 1
    assert '{"lines": 13, "sections": ["Alpha"]}' in lowered[0].message
    assert "Remove its entry" in removed[0].message
    assert file_findings(policy, SKILL_PATH, shrunk_text, None) == ()


def test_edit_that_only_shrinks_has_no_findings_without_a_policy_file() -> None:
    prior_text = section_text("Alpha", 9) + "\n" * 220
    shrunk_text = section_text("Alpha", 8) + "\n" * 210

    assert edit_findings(default_policy(), SKILL_PATH, prior_text, shrunk_text, True) == ()


def test_edit_that_grows_or_adds_a_section_is_reported_without_a_policy_file() -> None:
    prior_text = section_text("Alpha", 9) + "\n" * 220
    grown = edit_findings(default_policy(), SKILL_PATH, prior_text, prior_text + "x\n", True)
    added = edit_findings(
        default_policy(), SKILL_PATH, prior_text, section_text("Beta", 7) + "\n" * 200, True
    )

    assert [each.scope for each in grown] == ["file"]
    assert [each.scope for each in added] == ["Beta"]


def test_edit_of_an_unlisted_over_budget_file_is_allowed_when_it_shrinks_under_a_policy() -> None:
    policy = parse_policy(policy_text())
    prior_text = section_text("Alpha", 9) + "\n" * 220

    assert edit_findings(policy, SKILL_PATH, prior_text, prior_text[:-5], False) == ()
    assert [each.scope for each in edit_findings(policy, SKILL_PATH, None, prior_text, False)] == [
        "file",
        "Alpha",
    ]
