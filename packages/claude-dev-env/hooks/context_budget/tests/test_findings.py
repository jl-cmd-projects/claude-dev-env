"""File findings, the CI ratchet, and the findings an edit introduces."""

from __future__ import annotations

from context_budget.tests.budget_support import SKILL_PATH, policy_text, section_text, words_text
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


AGENT_PATH = "shared_utils/files/AGENTS.md"
LONG_LINE = words_text(26)
POINTER_LINE = "Read [the plan](reference/plan.md)."


def test_agent_file_with_no_relative_link_fails_the_pointer_rule() -> None:
    policy = parse_policy(policy_text())

    all_findings = file_findings(policy, AGENT_PATH, "Selection records own icon choice.\n", None)

    assert [each.scope for each in all_findings] == ["no pointer line"]
    assert (
        "shared_utils/files/AGENTS.md: context-budget: file has no pointer line"
        in all_findings[0].message
    )


def test_agent_file_fails_on_an_unlinked_line_over_the_word_limit_only() -> None:
    policy = parse_policy(policy_text())
    exact_line = words_text(25)

    over_limit = file_findings(policy, AGENT_PATH, f"{LONG_LINE}\n{POINTER_LINE}\n", None)
    at_limit = file_findings(policy, AGENT_PATH, f"{exact_line}\n{POINTER_LINE}\n", None)

    assert [each.scope for each in over_limit] == [f"prose line: {LONG_LINE}"]
    assert "26 words" in over_limit[0].message
    assert at_limit == ()


def test_claude_file_gets_the_same_rule_and_a_skill_file_does_not() -> None:
    policy = parse_policy(policy_text())

    claude_findings = file_findings(policy, "app/CLAUDE.md", f"{LONG_LINE}\n{POINTER_LINE}\n", None)

    assert [each.scope for each in claude_findings] == [f"prose line: {LONG_LINE}"]
    assert file_findings(policy, SKILL_PATH, f"{LONG_LINE}\n", None) == ()


def test_blank_agent_file_passes_the_pointer_rule() -> None:
    policy = parse_policy(policy_text())

    assert file_findings(policy, AGENT_PATH, "\n", None) == ()
    assert file_findings(policy, AGENT_PATH, "", None) == ()


def test_edit_that_adds_a_long_unlinked_line_introduces_its_finding_once() -> None:
    policy = parse_policy(policy_text())
    prior_text = f"{POINTER_LINE}\n"
    post_text = f"{prior_text}{LONG_LINE}\n"

    introduced = edit_findings(policy, AGENT_PATH, prior_text, post_text, False)

    assert [each.scope for each in introduced] == [f"prose line: {LONG_LINE}"]
    assert edit_findings(policy, AGENT_PATH, post_text, f"{post_text}Short line.\n", False) == ()


def test_changed_file_reports_only_prose_findings_its_prior_text_lacked() -> None:
    policy = parse_policy(policy_text())
    prior_text = f"{POINTER_LINE}\n{LONG_LINE}\n"
    kept_text = f"{prior_text}Short line.\n"
    added_line = words_text(27)
    added_text = f"{kept_text}{added_line}\n"
    long_line_scopes = [f"prose line: {LONG_LINE}"]

    assert file_findings(policy, AGENT_PATH, kept_text, prior_text) == ()
    added_findings = file_findings(policy, AGENT_PATH, added_text, prior_text)
    assert [each.scope for each in added_findings] == [f"prose line: {added_line}"]
    assert [each.scope for each in file_findings(policy, AGENT_PATH, kept_text, None)] == (
        long_line_scopes
    )
    assert [
        each.scope for each in file_findings(policy, AGENT_PATH, prior_text, prior_text)
    ] == long_line_scopes


def test_claude_file_that_only_imports_agents_md_passes_the_pointer_rule() -> None:
    policy = parse_policy(policy_text())

    assert file_findings(policy, "app/CLAUDE.md", "@AGENTS.md\n", None) == ()


def test_import_line_satisfies_the_pointer_rule_but_not_the_word_limit() -> None:
    policy = parse_policy(policy_text())

    all_findings = file_findings(policy, "app/CLAUDE.md", f"@AGENTS.md\n{LONG_LINE}\n", None)

    assert [each.scope for each in all_findings] == [f"prose line: {LONG_LINE}"]


def test_import_line_does_not_exempt_a_section_from_the_section_rule() -> None:
    policy = parse_policy(policy_text())
    text = section_text("Alpha", 7, "@reference/alpha.md")

    assert [each.scope for each in file_findings(policy, SKILL_PATH, text, None)] == ["Alpha"]


def test_skipped_kind_hides_an_agent_file_from_the_prose_rule() -> None:
    policy = parse_policy(policy_text())
    text = "Selection records own icon choice.\n"

    assert file_findings(policy, "pkg/skills-archived/AGENTS.md", text, None) == ()
    live_findings = file_findings(policy, "pkg/live/AGENTS.md", text, None)
    assert [each.scope for each in live_findings] == ["no pointer line"]
