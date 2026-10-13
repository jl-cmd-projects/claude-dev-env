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


def test_policy_holds_kinds_hooks_and_baselines() -> None:
    kind = ContextKind("skill entry", ("**/SKILL.md",), 200, True)
    hook = HookBudget("startup print", ("python", "hook.py"), "{}", 1500)
    baseline = BaselineEntry(210, ("Plan",))

    policy = BudgetPolicy(
        section_detail_line_limit=12,
        all_kinds=(kind,),
        all_hooks=(hook,),
        baseline_entry_by_path={"a/SKILL.md": baseline},
        baseline_characters_by_hook_name={"startup print": 5200},
        is_baseline_the_prior_text=True,
    )

    assert policy.all_kinds == (kind,)
    assert policy.all_hooks == (hook,)
    assert policy.baseline_entry_by_path["a/SKILL.md"] == baseline
    assert policy.baseline_characters_by_hook_name["startup print"] == 5200
    assert policy.is_baseline_the_prior_text is True


def test_policy_defaults_are_independent_and_frozen() -> None:
    first = BudgetPolicy(section_detail_line_limit=12, all_kinds=())
    second = BudgetPolicy(section_detail_line_limit=12, all_kinds=())

    assert first.all_hooks == ()
    assert first.baseline_entry_by_path == {}
    assert first.baseline_characters_by_hook_name == {}
    assert first.baseline_entry_by_path is not second.baseline_entry_by_path
    assert first.baseline_characters_by_hook_name is not second.baseline_characters_by_hook_name
    with pytest.raises(FrozenInstanceError):
        setattr(first, "section_detail_line_limit", 20)


def test_measure_and_finding_keep_the_scanned_section() -> None:
    kind = ContextKind("skill entry", ("**/SKILL.md",), 200, True)
    section = SectionScan("Plan", 15, False)
    measure = FileMeasure(kind, 210, (section,))
    finding = BudgetFinding("a/SKILL.md", "Plan", "section exceeds limit")

    assert measure.kind == kind
    assert measure.line_count == 210
    assert measure.all_over_limit_sections == (section,)
    assert finding.path == "a/SKILL.md"
    assert finding.scope == section.heading
    assert finding.message == "section exceeds limit"
