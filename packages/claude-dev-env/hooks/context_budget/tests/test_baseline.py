"""The generated over-budget list records exactly the items over budget."""

from __future__ import annotations

import json

from context_budget.baseline import build_baseline, policy_text_with_baseline
from context_budget.policy_file import parse_policy
from context_budget.tests.budget_support import policy_text, section_text


def test_baseline_records_over_budget_files_and_hooks_only() -> None:
    policy = parse_policy(policy_text())
    text_by_path = {
        "b/SKILL.md": section_text("Plan", 7) + section_text("Plan", 8),
        "c/SKILL.md": section_text("Plan", 7) + "\n" * 200,
        "a/SKILL.md": "short\n",
        "x/skills-archived/SKILL.md": section_text("Old", 40),
        "docs/notes.md": section_text("Notes", 40),
    }

    baseline = build_baseline(policy, text_by_path, {"greeter": 1501, "unlisted": 9000})

    assert baseline == {
        "files": {
            "b/SKILL.md": {"lines": None, "sections": ["Plan", "Plan"]},
            "c/SKILL.md": {"lines": 208, "sections": ["Plan"]},
        },
        "hooks": {"greeter": 1501},
    }


def test_rewriting_the_baseline_keeps_every_other_key() -> None:
    raw_policy = json.loads(policy_text())
    raw_policy["kept_by_another_tool"] = [1]

    rewritten = json.loads(
        policy_text_with_baseline(json.dumps(raw_policy), {"files": {}, "hooks": {"g": 2}})
    )

    assert rewritten["kept_by_another_tool"] == [1]
    assert rewritten["baseline"] == {"files": {}, "hooks": {"g": 2}}
    assert rewritten["kinds"] == raw_policy["kinds"]
