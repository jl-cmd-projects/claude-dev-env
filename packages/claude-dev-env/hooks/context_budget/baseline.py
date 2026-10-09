"""Build the over-budget list from the current tree, so no person writes it by hand.

::

    tree    a/SKILL.md 743 lines, section "Plan" over the limit
    hooks   "startup print" injects 5200 characters (limit 1500)
    result  {"files": {"a/SKILL.md": {"lines": 743, "sections": ["Plan"]}},
             "hooks": {"startup print": 5200}}
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from context_budget.model import BudgetPolicy
from context_budget.sections import baseline_entry_for, measure_file
from hooks_constants.context_budget_constants import (
    BASELINE_FILES_KEY,
    BASELINE_HOOKS_KEY,
    BASELINE_KEY,
    JSON_INDENT,
    LINES_KEY,
    SECTIONS_KEY,
)


def _file_entries(policy: BudgetPolicy, text_by_path: Mapping[str, str]) -> dict[str, dict]:
    entry_by_path: dict[str, dict] = {}
    for each_path in sorted(text_by_path):
        measure = measure_file(policy, each_path, text_by_path[each_path])
        entry = None if measure is None else baseline_entry_for(measure)
        if entry is not None:
            entry_by_path[each_path] = {
                LINES_KEY: entry.lines,
                SECTIONS_KEY: list(entry.all_section_headings),
            }
    return entry_by_path


def build_baseline(
    policy: BudgetPolicy,
    text_by_path: Mapping[str, str],
    characters_by_hook_name: Mapping[str, int],
) -> dict[str, dict]:
    """Return the baseline object that records every item over budget now.

    Args:
        policy: Budget policy whose kinds and hook limits apply.
        text_by_path: Text of each tracked file by repository-relative path.
        characters_by_hook_name: Measured characters of each policy hook.

    Returns:
        The ``baseline`` object with sorted file and hook entries.
    """
    entry_by_path = _file_entries(policy, text_by_path)
    limit_by_hook_name = {each.name: each.char_limit for each in policy.all_hooks}
    count_by_hook_name = {
        each_name: each_count
        for each_name, each_count in sorted(characters_by_hook_name.items())
        if each_count > limit_by_hook_name.get(each_name, each_count)
    }
    return {BASELINE_FILES_KEY: entry_by_path, BASELINE_HOOKS_KEY: count_by_hook_name}


def policy_text_with_baseline(policy_text: str, baseline_by_key: Mapping[str, dict]) -> str:
    """Return the policy text with its baseline replaced and every other key kept.

    Args:
        policy_text: Current policy JSON text.
        baseline_by_key: The new ``baseline`` object.

    Returns:
        Indented policy JSON text ending in a newline.
    """
    raw_policy = json.loads(policy_text)
    raw_policy[BASELINE_KEY] = dict(baseline_by_key)
    return json.dumps(raw_policy, indent=JSON_INDENT) + "\n"
