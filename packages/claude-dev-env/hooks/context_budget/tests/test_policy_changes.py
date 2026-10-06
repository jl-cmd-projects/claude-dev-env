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

    assert policy_shrink_findings("p", prior_policy, shrunk_policy) == ()
    assert policy_shrink_findings("p", None, shrunk_policy) == ()
