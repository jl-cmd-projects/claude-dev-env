"""Path classification and Markdown section measurement."""

from __future__ import annotations

import pytest

from context_budget.tests.budget_support import (
    ORCHESTRATOR_PATH,
    fixture_text,
    policy_text,
    section_text,
)
from context_budget.findings import file_findings
from context_budget.policy_file import default_policy, parse_policy
from context_budget.sections import context_kind_for_path, path_matches_pattern, scan_sections


def test_calibration_old_orchestrator_fails_on_oversee_delegated_work() -> None:
    all_findings = file_findings(
        default_policy(),
        ORCHESTRATOR_PATH,
        fixture_text("orchestrator_skill_3f2c3ef.txt"),
        None,
    )

    assert [each_finding.scope for each_finding in all_findings] == ["Oversee delegated work"]
    assert (
        'section "Oversee delegated work" has 9 detail lines and no pointer (limit 6)'
        in all_findings[0].message
    )
    assert "reference/oversee-delegated-work.md" in all_findings[0].message


def test_calibration_new_orchestrator_passes_with_largest_unpointed_section_at_five() -> None:
    text = fixture_text("orchestrator_skill_98f45b1.txt")
    all_unpointed_counts = [
        each_scan.detail_line_count
        for each_scan in scan_sections(text)
        if not each_scan.has_pointer
    ]

    assert max(all_unpointed_counts) == 5
    assert file_findings(default_policy(), ORCHESTRATOR_PATH, text, None) == ()


@pytest.mark.parametrize(
    ("pattern", "relative_path", "is_expected_match"),
    [
        ("**/SKILL.md", "SKILL.md", True),
        ("**/SKILL.md", "a/SKILL.md", True),
        ("**/SKILL.md", "a/b/SKILL.md", True),
        ("**/SKILL.md", "a/SKILL.md.bak", False),
        ("packages/claude-dev-env/rules/*.md", "packages/claude-dev-env/rules/a.md", True),
        ("packages/claude-dev-env/rules/*.md", "packages/claude-dev-env/rules/deep/a.md", False),
        ("**/skills-archived/**", "x/skills-archived/a/b/SKILL.md", True),
        ("skill-archive/**", "skill-archive/a/SKILL.md", True),
        ("skill-archive/**", "other/skill-archive/a/SKILL.md", False),
    ],
)
def test_glob_matches_whole_repository_relative_paths(
    pattern: str, relative_path: str, is_expected_match: bool
) -> None:
    assert path_matches_pattern(pattern, relative_path) is is_expected_match


def test_first_matching_kind_wins_and_a_skipped_kind_hides_the_path() -> None:
    policy = parse_policy(policy_text())

    assert context_kind_for_path(policy, "pkg/skills-archived/old/SKILL.md") is None
    skill_kind = context_kind_for_path(policy, "pkg/live/SKILL.md")
    assert skill_kind is not None and skill_kind.name == "skill entry"
    assert context_kind_for_path(policy, "docs/notes.md") is None


def test_section_rule_counts_detail_and_skips_tables_link_lists_and_frontmatter() -> None:
    text = (
        "---\nname: x\ndescription: y\nmore: z\nand: w\nkeys: v\nhere: u\nlast: t\n---\n"
        "# Title\n"
        "| a | b |\n| - | - |\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n| 7 | 8 |\n| 9 | 0 |\n"
        "- [one](https://example.com/one)\n- [two](https://example.com/two)\n"
        "- [three](https://example.com/three)\n1. [four](https://example.com/four)\n"
        "- [five](https://example.com/five)\n- [six](https://example.com/six)\n"
        "- [seven](https://example.com/seven)\n"
    )

    all_scans = scan_sections(text)

    assert [(each.heading, each.detail_line_count, each.has_pointer) for each in all_scans] == [
        ("(top)", 0, False),
        ("Title", 0, False),
    ]


def test_fenced_lines_count_as_detail_and_hide_headings_and_links() -> None:
    text = "## Example\n```bash\n# not a heading\nrun [x](ref.md)\n\nmore\n```\n"

    all_scans = scan_sections(text)

    assert [(each.heading, each.detail_line_count, each.has_pointer) for each in all_scans] == [
        ("(top)", 0, False),
        ("Example", 5, False),
    ]


def test_relative_link_is_a_pointer_and_external_or_anchor_links_are_not() -> None:
    pointed = section_text("Plan", 9, "Read [the plan](reference/plan.md).")
    external = section_text(
        "Plan", 9, "See [site](https://example.com) and [here](#plan) and [m](mailto:a@b.c)."
    )

    assert scan_sections(pointed)[1].has_pointer is True
    assert scan_sections(external)[1].has_pointer is False
