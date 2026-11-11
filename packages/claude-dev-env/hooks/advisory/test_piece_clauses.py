"""Labelled corpus for the signals that show an author's words naming several pieces.

Each case is an author's own subject, title, or body and the pieces a reader
would count in it. A single behaviour with a compound object or an alternative
names one piece.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

advisory_directory = str(Path(__file__).resolve().parent)
if advisory_directory not in sys.path:
    sys.path.insert(0, advisory_directory)

import piece_clauses

MIXED_SUBJECT = (
    "fix(convert): always publish drawn icons, put Tips on the tray, stop the label smear"
)
MIXED_TITLE = "fix(convert): always publish, put Tips on the tray, draw a plain home label"

ALL_SINGLE_BEHAVIOUR_SUBJECTS = (
    "fix(lock): darken or lighten the lock video behind lock elements",
    "perf(themes): copy queued themes on a bounded thread pool",
    "feat(evals): add theme metadata evals with frozen dataset and rerun commands",
    "fix(convert): handle empty input",
    "fix(hooks): stop the crash when the file is missing, empty or locked",
    "docs(readme): explain the install, update and removal steps",
    "chore: release 1.2.3",
    "Merge branch 'main' into feature, and keep going",
    "fix: handle the (a, b) pair",
    "fix: show the `a, b` label",
    "feat(installer): install and update the Pele npm package (#2213)",
    "feat(io): add read and write helpers",
    "fix(ui): align start and stop buttons",
    "feat(io): add read, write and move helpers",
    "fix(ui): show start and end dates",
    "feat(x): add log and cache layers",
)


def _three_pair_body() -> str:
    return "\n".join(
        [
            "## What this does",
            "Publishes icons.",
            "",
            "## Proof in practice",
            "### Publish",
            "- Without the change: `run publish` printed `skipped`.",
            "- With the change: `run publish` printed `published`.",
            "### Tray",
            "Without the change: `run tray` showed no Tips.",
            "With the change: `run tray` showed Tips.",
            "### Label",
            "**Without it** the label smeared.",
            "**With it** the label drew plain.",
            "",
            "## Risk",
            "Low.",
        ]
    )


def test_a_mixed_subject_names_each_verb_led_clause() -> None:
    all_pieces = piece_clauses.subject_pieces(MIXED_SUBJECT)
    assert all_pieces == [
        "always publish drawn icons",
        "put Tips on the tray",
        "stop the label smear",
    ]


def test_a_mixed_title_names_each_verb_led_clause() -> None:
    all_pieces = piece_clauses.subject_pieces(MIXED_TITLE)
    assert all_pieces == [
        "always publish",
        "put Tips on the tray",
        "draw a plain home label",
    ]


@pytest.mark.parametrize("subject", ALL_SINGLE_BEHAVIOUR_SUBJECTS)
def test_a_single_behaviour_subject_names_no_set_of_pieces(subject: str) -> None:
    assert piece_clauses.subject_pieces(subject) == []


@pytest.mark.parametrize(
    "subject",
    [
        "fix(x): publish icons; draw the label",
        "fix(x): publish icons and draw the label",
        "fix(x): publish icons, and draw the label",
        "feat!: add the flag, remove the old flag",
        "fix(x): add retry to the uploader and log each failure",
    ],
)
def test_a_subject_that_joins_verb_led_clauses_names_two_pieces(subject: str) -> None:
    assert len(piece_clauses.subject_pieces(subject)) == 2


def test_a_subject_without_a_conventional_prefix_names_no_pieces() -> None:
    assert piece_clauses.subject_pieces("publish icons, draw the label") == []


def test_an_empty_subject_names_no_pieces() -> None:
    assert piece_clauses.subject_pieces("") == []


def test_a_body_with_three_proof_pairs_names_the_count() -> None:
    assert piece_clauses.proof_pair_count(_three_pair_body()) == 3


def test_a_body_with_one_proof_pair_counts_one() -> None:
    body = "## Proof in practice\nWithout the change: `a` failed.\nWith the change: `a` passed.\n"
    assert piece_clauses.proof_pair_count(body) == 1


def test_a_one_line_pair_counts_once() -> None:
    body = (
        "## Proof in practice\nWithout the change the publish failed; with it the publish passed.\n"
    )
    assert piece_clauses.proof_pair_count(body) == 1


def test_pairs_quoted_inside_a_fence_do_not_count() -> None:
    body = "\n".join(
        [
            "## Proof in practice",
            "```",
            "Without the change: x",
            "With the change: y",
            "Without the change: x",
            "With the change: y",
            "```",
        ]
    )
    assert piece_clauses.proof_pair_count(body) == 0


def test_a_body_with_no_proof_section_counts_no_pairs() -> None:
    assert piece_clauses.proof_pair_count("## What this does\nOne line.\n") == 0


def test_bold_led_bullets_under_what_this_does_name_the_topics() -> None:
    body = "\n".join(
        [
            "## What this does",
            "- **Always publish.** Icons ship.",
            "- **Tips on the tray:** shown.",
            "  - **Nested detail** is not a topic.",
            "",
            "## Risk",
            "- **Low** risk.",
        ]
    )
    assert piece_clauses.topic_bullets(body) == ["Always publish", "Tips on the tray"]


def test_before_and_after_labels_are_not_topics() -> None:
    body = "## What this does\n- **Before:** a\n- **After:** b\n"
    assert piece_clauses.topic_bullets(body) == []


def test_a_body_with_six_topics_names_six() -> None:
    all_lines = ["## What this does"] + [
        f"- **Topic {each_number}.** text" for each_number in range(6)
    ]
    assert len(piece_clauses.topic_bullets("\n".join(all_lines))) == 6


def test_bullets_inside_a_fence_are_not_topics() -> None:
    body = "## What this does\n```\n- **A** x\n- **B** y\n```\n"
    assert piece_clauses.topic_bullets(body) == []


def test_a_trailing_issue_reference_stays_out_of_the_last_piece() -> None:
    all_pieces = piece_clauses.subject_pieces("docs: link orphan pages and drop repeated sentences (#2223)")
    assert all_pieces == ["link orphan pages", "drop repeated sentences"]
