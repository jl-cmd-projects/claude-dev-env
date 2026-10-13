"""Tests for the merge review receipt recorder."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

import merge_review_receipt

HEAD = "abc1234def5678abc1234def5678abc1234def56"


@pytest.fixture(autouse=True)
def receipt_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_RECEIPT_DIR", str(tmp_path))
    return tmp_path


def test_should_print_clean_and_exit_zero_for_a_pass_with_no_findings(receipt_folder: Path) -> None:
    verdict_stream = StringIO()
    assert merge_review_receipt.main(["acme/tools", "12", HEAD, "0"], verdict_stream) == 0
    assert verdict_stream.getvalue() == f"CLEAN acme/tools#12 {HEAD}\n"


def test_should_exit_one_and_count_findings_for_a_pass_with_findings() -> None:
    verdict_stream = StringIO()
    assert merge_review_receipt.main(["acme/tools", "12", HEAD, "3"], verdict_stream) == 1
    assert verdict_stream.getvalue() == f"REVIEWED acme/tools#12 {HEAD} 3 findings\n"


def test_record_review_replaces_the_previous_pass(receipt_folder: Path) -> None:
    merge_review_receipt.record_review("Acme/Tools", 12, "old", 4)
    path = merge_review_receipt.record_review("Acme/Tools", 12, HEAD, 0)
    assert path == receipt_folder / "acme__tools__12.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"head": HEAD, "findings": 0}
