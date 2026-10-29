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
    is_clean_open_pass,
    open_receipt_path,
    receipt_path,
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
    _write_open_receipt(2, {"ruled_out": 2, "rulings": ["a.py:1", "b.py:20"]})
    assert has_clean_open_review("tools", HEAD[:7]) is True


def test_should_reject_an_open_review_whose_rulings_cover_fewer_findings() -> None:
    _write_open_receipt(2, {"ruled_out": 2, "rulings": ["a.py:1"]})
    assert has_clean_open_review("tools", HEAD[:7]) is False


def test_should_count_an_open_pass_with_no_findings_as_clean() -> None:
    assert is_clean_open_pass({"head": HEAD, "findings": 0}) is True


def test_should_count_an_open_pass_with_every_finding_ruled_out_as_clean() -> None:
    all_receipt_fields = {
        "head": HEAD,
        "findings": 3,
        "ruled_out": 3,
        "rulings": ["a.py:1", "src/b.py:20", "docs/c.md:7"],
    }
    assert is_clean_open_pass(all_receipt_fields) is True


@pytest.mark.parametrize(
    "extra_fields",
    [
        {},
        {"ruled_out": 1, "rulings": ["a.py:1", "b.py:2"]},
        {"ruled_out": 2, "rulings": ["a.py:1"]},
        {"ruled_out": 2, "rulings": ["a.py:1", "b.py:2", "c.py:3"]},
        {"ruled_out": 2, "rulings": RULINGS_LINK},
        {"ruled_out": 2, "rulings": ["a.py:1", "see the thread"]},
        {"ruled_out": 2, "rulings": ["a.py:1", "b.py:0"]},
        {"ruled_out": 2, "rulings": ["a.py:1", 7]},
        {"ruled_out": True, "rulings": ["a.py:1", "b.py:2"]},
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
