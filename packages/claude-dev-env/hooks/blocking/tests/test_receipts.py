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
    open_receipt_path,
    receipt_path,
    same_commit,
)

HEAD = "abc1234def5678abc1234def5678abc1234def56"


@pytest.fixture(autouse=True)
def receipt_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_RECEIPT_DIR", str(tmp_path))
    return tmp_path


def _write_open_receipt(finding_count: int) -> None:
    path = open_receipt_path("acme", "tools", HEAD)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"head": HEAD, "findings": finding_count}), encoding="utf-8")


def test_should_find_a_clean_open_review_by_short_head_under_any_owner() -> None:
    _write_open_receipt(0)
    assert has_clean_open_review("Tools", HEAD[:7]) is True


def test_should_reject_an_open_review_that_counts_findings() -> None:
    _write_open_receipt(1)
    assert has_clean_open_review("tools", HEAD[:7]) is False


def test_should_reject_a_head_that_is_not_a_commit() -> None:
    _write_open_receipt(0)
    assert has_clean_open_review("tools", "main") is False


def test_should_lowercase_owner_and_repo_in_the_numbered_receipt_path(receipt_folder: Path) -> None:
    assert receipt_path("Acme", "Tools", 12) == receipt_folder / "acme__tools__12.json"


def test_should_match_commits_by_prefix_in_either_order() -> None:
    assert same_commit(HEAD[:7].upper(), HEAD) is True
    assert same_commit(HEAD, "def5678") is False
