"""The over-budget list may only shrink."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_budget.tests.budget_support import policy_text, section_text
from context_budget.policy_changes import policy_shrink_findings
from context_budget.policy_file import parse_policy


@pytest.mark.parametrize(
    ("mutation", "expected_fragment"),
    [
        (
            lambda raw: raw["baseline"]["files"].update(
                {"b/SKILL.md": {"lines": 300, "sections": []}}
            ),
            'adds file "b/SKILL.md"',
        ),
        (
            lambda raw: raw["baseline"]["files"]["a/SKILL.md"].update({"lines": 301}),
            "from 300 to 301 lines",
        ),
        (
            lambda raw: raw["baseline"]["files"]["a/SKILL.md"]["sections"].append("X"),
            'adds section "X"',
        ),
        (lambda raw: raw["baseline"]["hooks"].update({"other": 1600}), 'adds hook "other"'),
        (
            lambda raw: raw["baseline"]["hooks"].update({"greeter": 2001}),
            "from 2000 to 2001 characters",
        ),
        (lambda raw: raw.update({"section_detail_line_limit": 7}), "rises from 6 to 7"),
        (
            lambda raw: raw["kinds"][1].update({"line_limit": 250}),
            "line_limit rises from 200 to 250",
        ),
        (lambda raw: raw["kinds"].pop(2), 'kind "rule" is deleted'),
        (
            lambda raw: raw["kinds"][1].update({"patterns": ["no-skills/*.md"]}),
            'kind "skill entry" patterns change',
        ),
        (lambda raw: raw["kinds"].reverse(), "kind selection order changes"),
        (lambda raw: raw["hooks"].clear(), 'hook "greeter" is deleted'),
        (
            lambda raw: raw["hooks"][0].update({"char_limit": 1501}),
            "char_limit rises from 1500 to 1501",
        ),
    ],
)
def test_policy_change_that_loosens_the_budget_is_a_finding(
    mutation, expected_fragment: str, tmp_path: Path
) -> None:
    (tmp_path / "g.py").write_text("", encoding="utf-8")
    raw_prior = json.loads(policy_text({"a/SKILL.md": {"lines": 300, "sections": []}}))
    raw_prior["baseline"]["hooks"] = {"greeter": 2000}
    raw_current = json.loads(json.dumps(raw_prior))
    mutation(raw_current)

    all_findings = policy_shrink_findings(
        ".claude/context-budget.json",
        parse_policy(json.dumps(raw_prior)),
        parse_policy(json.dumps(raw_current)),
        tmp_path,
    )

    assert len(all_findings) == 1
    assert expected_fragment in all_findings[0].message
    assert "the over-budget list may only shrink" in all_findings[0].message


def test_deleting_a_hook_whose_script_is_still_in_the_tree_is_a_finding(
    tmp_path: Path,
) -> None:
    (tmp_path / "g.py").write_text("", encoding="utf-8")
    raw_prior = json.loads(policy_text())
    raw_current = json.loads(json.dumps(raw_prior))
    raw_current["hooks"].clear()

    all_findings = policy_shrink_findings(
        "p", parse_policy(json.dumps(raw_prior)), parse_policy(json.dumps(raw_current)), tmp_path
    )

    assert len(all_findings) == 1
    assert 'hook "greeter" is deleted' in all_findings[0].message


def test_deleting_a_hook_together_with_its_script_passes(tmp_path: Path) -> None:
    raw_prior = json.loads(policy_text())
    raw_current = json.loads(json.dumps(raw_prior))
    raw_current["hooks"].clear()

    assert policy_shrink_findings(
        "p", parse_policy(json.dumps(raw_prior)), parse_policy(json.dumps(raw_current)), tmp_path
    ) == ()


def test_policy_change_that_shrinks_or_adds_the_file_passes(tmp_path: Path) -> None:
    prior_policy = parse_policy(policy_text({"a/SKILL.md": {"lines": 300, "sections": ["X"]}}))
    shrunk_policy = parse_policy(policy_text({"a/SKILL.md": {"lines": 250, "sections": []}}))
    nulled_policy = parse_policy(policy_text({"a/SKILL.md": {"lines": None, "sections": ["X"]}}))

    assert policy_shrink_findings("p", prior_policy, shrunk_policy, tmp_path) == ()
    assert policy_shrink_findings("p", prior_policy, nulled_policy, tmp_path) == ()
    assert policy_shrink_findings("p", None, shrunk_policy, tmp_path) == ()


def test_policy_change_from_null_lines_to_a_number_fails_shrink_only(tmp_path: Path) -> None:
    prior_policy = parse_policy(policy_text({"a/SKILL.md": {"lines": None, "sections": ["X"]}}))
    numbered_policy = parse_policy(policy_text({"a/SKILL.md": {"lines": 250, "sections": ["X"]}}))

    all_findings = policy_shrink_findings("p", prior_policy, numbered_policy, tmp_path)

    assert len(all_findings) == 1
    assert 'records 250 lines for "a/SKILL.md"' in all_findings[0].message
    assert "the over-budget list may only shrink" in all_findings[0].message


@pytest.mark.parametrize("position", [0, 1])
def test_a_new_kind_cannot_precede_an_existing_kind(position: int, tmp_path: Path) -> None:
    raw_prior = json.loads(policy_text())
    raw_current = json.loads(json.dumps(raw_prior))
    raw_current["kinds"].insert(
        position,
        {"name": "unlimited", "patterns": ["**/*"], "line_limit": None},
    )

    findings = policy_shrink_findings(
        "p",
        parse_policy(json.dumps(raw_prior)),
        parse_policy(json.dumps(raw_current)),
        tmp_path,
    )

    assert len(findings) == 1
    assert "kind selection order changes" in findings[0].message


def test_a_duplicate_name_cannot_hide_a_raised_limit(tmp_path: Path) -> None:
    raw_prior = json.loads(policy_text())
    raw_current = json.loads(json.dumps(raw_prior))
    raw_current["kinds"][1]["line_limit"] = None
    raw_current["kinds"].append(raw_prior["kinds"][1])

    findings = policy_shrink_findings(
        "p",
        parse_policy(json.dumps(raw_prior)),
        parse_policy(json.dumps(raw_current)),
        tmp_path,
    )

    assert len(findings) == 1
    assert "kind selection order changes" in findings[0].message


def test_appending_a_kind_and_tightening_limits_passes(tmp_path: Path) -> None:
    raw_prior = json.loads(policy_text())
    raw_current = json.loads(json.dumps(raw_prior))
    raw_current["kinds"][1]["line_limit"] = 100
    raw_current["hooks"][0]["char_limit"] = 1000
    raw_current["section_detail_line_limit"] = 5
    raw_current["kinds"].append(
        {"name": "extra", "patterns": ["extra/*.md"], "line_limit": 20}
    )

    assert policy_shrink_findings(
        "p",
        parse_policy(json.dumps(raw_prior)),
        parse_policy(json.dumps(raw_current)),
        tmp_path,
    ) == ()


def _policy_without_baseline_key() -> dict:
    raw_policy = json.loads(policy_text())
    del raw_policy["baseline"]
    return raw_policy


def _policy_with_first_list() -> dict:
    raw_policy = json.loads(policy_text({"a/SKILL.md": {"lines": 300, "sections": ["X"]}}))
    raw_policy["baseline"]["hooks"] = {"greeter": 2000}
    return raw_policy


def _write_over_budget_skill(repository_root: Path) -> None:
    skill_text = section_text("X", 7)
    filler_line_count = 300 - len(skill_text.splitlines())
    (repository_root / "a").mkdir()
    (repository_root / "a" / "SKILL.md").write_text(
        skill_text + "\n" * filler_line_count, encoding="utf-8"
    )


def _first_list_findings(raw_current: dict, repository_root: Path) -> tuple:
    return policy_shrink_findings(
        "p",
        parse_policy(json.dumps(_policy_without_baseline_key())),
        parse_policy(json.dumps(raw_current)),
        repository_root,
    )


def test_first_baseline_that_matches_the_tree_passes(tmp_path: Path) -> None:
    _write_over_budget_skill(tmp_path)

    assert _first_list_findings(_policy_with_first_list(), tmp_path) == ()


@pytest.mark.parametrize(
    ("mutation", "expected_fragment"),
    [
        (
            lambda raw: raw["baseline"]["files"]["a/SKILL.md"].update({"lines": 400}),
            'baseline raises "a/SKILL.md" from 300 to 400 lines',
        ),
        (
            lambda raw: raw["baseline"]["files"]["a/SKILL.md"]["sections"].append("Y"),
            'baseline adds section "Y" to "a/SKILL.md"',
        ),
        (
            lambda raw: raw["baseline"]["files"].update(
                {"b/SKILL.md": {"lines": 300, "sections": []}}
            ),
            'baseline adds file "b/SKILL.md"',
        ),
    ],
)
def test_first_baseline_entry_beyond_the_tree_is_a_finding(
    mutation, expected_fragment: str, tmp_path: Path
) -> None:
    _write_over_budget_skill(tmp_path)
    raw_current = _policy_with_first_list()
    mutation(raw_current)

    all_findings = _first_list_findings(raw_current, tmp_path)

    assert len(all_findings) == 1
    assert expected_fragment in all_findings[0].message
    assert "the over-budget list may only shrink" in all_findings[0].message


def test_first_baseline_entry_for_a_file_within_budget_is_a_finding(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "SKILL.md").write_text("# Short\n", encoding="utf-8")

    all_findings = _first_list_findings(_policy_with_first_list(), tmp_path)

    assert len(all_findings) == 1
    assert 'baseline adds file "a/SKILL.md"' in all_findings[0].message


def test_first_baseline_added_to_an_explicit_empty_baseline_is_a_finding(
    tmp_path: Path,
) -> None:
    _write_over_budget_skill(tmp_path)

    all_findings = policy_shrink_findings(
        "p",
        parse_policy(policy_text()),
        parse_policy(json.dumps(_policy_with_first_list())),
        tmp_path,
    )

    assert len(all_findings) == 2
    assert 'baseline adds file "a/SKILL.md"' in all_findings[0].message
    assert 'baseline adds hook "greeter"' in all_findings[1].message


def test_deleting_the_baseline_key_is_a_finding(tmp_path: Path) -> None:
    all_findings = policy_shrink_findings(
        "p",
        parse_policy(policy_text()),
        parse_policy(json.dumps(_policy_without_baseline_key())),
        tmp_path,
    )

    assert len(all_findings) == 1
    assert 'the "baseline" key is deleted' in all_findings[0].message
    assert "the over-budget list may only shrink" in all_findings[0].message


def test_first_baseline_still_holds_the_limits_to_the_prior_policy(tmp_path: Path) -> None:
    _write_over_budget_skill(tmp_path)
    raw_current = _policy_with_first_list()
    raw_current["kinds"][1]["line_limit"] = 250

    all_findings = _first_list_findings(raw_current, tmp_path)

    assert len(all_findings) == 1
    assert "line_limit rises from 200 to 250" in all_findings[0].message


def test_raising_the_prose_line_word_limit_is_a_loosening_change(tmp_path: Path) -> None:
    raw_prior = json.loads(policy_text())
    raw_prior["prose_line_word_limit"] = 25
    raw_current = json.loads(policy_text())
    raw_current["prose_line_word_limit"] = 40
    prior_policy = parse_policy(json.dumps(raw_prior))

    raised = policy_shrink_findings(
        "p", prior_policy, parse_policy(json.dumps(raw_current)), tmp_path
    )
    raw_current["prose_line_word_limit"] = 10
    lowered = policy_shrink_findings(
        "p", prior_policy, parse_policy(json.dumps(raw_current)), tmp_path
    )

    assert "prose_line_word_limit rises from 25 to 40" in raised[0].message
    assert lowered == ()
