"""The context-budget rules reach context Markdown and the policy file through the registry."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from policy_lint import adapters, registry
from policy_lint.model import ContentOrigin, Document, DocumentRule

_SKILL_PATH = "tools/example/SKILL.md"
_POLICY_PATH = ".claude/context-budget.json"


def _policy(baseline_files: dict | None = None, line_limit: int = 200) -> dict:
    return {
        "section_detail_line_limit": 6,
        "kinds": [
            {
                "name": "skill entry",
                "patterns": ["**/SKILL.md"],
                "line_limit": line_limit,
                "section_rule": True,
            }
        ],
        "hooks": [],
        "baseline": {"files": baseline_files or {}, "hooks": {}},
    }


def _write_policy(repository_root: Path, raw_policy: dict) -> None:
    (repository_root / ".claude").mkdir(exist_ok=True)
    (repository_root / _POLICY_PATH).write_text(
        json.dumps(raw_policy), encoding="utf-8"
    )


def _document(path: str, text: str, prior_text: str | None = None) -> Document:
    return Document(PurePosixPath(path), text, prior_text, None, ContentOrigin.WORKTREE)


def _section(heading: str, detail_count: int) -> str:
    all_lines = [
        f"## {heading}",
        *(f"Detail line {each}." for each in range(detail_count)),
    ]
    return "\n".join(all_lines) + "\n"


def _registered_rule(rule_id: str) -> DocumentRule:
    for each_rule in registry.default_registry():
        if each_rule.rule_id == rule_id and isinstance(each_rule, DocumentRule):
            return each_rule
    raise AssertionError(rule_id)


def test_both_rules_are_registered_for_changed_and_repository_selections() -> None:
    for each_rule_id in ("context-budget", "context-budget-policy"):
        assert _registered_rule(each_rule_id).rule_sets == frozenset(
            {"changed", "repository"}
        )
    assert _registered_rule("context-budget").accepts(_document(_SKILL_PATH, ""))
    assert _registered_rule("context-budget-policy").accepts(
        _document(_POLICY_PATH, "{}")
    )
    assert not _registered_rule("context-budget-policy").accepts(
        _document("a/b.json", "{}")
    )


def test_an_unpointed_long_section_reports_with_its_fix(tmp_path: Path) -> None:
    _write_policy(tmp_path, _policy())

    all_diagnostics = adapters.context_budget_diagnostics(
        _document(_SKILL_PATH, _section("Plan", 7)), tmp_path
    )

    assert [each.rule_id for each in all_diagnostics] == ["context-budget"]
    assert (
        'section "Plan" has 7 detail lines and no pointer (limit 6)'
        in all_diagnostics[0].message
    )
    assert "reference/plan.md" in all_diagnostics[0].message


def test_a_repository_without_a_policy_file_is_not_checked(tmp_path: Path) -> None:
    assert (
        adapters.context_budget_diagnostics(
            _document(_SKILL_PATH, _section("Plan", 9)), tmp_path
        )
        == ()
    )


def test_a_changed_listed_file_below_its_record_must_lower_its_entry(
    tmp_path: Path,
) -> None:
    prior_text = _section("Plan", 7) + "\n" * 10
    _write_policy(
        tmp_path, _policy({_SKILL_PATH: {"lines": 18, "sections": ["Plan"]}}, 10)
    )

    all_diagnostics = adapters.context_budget_diagnostics(
        _document(_SKILL_PATH, _section("Plan", 7) + "\n" * 5, prior_text), tmp_path
    )

    assert len(all_diagnostics) == 1
    assert '{"lines": 13, "sections": ["Plan"]}' in all_diagnostics[0].message


def test_raising_a_baseline_entry_is_a_shrink_only_finding(tmp_path: Path) -> None:
    prior_text = json.dumps(_policy({_SKILL_PATH: {"lines": 300, "sections": []}}))
    current_text = json.dumps(_policy({_SKILL_PATH: {"lines": 310, "sections": []}}))

    all_diagnostics = adapters.context_budget_policy_diagnostics(
        _document(_POLICY_PATH, current_text, prior_text), tmp_path
    )

    assert [each.rule_id for each in all_diagnostics] == ["context-budget-policy"]
    assert "the over-budget list may only shrink" in all_diagnostics[0].message


def test_a_new_or_shrunk_policy_file_passes_and_a_malformed_one_reports(
    tmp_path: Path,
) -> None:
    prior_text = json.dumps(_policy({_SKILL_PATH: {"lines": 300, "sections": []}}))
    shrunk_text = json.dumps(_policy())

    assert (
        adapters.context_budget_policy_diagnostics(
            _document(_POLICY_PATH, shrunk_text, prior_text), tmp_path
        )
        == ()
    )
    assert (
        adapters.context_budget_policy_diagnostics(
            _document(_POLICY_PATH, shrunk_text), tmp_path
        )
        == ()
    )
    malformed = adapters.context_budget_policy_diagnostics(
        _document(_POLICY_PATH, "{broken"), tmp_path
    )
    assert "does not parse" in malformed[0].message
