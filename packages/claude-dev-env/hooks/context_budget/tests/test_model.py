"""Tests for the context budget data shapes."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from context_budget.model import (
    BaselineEntry,
    BudgetFinding,
    BudgetPolicy,
    ContextKind,
    FileMeasure,
    HookBudget,
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

    assert policy.all_kinds == (SKILL_ENTRY_KIND,)
    assert policy.all_hooks == (hook,)
    assert policy.baseline_entry_by_path["a/SKILL.md"] == baseline
    assert policy.baseline_characters_by_hook_name["startup print"] == 5200
    assert policy.is_baseline_the_prior_text is True


def test_baseline_entry_holds_no_line_count_for_a_section_only_file() -> None:
    entry = BaselineEntry(None, ("Steps", "Steps"))

    assert entry.lines is None
    assert entry.all_section_headings == ("Steps", "Steps")


def test_policy_defaults_are_independent() -> None:
    first = BudgetPolicy(section_detail_line_limit=12, all_kinds=())
    second = BudgetPolicy(section_detail_line_limit=12, all_kinds=())

    assert first.all_hooks == ()
    assert first.baseline_entry_by_path == {}
    assert first.baseline_characters_by_hook_name == {}
    assert first.baseline_entry_by_path is not second.baseline_entry_by_path
    assert first.baseline_characters_by_hook_name is not second.baseline_characters_by_hook_name
    assert first.is_baseline_the_prior_text is False


def test_policy_rejects_field_rebinding() -> None:
    policy = BudgetPolicy(section_detail_line_limit=12, all_kinds=())

    with pytest.raises(FrozenInstanceError):
        policy.section_detail_line_limit = 20


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
