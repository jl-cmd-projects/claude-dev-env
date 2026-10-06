"""Policy parsing and repository lookup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_budget.tests.budget_support import policy_text
from context_budget.model import ContextBudgetPolicyError
from context_budget.policy_file import find_repository_root, parse_policy, read_policy_file


def test_parse_ignores_unknown_keys_and_rejects_a_bad_shape() -> None:
    raw_policy = json.loads(policy_text())
    raw_policy["added_by_another_tool"] = {"anything": True}
    raw_policy["kinds"][1]["extra"] = 1

    assert len(parse_policy(json.dumps(raw_policy)).all_kinds) == 3
    with pytest.raises(ContextBudgetPolicyError):
        parse_policy("[1, 2]")
    with pytest.raises(ContextBudgetPolicyError):
        parse_policy(json.dumps({"kinds": [{"name": "x", "patterns": "**/a.md"}]}))
    with pytest.raises(ContextBudgetPolicyError):
        parse_policy("{not json")


def test_repository_root_accepts_a_git_file_and_policy_reads_from_it(tmp_path: Path) -> None:
    repository_root = tmp_path / "worktree"
    (repository_root / ".claude").mkdir(parents=True)
    (repository_root / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    (repository_root / ".claude" / "context-budget.json").write_text(
        policy_text(), encoding="utf-8"
    )

    found_root = find_repository_root(repository_root / "new" / "dir" / "SKILL.md")

    assert found_root == repository_root
    policy = read_policy_file(repository_root)
    assert policy is not None and len(policy.all_hooks) == 1
    assert read_policy_file(tmp_path) is None
    assert (
        find_repository_root(tmp_path / "x.md") is None
        or find_repository_root(tmp_path / "x.md") != repository_root
    )


