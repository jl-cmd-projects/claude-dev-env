"""Tests for the context budget data shapes."""

from __future__ import annotations

from context_budget.model import (
    BaselineEntry,
    BudgetFinding,
    BudgetPolicy,
    ContextKind,
    FileMeasure,
    HookBudget,
    ProseScan,
    SectionScan,
)

SKILL_ENTRY_KIND = ContextKind("skill entry", ("**/SKILL.md",), 200, True)


def test_policy_holds_kinds_hooks_and_baselines() -> None:
    hook = HookBudget("startup print", ("python", "hook.py"), "{}", 1500)
    baseline = BaselineEntry(210, ("Plan",))

    policy = BudgetPolicy(
        section_detail_line_limit=12,
        all_kinds=(SKILL_ENTRY_KIND,),
        all_hooks=(hook,),
        baseline_entry_by_path={"a/SKILL.md": baseline},
        baseline_characters_by_hook_name={"startup print": 5200},
        is_baseline_the_prior_text=True,
    )

    assert policy.section_detail_line_limit == 12
    assert policy.all_kinds == (SKILL_ENTRY_KIND,)
    assert policy.all_hooks == (hook,)
    assert policy.baseline_entry_by_path["a/SKILL.md"] == baseline
    assert policy.baseline_characters_by_hook_name["startup print"] == 5200
    assert policy.is_baseline_the_prior_text is True


def test_baseline_entry_holds_no_line_count_for_a_section_only_file() -> None:
    entry = BaselineEntry(None, ("Steps", "Steps"))

    assert entry.lines is None
    assert entry.all_section_headings == ("Steps", "Steps")


def test_policy_defaults_are_empty() -> None:
    policy = BudgetPolicy(section_detail_line_limit=12, all_kinds=())

    assert policy.all_hooks == ()
    assert policy.baseline_entry_by_path == {}
    assert policy.baseline_characters_by_hook_name == {}
    assert policy.is_baseline_the_prior_text is False


def test_policy_prose_line_word_limit_defaults_to_25_and_holds_an_override() -> None:
    default_policy = BudgetPolicy(section_detail_line_limit=12, all_kinds=())
    raised_policy = BudgetPolicy(
        section_detail_line_limit=12, all_kinds=(), prose_line_word_limit=40
    )

    assert default_policy.prose_line_word_limit == 25
    assert raised_policy.prose_line_word_limit == 40


def test_prose_scan_holds_its_fields() -> None:
    long_line = "word " * 26
    scan = ProseScan(True, False, (long_line,))

    assert scan.has_detail_line is True
    assert scan.has_pointer_line is False
    assert scan.all_long_unlinked_lines == (long_line,)


def test_measure_and_finding_hold_their_fields() -> None:
    section = SectionScan("Plan", 15, False)
    measure = FileMeasure(SKILL_ENTRY_KIND, 210, (section,))
    finding = BudgetFinding("a/SKILL.md", "Plan", "section exceeds limit")

    assert measure.kind == SKILL_ENTRY_KIND
    assert measure.line_count == 210
    assert measure.all_over_limit_sections == (section,)
    assert finding.path == "a/SKILL.md"
    assert finding.scope == "Plan"
    assert finding.message == "section exceeds limit"
