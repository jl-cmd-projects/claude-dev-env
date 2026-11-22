"""Behavioral tests for the merge review receipt readers.

open receipt {head: <full sha>, findings: 0}, head <short sha> -> clean
open receipt {head: <full sha>, findings: 1}, head <short sha> -> not clean
numbered receipt path                                         -> lowercased owner and repo
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from blocking.merge_review_gate_parts.receipts import (
    has_clean_open_review,
    open_reviewed_heads_among,
    has_zero_finding_open_review,
    is_clean_open_pass,
    is_filed_receipt,
    is_issue_link_in,
    is_past_full_passes,
    open_receipt_path,
    read_receipt,
    receipt_path,
    recorded_open_finding_count,
    recorded_pass_number,
    same_commit,
)

HEAD = "abc1234def5678abc1234def5678abc1234def56"
RULINGS_LINK = "https://github.com/acme/tools/pull/12#issuecomment-1"


@pytest.fixture(autouse=True)
def receipt_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_RECEIPT_DIR", str(tmp_path))
    return tmp_path


def _write_open_receipt(finding_count: int, all_extra_fields: dict[str, object] | None = None) -> None:
    path = open_receipt_path("acme", "tools", HEAD)
    path.parent.mkdir(parents=True, exist_ok=True)
    all_receipt_fields = {"head": HEAD, "findings": finding_count, **(all_extra_fields or {})}
    path.write_text(json.dumps(all_receipt_fields), encoding="utf-8")


def test_should_find_a_clean_open_review_by_short_head_under_any_owner() -> None:
    _write_open_receipt(0)
    assert has_clean_open_review("Tools", HEAD[:7]) is True


def test_should_reject_an_open_review_that_counts_findings() -> None:
    _write_open_receipt(1)
    assert has_clean_open_review("tools", HEAD[:7]) is False


def test_should_reject_a_head_that_is_not_a_commit() -> None:
    _write_open_receipt(0)
    assert has_clean_open_review("tools", "main") is False


def test_should_find_an_open_review_whose_findings_are_ruled_out_at_file_and_line() -> None:
    _write_open_receipt(2, {"ruled_out": 2, "ruling_lines": ["a.py:1", "b.py:20"]})
    assert has_clean_open_review("tools", HEAD[:7]) is True


def test_should_reject_an_open_review_whose_rulings_cover_fewer_findings() -> None:
    _write_open_receipt(2, {"ruled_out": 2, "ruling_lines": ["a.py:1"]})
    assert has_clean_open_review("tools", HEAD[:7]) is False


@pytest.mark.parametrize("finding_count", [0, 2])
def test_should_find_an_open_review_on_an_earlier_commit_whatever_it_found(
    finding_count: int,
) -> None:
    _write_open_receipt(finding_count, {"branch": "feature"})
    assert open_reviewed_heads_among("Tools", ["1" * 40, HEAD.upper()], "feature") == [HEAD]


def test_should_find_no_open_review_among_commits_it_did_not_review() -> None:
    _write_open_receipt(2, {"branch": "feature"})
    assert open_reviewed_heads_among("tools", ["1" * 40], "feature") == []
    assert open_reviewed_heads_among("other", [HEAD], "feature") == []


def test_should_find_no_earlier_open_review_recorded_on_another_branch() -> None:
    _write_open_receipt(2, {"branch": "feature"})
    assert open_reviewed_heads_among("tools", [HEAD], "second") == []


def test_should_find_no_earlier_open_review_whose_receipt_names_no_branch() -> None:
    _write_open_receipt(2)
    assert open_reviewed_heads_among("tools", [HEAD], "feature") == []


def test_should_list_only_receipts_with_no_branch_when_asked_for_no_branch() -> None:
    _write_open_receipt(2)
    assert open_reviewed_heads_among("tools", [HEAD], None) == [HEAD]
    _write_open_receipt(2, {"branch": "feature"})
    assert open_reviewed_heads_among("tools", [HEAD], None) == []


def test_should_skip_an_open_review_whose_finding_count_is_not_a_count() -> None:
    path = open_receipt_path("acme", "tools", HEAD)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"head": HEAD, "findings": "two", "branch": "feature"}), encoding="utf-8"
    )
    assert open_reviewed_heads_among("tools", [HEAD], "feature") == []


def test_should_find_a_zero_finding_open_review_by_short_head() -> None:
    _write_open_receipt(0)
    assert has_zero_finding_open_review("tools", HEAD[:7]) is True


@pytest.mark.parametrize(
    "extra_fields",
    [{}, {"ruled_out": 2, "ruling_lines": ["a.py:1", "b.py:20"]}],
)
def test_should_reject_a_zero_finding_open_review_when_findings_were_reported(
    extra_fields: dict[str, object],
) -> None:
    _write_open_receipt(2, extra_fields)
    assert has_zero_finding_open_review("tools", HEAD[:7]) is False


def test_should_reject_a_zero_finding_open_review_for_a_head_that_is_not_a_commit() -> None:
    _write_open_receipt(0)
    assert has_zero_finding_open_review("tools", "main") is False


def test_should_count_an_open_pass_with_no_findings_as_clean() -> None:
    assert is_clean_open_pass({"head": HEAD, "findings": 0}) is True


def test_should_count_an_open_pass_with_every_finding_ruled_out_as_clean() -> None:
    all_receipt_fields = {
        "head": HEAD,
        "findings": 3,
        "ruled_out": 3,
        "ruling_lines": ["a.py:1", "src/b.py:20", "docs/c.md:7"],
    }
    assert is_clean_open_pass(all_receipt_fields) is True


def test_should_count_an_open_pass_ruled_out_at_paths_with_spaces_and_dots_as_clean() -> None:
    all_receipt_fields = {
        "head": HEAD,
        "findings": 3,
        "ruled_out": 3,
        "ruling_lines": ["docs/My Notes.md:4", ".github/ci.yml:2", "src/..hidden/a.py:9"],
    }
    assert is_clean_open_pass(all_receipt_fields) is True


@pytest.mark.parametrize(
    "extra_fields",
    [
        {},
        {"ruled_out": 1, "ruling_lines": ["a.py:1", "b.py:2"]},
        {"ruled_out": 2, "ruling_lines": ["a.py:1"]},
        {"ruled_out": 2, "ruling_lines": ["a.py:1", "b.py:2", "c.py:3"]},
        {"ruled_out": 2, "rulings": RULINGS_LINK},
        {"ruled_out": 2, "ruling_lines": ["a.py:1", "see the thread"]},
        {"ruled_out": 2, "ruling_lines": ["a.py:1", "b.py:0"]},
        {"ruled_out": 2, "ruling_lines": ["a.py:1", 7]},
        {"ruled_out": 2, "ruling_lines": ["a.py:1", "a.py:1"]},
        {"ruled_out": 2, "ruling_lines": ["a.py:1", "b.py:2", "a.py:1"]},
        {"ruled_out": 2, "ruling_lines": ["a.py:1", "./a.py:1"]},
        {"ruled_out": 2, "ruling_lines": ["a.py:1", "docs/../a.py:2"]},
        {"ruled_out": 2, "ruling_lines": ["a.py:1", "/a.py:2"]},
        {"ruled_out": 2, "ruling_lines": ["a.py:1", "docs//notes.txt:1"]},
        {"ruled_out": 2, "ruling_lines": ["a.py:1", "docs/:1"]},
        {"ruled_out": True, "ruling_lines": ["a.py:1", "b.py:2"]},
    ],
)
def test_should_reject_an_open_pass_whose_rulings_do_not_prove_each_finding(
    extra_fields: dict[str, object],
) -> None:
    assert is_clean_open_pass({"head": HEAD, "findings": 2, **extra_fields}) is False


@pytest.mark.parametrize("finding_count", [-1, True, "0", None])
def test_should_reject_an_open_pass_whose_finding_count_is_not_a_count(
    finding_count: object,
) -> None:
    assert is_clean_open_pass({"head": HEAD, "findings": finding_count}) is False


def test_should_lowercase_owner_and_repo_in_the_numbered_receipt_path(receipt_folder: Path) -> None:
    assert receipt_path("Acme", "Tools", 12) == receipt_folder / "acme__tools__12.json"


def test_should_match_commits_by_prefix_in_either_order() -> None:
    assert same_commit(HEAD[:7].upper(), HEAD) is True
    assert same_commit(HEAD, "def5678") is False


ISSUE_LINK = "https://github.com/acme/tools/issues/40"


def test_should_read_a_receipt_object_and_nothing_else(receipt_folder: Path) -> None:
    path = receipt_folder / "receipt.json"
    assert read_receipt(path) is None
    path.write_text("[1, 2]", encoding="utf-8")
    assert read_receipt(path) is None
    path.write_text('{"head": "abc1234", "findings": 0}', encoding="utf-8")
    assert read_receipt(path) == {"head": "abc1234", "findings": 0}


@pytest.mark.parametrize(
    ("pass_field", "expected_pass"),
    [({"pass": 4}, 4), ({}, 1), ({"pass": "4"}, 1), ({"pass": 0}, 1), ({"pass": True}, 1)],
)
def test_should_count_a_receipt_without_a_pass_number_as_pass_one(
    pass_field: dict[str, object], expected_pass: int
) -> None:
    assert recorded_pass_number({"head": HEAD, "findings": 2, **pass_field}) == expected_pass


def test_should_put_only_pass_four_and_later_past_the_full_passes() -> None:
    assert is_past_full_passes(3) is False
    assert is_past_full_passes(4) is True


@pytest.mark.parametrize(
    ("link", "is_expected_match"),
    [
        ("https://github.com/Acme/Tools/issues/40", True),
        ("https://github.com/acme/other/issues/40", False),
        ("https://github.com/acme/tools/pull/40", False),
        ("https://github.com/acme/tools/issues/40#issuecomment-1", False),
        ("https://github.com/acme/tools/issues/12", False),
        (40, False),
    ],
)
def test_should_match_only_an_issue_link_in_the_named_repository(
    link: object, is_expected_match: bool
) -> None:
    assert is_issue_link_in(link, "acme", "tools", 12) is is_expected_match


@pytest.mark.parametrize(
    ("receipt_fields", "is_expected_filed"),
    [
        ({"findings": 2, "pass": 4, "filed": ISSUE_LINK}, True),
        ({"findings": 2, "pass": 3, "filed": ISSUE_LINK}, False),
        ({"findings": 2, "pass": 4}, False),
        ({"findings": 2, "pass": 4, "filed": "https://github.com/acme/other/issues/40"}, False),
        ({"findings": "2", "pass": 4, "filed": ISSUE_LINK}, False),
        ({"findings": 2, "pass": 4, "filed": "https://github.com/acme/tools/issues/12"}, False),
        (
            {"findings": 3, "pass": 4, "ruled_out": 1, "rulings": RULINGS_LINK, "filed": ISSUE_LINK},
            True,
        ),
        (
            {
                "findings": 3,
                "pass": 4,
                "ruled_out": 1,
                "rulings": "https://github.com/acme/tools/pull/99#issuecomment-1",
                "filed": ISSUE_LINK,
            },
            False,
        ),
        ({"findings": 3, "pass": 4, "ruled_out": 1, "filed": ISSUE_LINK}, False),
        (
            {"findings": 3, "pass": 4, "ruled_out": "1", "rulings": RULINGS_LINK, "filed": ISSUE_LINK},
            False,
        ),
        (
            {"findings": 3, "pass": 4, "ruled_out": 3, "rulings": RULINGS_LINK, "filed": ISSUE_LINK},
            False,
        ),
    ],
)
def test_should_count_a_pass_as_filed_only_after_three_full_passes(
    receipt_fields: dict[str, object], is_expected_filed: bool
) -> None:
    assert (
        is_filed_receipt({"head": HEAD, **receipt_fields}, "acme", "tools", 12) is is_expected_filed
    )


def test_should_read_the_finding_count_of_a_pass_recorded_at_a_head() -> None:
    assert recorded_open_finding_count("tools", HEAD) is None
    _write_open_receipt(3)
    assert recorded_open_finding_count("Tools", HEAD[:7]) == 3
    assert recorded_open_finding_count("tools", "9" * 40) is None
    assert recorded_open_finding_count("other", HEAD) is None
