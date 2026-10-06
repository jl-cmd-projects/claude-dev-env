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


def _section_only_policy():
    return parse_policy(policy_text({SKILL_PATH: {"lines": None, "sections": ["Alpha", "Alpha"]}}))


def test_section_only_listed_file_grows_under_its_limit_and_passes() -> None:
    text = section_text("Alpha", 7) + section_text("Alpha", 8) + section_text("Beta", 7)

    assert [each.scope for each in file_findings(_section_only_policy(), SKILL_PATH, text, None)] == [
        "Beta"
    ]
    grown_text = text + "one more\n" * (200 - len(text.splitlines()))
    assert [
        each.scope for each in file_findings(_section_only_policy(), SKILL_PATH, grown_text, None)
    ] == ["Beta"]


def test_section_only_listed_file_crossing_its_limit_fails() -> None:
    text = section_text("Alpha", 7) + section_text("Alpha", 8)
    crossed_text = text + "one more\n" * (201 - len(text.splitlines()))

    all_findings = file_findings(_section_only_policy(), SKILL_PATH, crossed_text, None)

    assert [each.scope for each in all_findings] == ["file"]
    assert "file has 201 lines (skill entry limit 200)" in all_findings[0].message


def test_over_limit_listed_file_may_not_grow_past_its_record() -> None:
    text = section_text("Alpha", 7) + "\n" * 202
    policy = parse_policy(policy_text({SKILL_PATH: {"lines": 210, "sections": ["Alpha"]}}))

    assert file_findings(policy, SKILL_PATH, text, None) == ()
    grown_findings = file_findings(policy, SKILL_PATH, text + "one more\n", None)
    assert [each.scope for each in grown_findings] == ["file"]
    assert "grew from 210 to 211 lines" in grown_findings[0].message


def test_ratchet_asks_to_lower_null_or_remove_the_entry_of_a_changed_listed_file() -> None:
    prior_text = section_text("Alpha", 7) + section_text("Beta", 7) + "\n" * 200
    policy = parse_policy(policy_text({SKILL_PATH: {"lines": 216, "sections": ["Alpha", "Beta"]}}))
    lowered_text = section_text("Alpha", 7) + section_text("Beta", 7) + "\n" * 190
    nulled_text = section_text("Alpha", 7) + section_text("Beta", 7)

    lowered = file_findings(policy, SKILL_PATH, lowered_text, prior_text)
    nulled = file_findings(policy, SKILL_PATH, nulled_text, prior_text)
    removed = file_findings(policy, SKILL_PATH, "short\n", prior_text)

    assert len(lowered) == 1
    assert '{"lines": 206, "sections": ["Alpha", "Beta"]}' in lowered[0].message
    assert '{"lines": null, "sections": ["Alpha", "Beta"]}' in nulled[0].message
    assert "Remove its entry" in removed[0].message
    assert file_findings(policy, SKILL_PATH, lowered_text, None) == ()


def test_ratchet_asks_to_drop_a_lost_section_from_a_section_only_entry() -> None:
    policy = parse_policy(policy_text({SKILL_PATH: {"lines": None, "sections": ["Alpha", "Beta"]}}))
    prior_text = section_text("Alpha", 7) + section_text("Beta", 7)
    shrunk_text = section_text("Alpha", 7) + section_text("Beta", 3, "[b](reference/beta.md)")

    lowered = file_findings(policy, SKILL_PATH, shrunk_text, prior_text)

    assert len(lowered) == 1
    assert '{"lines": null, "sections": ["Alpha"]}' in lowered[0].message


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
    assert "was already over its limit at 230 lines and may only shrink" in grown[0].message
    assert "list" not in grown[0].message
    assert [each.scope for each in added] == ["Beta"]


def test_short_skill_with_one_long_section_accepts_an_added_line_without_a_policy_file() -> None:
    prior_text = "# Skill\nIntro.\n" + section_text("Alpha", 8)
    post_text = "# Skill\nIntro.\nOne more intro line.\n" + section_text("Alpha", 8)

    assert len(prior_text.splitlines()) == 11
    assert edit_findings(default_policy(), SKILL_PATH, prior_text, post_text, True) == ()


def test_edit_of_an_unlisted_over_budget_file_is_allowed_when_it_shrinks_under_a_policy() -> None:
    policy = parse_policy(policy_text())
    prior_text = section_text("Alpha", 9) + "\n" * 220

    assert edit_findings(policy, SKILL_PATH, prior_text, prior_text[:-5], False) == ()
    assert [each.scope for each in edit_findings(policy, SKILL_PATH, None, prior_text, False)] == [
        "file",
        "Alpha",
    ]
