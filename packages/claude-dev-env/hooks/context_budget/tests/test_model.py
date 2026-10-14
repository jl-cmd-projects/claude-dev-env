"""Tests for the context budget data shapes."""

from __future__ import annotations

from typing import Any

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


def test_policy_maps_ignore_later_changes_to_their_source() -> None:
    entry_by_path = {"a/SKILL.md": BaselineEntry(210, ("Plan",))}
    characters_by_hook_name = {"startup print": 5200}
    policy = BudgetPolicy(
        section_detail_line_limit=12,
        all_kinds=(),
        baseline_entry_by_path=entry_by_path,
        baseline_characters_by_hook_name=characters_by_hook_name,
    )

    entry_by_path["b/SKILL.md"] = BaselineEntry(None, ("Steps",))
    characters_by_hook_name["startup print"] = 1

    assert policy.baseline_entry_by_path == {"a/SKILL.md": BaselineEntry(210, ("Plan",))}
    assert policy.baseline_characters_by_hook_name == {"startup print": 5200}


def test_policy_maps_reject_item_assignment() -> None:
    policy = BudgetPolicy(section_detail_line_limit=12, all_kinds=())
    entry_by_path: Any = policy.baseline_entry_by_path
    characters_by_hook_name: Any = policy.baseline_characters_by_hook_name

    with pytest.raises(TypeError):
        entry_by_path["a/SKILL.md"] = BaselineEntry(1, ())
    with pytest.raises(TypeError):
        characters_by_hook_name["startup print"] = 1


def test_equal_policies_hash_alike() -> None:
    first = BudgetPolicy(12, (), (), {"a/SKILL.md": BaselineEntry(210, ("Plan",))}, {"hook": 5})
    second = BudgetPolicy(12, (), (), {"a/SKILL.md": BaselineEntry(210, ("Plan",))}, {"hook": 5})

    assert first == second
    assert hash(first) == hash(second)


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
