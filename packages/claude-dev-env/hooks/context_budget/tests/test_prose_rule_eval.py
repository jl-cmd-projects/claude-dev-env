"""Grade the prose rule on labeled agent and Claude instruction files.

Each case's label comes from the rule's text, not from the checker's output.
A case is positive when the prose rule must report a finding for its file.
The scope strings are spelled out here so the eval grades the findings the
rule reports, not the constants that produce them.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from context_budget.findings import file_findings
from context_budget.policy_file import default_policy

NO_POINTER_SCOPE = "no pointer line"
LONG_LINE_SCOPE_PREFIX = "prose line: "
POINTER_LINE = "Read [the plan](reference/plan.md)."


@dataclass(frozen=True)
class LabeledCase:
    """One file and whether the prose rule must reject it.

    Attributes:
        name: Test id.
        path: Repository-relative POSIX path.
        text: File text.
        should_fail: Whether the prose rule must report a finding.
    """

    name: str
    path: str
    text: str
    should_fail: bool


def _words(count: int) -> str:
    return " ".join(["word"] * count)


ALL_LABELED_CASES = (
    LabeledCase("blank-agents-file", "app/AGENTS.md", "", False),
    LabeledCase("import-only-agents-file", "app/AGENTS.md", "@CLAUDE.md\n", False),
    LabeledCase("relative-import-claude-file", "app/CLAUDE.md", "@../AGENTS.md\n", False),
    LabeledCase(
        "link-index",
        "app/AGENTS.md",
        "# Index\n- [Plan](reference/plan.md)\n- [Rules](reference/rules.md)\n",
        False,
    ),
    LabeledCase("one-pointer-line", "app/AGENTS.md", f"{POINTER_LINE}\n", False),
    LabeledCase(
        "prose-without-pointer",
        "app/AGENTS.md",
        "Selection records own icon choice.\n",
        True,
    ),
    LabeledCase(
        "long-unlinked-line-with-pointer",
        "app/AGENTS.md",
        f"{_words(26)}\n{POINTER_LINE}\n",
        True,
    ),
    LabeledCase(
        "line-at-word-limit",
        "app/AGENTS.md",
        f"{_words(25)}\n{POINTER_LINE}\n",
        False,
    ),
    LabeledCase(
        "long-line-with-its-own-link",
        "app/CLAUDE.md",
        f"{_words(26)} [plan](reference/plan.md)\n",
        False,
    ),
    LabeledCase(
        "import-with-long-unlinked-line",
        "app/CLAUDE.md",
        f"@AGENTS.md\n{_words(26)}\n",
        True,
    ),
    LabeledCase("mention-is-not-an-import", "app/AGENTS.md", "@reviewer please review\n", True),
    LabeledCase(
        "long-list-item-with-link",
        "app/AGENTS.md",
        f"- {_words(30)} [plan](reference/plan.md)\n",
        False,
    ),
    LabeledCase(
        "long-line-inside-fence",
        "app/AGENTS.md",
        f"```\n{_words(30)}\n```\n{POINTER_LINE}\n",
        False,
    ),
    LabeledCase(
        "long-table-row",
        "app/AGENTS.md",
        f"| {_words(30)} |\n{POINTER_LINE}\n",
        False,
    ),
    LabeledCase(
        "short-intro-lines-with-pointer",
        "app/AGENTS.md",
        f"Holds shared helpers.\nCallers copy and publish trees.\n{POINTER_LINE}\n",
        False,
    ),
    LabeledCase("not-an-agent-file", "docs/notes.md", f"{_words(40)}\n", False),
    LabeledCase(
        "import-and-pointer-claude-file",
        "app/CLAUDE.md",
        f"@AGENTS.md\n{POINTER_LINE}\n",
        False,
    ),
    LabeledCase(
        "wordy-paragraph-with-pointer",
        "app/AGENTS.md",
        f"{_words(52)}\n{POINTER_LINE}\n",
        True,
    ),
)


def _prose_rule_fails(each_case: LabeledCase) -> bool:
    all_findings = file_findings(default_policy(), each_case.path, each_case.text, None)
    return any(
        each_finding.scope == NO_POINTER_SCOPE
        or each_finding.scope.startswith(LONG_LINE_SCOPE_PREFIX)
        for each_finding in all_findings
    )


@pytest.mark.parametrize("each_case", ALL_LABELED_CASES, ids=lambda each_case: each_case.name)
def test_prose_rule_grades_each_labeled_case_as_labeled(each_case: LabeledCase) -> None:
    assert _prose_rule_fails(each_case) == each_case.should_fail


def test_prose_rule_confusion_matrix_has_perfect_precision_and_recall() -> None:
    all_outcomes = [
        (each_case.should_fail, _prose_rule_fails(each_case)) for each_case in ALL_LABELED_CASES
    ]

    true_positives = sum(each_label and each_grade for each_label, each_grade in all_outcomes)
    false_positives = sum(not each_label and each_grade for each_label, each_grade in all_outcomes)
    true_negatives = sum(
        not each_label and not each_grade for each_label, each_grade in all_outcomes
    )
    false_negatives = sum(each_label and not each_grade for each_label, each_grade in all_outcomes)

    assert (true_positives, false_positives, true_negatives, false_negatives) == (5, 0, 13, 0)
