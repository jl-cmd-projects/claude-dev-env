"""Tests for the merge review receipt recorder."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

import merge_review_receipt

HEAD = "abc1234def5678abc1234def5678abc1234def56"
RULINGS_LINK = "https://github.com/acme/tools/pull/12#issuecomment-1"


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


def test_should_print_clean_when_every_finding_is_ruled_out_with_a_link() -> None:
    verdict_stream = StringIO()
    exit_code = merge_review_receipt.main(
        ["acme/tools", "12", HEAD, "2", "--ruled-out", "2", "--rulings", RULINGS_LINK],
        verdict_stream,
    )
    assert exit_code == 0
    assert verdict_stream.getvalue() == (
        f"CLEAN acme/tools#12 {HEAD} (2 findings ruled out: {RULINGS_LINK})\n"
    )


def test_should_record_the_rulings_link_without_surrounding_whitespace(
    receipt_folder: Path,
) -> None:
    verdict_stream = StringIO()
    exit_code = merge_review_receipt.main(
        ["acme/tools", "12", HEAD, "2", "--ruled-out", "2", "--rulings", f" {RULINGS_LINK}\n"],
        verdict_stream,
    )
    assert exit_code == 0
    assert verdict_stream.getvalue() == (
        f"CLEAN acme/tools#12 {HEAD} (2 findings ruled out: {RULINGS_LINK})\n"
    )
    (receipt_file,) = receipt_folder.rglob("*.json")
    assert json.loads(receipt_file.read_text(encoding="utf-8"))["rulings"] == RULINGS_LINK


def test_should_keep_the_raw_finding_count_beside_the_ruled_out_count(
    receipt_folder: Path,
) -> None:
    path = merge_review_receipt.record_review("acme/tools", 12, HEAD, 2, 2, RULINGS_LINK)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "head": HEAD,
        "findings": 2,
        "ruled_out": 2,
        "rulings": RULINGS_LINK,
    }


def test_should_report_reviewed_when_some_findings_stay_open() -> None:
    verdict_stream = StringIO()
    exit_code = merge_review_receipt.main(
        ["acme/tools", "12", HEAD, "3", "--ruled-out", "2", "--rulings", RULINGS_LINK],
        verdict_stream,
    )
    assert exit_code == 1
    assert verdict_stream.getvalue() == f"REVIEWED acme/tools#12 {HEAD} 3 findings\n"


@pytest.mark.parametrize(
    "extra_arguments",
    [["--ruled-out", "2"], ["--ruled-out", "4", "--rulings", RULINGS_LINK], ["--ruled-out", "-1"]],
)
def test_should_refuse_a_ruled_out_count_it_cannot_back(extra_arguments: list[str]) -> None:
    with pytest.raises(SystemExit):
        merge_review_receipt.main(["acme/tools", "12", HEAD, "3", *extra_arguments], StringIO())


@pytest.mark.parametrize(
    "all_arguments",
    [
        ["acme/tools", "12", HEAD, "-1"],
        ["acme/tools", "12", HEAD, "2", "--rulings", RULINGS_LINK],
    ],
)
def test_should_refuse_counts_and_links_it_cannot_record(
    all_arguments: list[str], receipt_folder: Path
) -> None:
    with pytest.raises(SystemExit):
        merge_review_receipt.main(all_arguments, StringIO())
    assert list(receipt_folder.iterdir()) == []


def test_should_report_reviewed_when_the_rulings_link_points_at_another_pull_request() -> None:
    verdict_stream = StringIO()
    other_link = "https://github.com/acme/tools/pull/13#issuecomment-1"
    exit_code = merge_review_receipt.main(
        ["acme/tools", "12", HEAD, "2", "--ruled-out", "2", "--rulings", other_link],
        verdict_stream,
    )
    assert exit_code == 1
    assert verdict_stream.getvalue() == f"REVIEWED acme/tools#12 {HEAD} 2 findings\n"


def test_should_record_a_clean_open_pass_under_heads(receipt_folder: Path) -> None:
    verdict_stream = StringIO()
    assert merge_review_receipt.main(["acme/tools", "open", HEAD, "0"], verdict_stream) == 0
    assert verdict_stream.getvalue() == f"CLEAN acme/tools open {HEAD}\n"
    receipt = json.loads((receipt_folder / "heads" / f"acme__tools__{HEAD}.json").read_text())
    assert receipt == {"head": HEAD, "findings": 0}


def test_record_open_review_writes_the_head_receipt_in_lowercase(receipt_folder: Path) -> None:
    path = merge_review_receipt.record_open_review("Acme/Tools", HEAD.upper(), 2)
    assert path == receipt_folder / "heads" / f"acme__tools__{HEAD}.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"head": HEAD.upper(), "findings": 2}


def test_should_exit_one_for_an_open_pass_with_findings() -> None:
    verdict_stream = StringIO()
    assert merge_review_receipt.main(["acme/tools", "open", HEAD, "2"], verdict_stream) == 1
    assert verdict_stream.getvalue() == f"REVIEWED acme/tools open {HEAD} 2 findings\n"


@pytest.mark.parametrize(
    "all_arguments",
    [
        ["acme/tools", "open", HEAD, "-1"],
        ["acme/tools", "open", HEAD, "2", "--ruled-out", "2", "--rulings", RULINGS_LINK],
        ["acme/tools", "twelve", HEAD, "0"],
    ],
)
def test_should_refuse_an_open_pass_it_cannot_record(
    all_arguments: list[str], receipt_folder: Path
) -> None:
    with pytest.raises(SystemExit):
        merge_review_receipt.main(all_arguments, StringIO())
    assert list(receipt_folder.iterdir()) == []


@pytest.mark.parametrize("head", ["abc", "abc1234", "../../escape", "zzzzzzz"])
def test_should_refuse_an_open_pass_whose_head_is_not_a_commit(head: str, receipt_folder: Path) -> None:
    with pytest.raises(SystemExit):
        merge_review_receipt.main(["acme/tools", "open", head, "0"], StringIO())
    assert list(receipt_folder.iterdir()) == []


@pytest.mark.parametrize("slug", ["owner-repo", "a/b/../c", "a/.."])
@pytest.mark.parametrize("number", ["open", "12"])
def test_should_refuse_a_slug_that_is_not_owner_and_name(
    slug: str, number: str, receipt_folder: Path
) -> None:
    with pytest.raises(SystemExit):
        merge_review_receipt.main([slug, number, HEAD, "0"], StringIO())
    assert list(receipt_folder.iterdir()) == []
