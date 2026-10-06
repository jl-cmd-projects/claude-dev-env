"""Report a policy file change that loosens the budget.

The over-budget list may only shrink: a new or larger baseline entry, a raised
limit, a section rule turned off, or a deleted kind or hook is a finding.
Existing kind patterns and precedence stay fixed. A null line count that
becomes a number is larger. A policy file the change introduces passes.
"""

from __future__ import annotations

from collections import Counter

from context_budget.model import BaselineEntry, BudgetFinding, BudgetPolicy, ContextKind
from hooks_constants.context_budget_constants import (
    CHANGE_ADDS_FILE,
    CHANGE_ADDS_HOOK,
    CHANGE_ADDS_SECTION,
    CHANGE_CHANGES_KIND_ORDER,
    CHANGE_CHANGES_PATTERNS,
    CHANGE_DELETES_HOOK,
    CHANGE_DELETES_KIND,
    CHANGE_DISABLES_SECTION_RULE,
    CHANGE_RAISES_CHAR_LIMIT,
    CHANGE_RAISES_FILE,
    CHANGE_RAISES_HOOK,
    CHANGE_RAISES_LINE_LIMIT,
    CHANGE_RAISES_SECTION_LIMIT,
    CHANGE_RECORDS_FILE_LINES,
    FILE_SCOPE,
    NO_LINE_LIMIT_TEXT,
    SHRINK_ONLY_TEMPLATE,
)


def _limit_text(line_limit: int | None) -> str:
    return NO_LINE_LIMIT_TEXT if line_limit is None else str(line_limit)


def _kind_changes(prior_kind: ContextKind, current_kind: ContextKind | None) -> list[str]:
    if current_kind is None:
        return [CHANGE_DELETES_KIND.format(subject=prior_kind.name)]
    all_changes: list[str] = []
    if current_kind.all_patterns != prior_kind.all_patterns:
        all_changes.append(CHANGE_CHANGES_PATTERNS.format(subject=prior_kind.name))
    prior_limit = prior_kind.line_limit
    current_limit = current_kind.line_limit
    if prior_limit is not None and (current_limit is None or current_limit > prior_limit):
        all_changes.append(
            CHANGE_RAISES_LINE_LIMIT.format(
                subject=prior_kind.name,
                prior=_limit_text(prior_limit),
                current=_limit_text(current_limit),
            )
        )
    if prior_kind.is_section_rule_on and not current_kind.is_section_rule_on:
        all_changes.append(CHANGE_DISABLES_SECTION_RULE.format(subject=prior_kind.name))
    return all_changes


def _limit_changes(prior_policy: BudgetPolicy, current_policy: BudgetPolicy) -> list[str]:
    all_changes: list[str] = []
    prior_section_limit = prior_policy.section_detail_line_limit
    current_section_limit = current_policy.section_detail_line_limit
    if current_section_limit > prior_section_limit:
        all_changes.append(
            CHANGE_RAISES_SECTION_LIMIT.format(
                prior=prior_section_limit, current=current_section_limit
            )
        )
    current_kind_by_name = {each.name: each for each in current_policy.all_kinds}
    all_prior_kind_names = tuple(
        each.name for each in prior_policy.all_kinds if each.name in current_kind_by_name
    )
    all_current_kind_names = tuple(each.name for each in current_policy.all_kinds)
    if (
        all_current_kind_names[:len(all_prior_kind_names)] != all_prior_kind_names
        or len(set(all_current_kind_names)) != len(all_current_kind_names)
    ):
        all_changes.append(CHANGE_CHANGES_KIND_ORDER)
    for each_prior_kind in prior_policy.all_kinds:
        all_changes.extend(
            _kind_changes(each_prior_kind, current_kind_by_name.get(each_prior_kind.name))
        )
    return all_changes + _hook_limit_changes(prior_policy, current_policy)


def _hook_limit_changes(prior_policy: BudgetPolicy, current_policy: BudgetPolicy) -> list[str]:
    """Preserve each measured hook and hold its output limit to the prior budget."""
    all_changes: list[str] = []
    current_hook_by_name = {each.name: each for each in current_policy.all_hooks}
    for each_prior_hook in prior_policy.all_hooks:
        current_hook = current_hook_by_name.get(each_prior_hook.name)
        if current_hook is None:
            all_changes.append(CHANGE_DELETES_HOOK.format(subject=each_prior_hook.name))
            continue
        current_limit = current_hook.char_limit
        if current_limit > each_prior_hook.char_limit:
            all_changes.append(
                CHANGE_RAISES_CHAR_LIMIT.format(
                    subject=each_prior_hook.name,
                    prior=each_prior_hook.char_limit,
                    current=current_limit,
                )
            )
    return all_changes


def _line_entry_change(
    each_path: str, each_entry: BaselineEntry, prior_entry: BaselineEntry
) -> str | None:
    if each_entry.lines is None:
        return None
    if prior_entry.lines is None:
        return CHANGE_RECORDS_FILE_LINES.format(subject=each_path, current=each_entry.lines)
    if each_entry.lines > prior_entry.lines:
        return CHANGE_RAISES_FILE.format(
            subject=each_path, prior=prior_entry.lines, current=each_entry.lines
        )
    return None


def _file_entry_changes(prior_policy: BudgetPolicy, current_policy: BudgetPolicy) -> list[str]:
    all_changes: list[str] = []
    for each_path, each_entry in sorted(current_policy.baseline_entry_by_path.items()):
        prior_entry = prior_policy.baseline_entry_by_path.get(each_path)
        if prior_entry is None:
            all_changes.append(CHANGE_ADDS_FILE.format(subject=each_path))
            continue
        line_change = _line_entry_change(each_path, each_entry, prior_entry)
        if line_change is not None:
            all_changes.append(line_change)
        all_added_headings = Counter(each_entry.all_section_headings) - Counter(
            prior_entry.all_section_headings
        )
        all_changes.extend(
            CHANGE_ADDS_SECTION.format(heading=each_heading, subject=each_path)
            for each_heading in sorted(all_added_headings.elements())
        )
    return all_changes


def _hook_entry_change(each_name: str, each_count: int, prior_count: int | None) -> str | None:
    if prior_count is None:
        return CHANGE_ADDS_HOOK.format(subject=each_name)
    if each_count > prior_count:
        return CHANGE_RAISES_HOOK.format(subject=each_name, prior=prior_count, current=each_count)
    return None


def _hook_entry_changes(prior_policy: BudgetPolicy, current_policy: BudgetPolicy) -> list[str]:
    prior_count_by_name = prior_policy.baseline_characters_by_hook_name
    all_candidate_changes = (
        _hook_entry_change(each_name, each_count, prior_count_by_name.get(each_name))
        for each_name, each_count in sorted(current_policy.baseline_characters_by_hook_name.items())
    )
    return [each for each in all_candidate_changes if each is not None]


def policy_shrink_findings(
    policy_path: str, prior_policy: BudgetPolicy | None, current_policy: BudgetPolicy
) -> tuple[BudgetFinding, ...]:
    """Report each change to the policy file that loosens the budget.

    Args:
        policy_path: Repository-relative path of the policy file.
        prior_policy: Policy before the change, or None when the change adds it.
        current_policy: Policy after the change.

    Returns:
        One finding per loosening change; empty when the file is new.
    """
    if prior_policy is None:
        return ()
    all_changes = (
        _limit_changes(prior_policy, current_policy)
        + _file_entry_changes(prior_policy, current_policy)
        + _hook_entry_changes(prior_policy, current_policy)
    )
    return tuple(
        BudgetFinding(
            policy_path, FILE_SCOPE, SHRINK_ONLY_TEMPLATE.format(path=policy_path, change=each)
        )
        for each in all_changes
    )
