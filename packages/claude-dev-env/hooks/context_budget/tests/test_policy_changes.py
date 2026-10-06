"""The over-budget list may only shrink."""

from __future__ import annotations

import json

import pytest

from context_budget.tests.budget_support import policy_text
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
    mutation, expected_fragment: str
) -> None:
    raw_prior = json.loads(policy_text({"a/SKILL.md": {"lines": 300, "sections": []}}))
    raw_prior["baseline"]["hooks"] = {"greeter": 2000}
    raw_current = json.loads(json.dumps(raw_prior))
    mutation(raw_current)

    all_findings = policy_shrink_findings(
        ".claude/context-budget.json",
        parse_policy(json.dumps(raw_prior)),
        parse_policy(json.dumps(raw_current)),
    )

    assert len(all_findings) == 1
    assert expected_fragment in all_findings[0].message
    assert "the over-budget list may only shrink" in all_findings[0].message


def test_policy_change_that_shrinks_or_adds_the_file_passes() -> None:
    prior_policy = parse_policy(policy_text({"a/SKILL.md": {"lines": 300, "sections": ["X"]}}))
    shrunk_policy = parse_policy(policy_text({"a/SKILL.md": {"lines": 250, "sections": []}}))
    nulled_policy = parse_policy(policy_text({"a/SKILL.md": {"lines": None, "sections": ["X"]}}))

    assert policy_shrink_findings("p", prior_policy, shrunk_policy) == ()
    assert policy_shrink_findings("p", prior_policy, nulled_policy) == ()
    assert policy_shrink_findings("p", None, shrunk_policy) == ()


def test_policy_change_from_null_lines_to_a_number_fails_shrink_only() -> None:
    prior_policy = parse_policy(policy_text({"a/SKILL.md": {"lines": None, "sections": ["X"]}}))
    numbered_policy = parse_policy(policy_text({"a/SKILL.md": {"lines": 250, "sections": ["X"]}}))

    all_findings = policy_shrink_findings("p", prior_policy, numbered_policy)

    assert len(all_findings) == 1
    assert 'records 250 lines for "a/SKILL.md"' in all_findings[0].message
    assert "the over-budget list may only shrink" in all_findings[0].message


@pytest.mark.parametrize("position", [0, 1])
def test_a_new_kind_cannot_precede_an_existing_kind(position: int) -> None:
    raw_prior = json.loads(policy_text())
    raw_current = json.loads(json.dumps(raw_prior))
    raw_current["kinds"].insert(
        position,
        {"name": "unlimited", "patterns": ["**/*"], "line_limit": None},
    )

    findings = policy_shrink_findings(
        "p", parse_policy(json.dumps(raw_prior)), parse_policy(json.dumps(raw_current))
    )

    assert len(findings) == 1
    assert "kind selection order changes" in findings[0].message


def test_a_duplicate_name_cannot_hide_a_raised_limit() -> None:
    raw_prior = json.loads(policy_text())
    raw_current = json.loads(json.dumps(raw_prior))
    raw_current["kinds"][1]["line_limit"] = None
    raw_current["kinds"].append(raw_prior["kinds"][1])

    findings = policy_shrink_findings(
        "p", parse_policy(json.dumps(raw_prior)), parse_policy(json.dumps(raw_current))
    )

    assert len(findings) == 1
    assert "kind selection order changes" in findings[0].message


def test_appending_a_kind_and_tightening_limits_passes() -> None:
    raw_prior = json.loads(policy_text())
    raw_current = json.loads(json.dumps(raw_prior))
    raw_current["kinds"][1]["line_limit"] = 100
    raw_current["hooks"][0]["char_limit"] = 1000
    raw_current["section_detail_line_limit"] = 5
    raw_current["kinds"].append(
        {"name": "extra", "patterns": ["extra/*.md"], "line_limit": 20}
    )

    assert policy_shrink_findings(
        "p", parse_policy(json.dumps(raw_prior)), parse_policy(json.dumps(raw_current))
    ) == ()
