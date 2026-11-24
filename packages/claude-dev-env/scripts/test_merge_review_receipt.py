"""Tests for the merge review receipt recorder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from io import StringIO
from pathlib import Path

import pytest

import merge_review_receipt

HEAD = "abc1234def5678abc1234def5678abc1234def56"
RULINGS_LINK = "https://github.com/acme/tools/pull/12#issuecomment-1"
ISSUE_LINK = "https://github.com/acme/tools/issues/40"


ISSUE_API_PATH = "repos/acme/tools/issues/40"
GH_STUB_SCRIPT = """#!{python}
import json, os, sys
all_responses = json.loads(open(os.environ["GH_ISSUE_STUB"], encoding="utf-8").read())
api_path = sys.argv[-1]
if sys.argv[1:4] != ["api", "--hostname", "github.com"] or api_path not in all_responses:
    sys.stderr.write("gh: Not Found (HTTP 404)\\n")
    sys.exit(1)
sys.stdout.buffer.write(json.dumps(all_responses[api_path], ensure_ascii=False).encode("utf-8"))
"""


@pytest.fixture(autouse=True)
def receipt_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_RECEIPT_DIR", str(receipts))
    monkeypatch.chdir(tmp_path)
    return receipts


@pytest.fixture(autouse=True)
def gh_issues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Put a stub ``gh`` first on PATH that answers each API path from a JSON map.

    Issue 40 of acme/tools exists. A test changes the map and calls
    ``_serve_issues`` to write it again. A path the map lacks answers 404.
    """
    executable_folder = tmp_path / "bin"
    executable_folder.mkdir()
    stub_path = executable_folder / "gh"
    stub_path.write_text(GH_STUB_SCRIPT.format(python=sys.executable), encoding="utf-8")
    stub_path.chmod(0o755)
    (executable_folder / "gh.cmd").write_text(f'@"{sys.executable}" "%~dp0gh" %*\r\n')
    monkeypatch.setenv("PATH", str(executable_folder) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("GH_ISSUE_STUB", str(tmp_path / "gh_issues.json"))
    monkeypatch.delenv("CLAUDE_MERGE_REVIEW_RUNS_REPOSITORY", raising=False)
    all_responses: dict[str, object] = {ISSUE_API_PATH: {"html_url": ISSUE_LINK, "number": 40}}
    _serve_issues(all_responses)
    if sys.platform == "win32":
        monkeypatch.setattr(merge_review_receipt, "_github_answer", _answer_from_stub_map)
    return all_responses


def _answer_from_stub_map(
    api_path: str, deadline: float | None = None, stop_reading: threading.Event | None = None
) -> object:
    if (deadline is not None and time.monotonic() >= deadline) or (
        stop_reading is not None and stop_reading.is_set()
    ):
        return None
    return json.loads(Path(os.environ["GH_ISSUE_STUB"]).read_text(encoding="utf-8")).get(api_path)


def _serve_issues(all_responses: dict[str, object]) -> None:
    Path(os.environ["GH_ISSUE_STUB"]).write_text(json.dumps(all_responses), encoding="utf-8")


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
    assert json.loads(path.read_text(encoding="utf-8")) == {"head": HEAD, "findings": 0, "pass": 2}


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
        "pass": 1,
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


def test_should_leave_ruling_keys_out_of_an_open_pass_that_rules_nothing_out(
    receipt_folder: Path,
) -> None:
    merge_review_receipt.main(["acme/tools", "open", HEAD, "2"], StringIO())
    receipt = json.loads((receipt_folder / "heads" / f"acme__tools__{HEAD}.json").read_text())
    assert receipt == {"head": HEAD, "findings": 2}


def test_record_open_review_should_name_the_checkout_branch_in_the_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = _checkout_with_file(tmp_path, monkeypatch)
    path = merge_review_receipt.record_open_review("acme/tools", head, 2)
    assert json.loads(path.read_text(encoding="utf-8"))["branch"] == "feature"


def test_record_open_review_should_name_the_branch_when_only_its_upstream_also_holds_the_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = _checkout_with_file(tmp_path, monkeypatch)
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/feature", head], check=True
    )
    path = merge_review_receipt.record_open_review("acme/tools", head, 2)
    assert json.loads(path.read_text(encoding="utf-8"))["branch"] == "feature"


def test_record_open_review_should_name_no_branch_when_another_branch_holds_the_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = _checkout_with_file(tmp_path, monkeypatch)
    subprocess.run(["git", "checkout", "--quiet", "-b", "second"], check=True)
    path = merge_review_receipt.record_open_review("acme/tools", head, 2)
    assert "branch" not in json.loads(path.read_text(encoding="utf-8"))


def test_record_open_review_should_refuse_a_ruling_the_head_lacks(receipt_folder: Path) -> None:
    with pytest.raises(ValueError, match="no file and line at nowhere.py:3"):
        merge_review_receipt.record_open_review("acme/tools", HEAD, 1, ["nowhere.py:3"])
    assert not (receipt_folder / "heads").exists()


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


def _checkout_with_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    subprocess.run(
        ["git", "init", "--quiet", "--initial-branch", "feature", str(checkout)], check=True
    )
    (checkout / "a.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (checkout / "docs").mkdir()
    (checkout / "docs" / "notes.txt").write_text("note\n", encoding="utf-8")
    (checkout / "docs" / "my notes.txt").write_text("spaced\nname\n", encoding="utf-8")
    (checkout / "odd.txt").write_bytes(b"a\x0cb\x1cc\xc2\x85d\n")
    (checkout / "unterminated.txt").write_bytes(b"first\nlast")
    subprocess.run(
        ["git", "-C", str(checkout), "add", "a.py", "docs", "odd.txt", "unterminated.txt"],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "commit",
            "--quiet",
            "-m",
            "first",
        ],
        check=True,
    )
    completed = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    monkeypatch.chdir(checkout)
    return completed.stdout.strip()


def test_should_print_clean_for_an_open_pass_ruled_out_at_file_and_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, receipt_folder: Path
) -> None:
    head = _checkout_with_file(tmp_path, monkeypatch)
    verdict_stream = StringIO()
    exit_code = merge_review_receipt.main(
        ["acme/tools", "open", head, "2", "--ruled-out", "2", "--rulings", "a.py:1,a.py:3"],
        verdict_stream,
    )
    assert exit_code == 0
    assert verdict_stream.getvalue() == (
        f"CLEAN acme/tools open {head} (2 findings ruled out: a.py:1,a.py:3)\n"
    )
    receipt = json.loads((receipt_folder / "heads" / f"acme__tools__{head}.json").read_text())
    assert receipt == {
        "head": head,
        "findings": 2,
        "ruled_out": 2,
        "ruling_lines": ["a.py:1", "a.py:3"],
        "branch": "feature",
    }


def test_should_count_a_line_by_newline_only_and_keep_an_unterminated_last_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, receipt_folder: Path
) -> None:
    head = _checkout_with_file(tmp_path, monkeypatch)
    exit_code = merge_review_receipt.main(
        ["acme/tools", "open", head, "2", "--ruled-out", "2", "--rulings", "odd.txt:1,unterminated.txt:2"],
        StringIO(),
    )
    assert exit_code == 0


def test_should_report_reviewed_and_keep_the_rulings_when_some_open_findings_stay_unruled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, receipt_folder: Path
) -> None:
    head = _checkout_with_file(tmp_path, monkeypatch)
    verdict_stream = StringIO()
    exit_code = merge_review_receipt.main(
        ["acme/tools", "open", head, "3", "--ruled-out", "2", "--rulings", "a.py:1,a.py:2"],
        verdict_stream,
    )
    assert exit_code == 1
    assert verdict_stream.getvalue().startswith(f"REVIEWED acme/tools open {head} 3 findings (")
    receipt = json.loads((receipt_folder / "heads" / f"acme__tools__{head}.json").read_text())
    assert receipt == {
        "head": head,
        "findings": 3,
        "ruled_out": 2,
        "ruling_lines": ["a.py:1", "a.py:2"],
        "branch": "feature",
    }


def test_should_accept_an_open_pass_ruled_out_at_a_path_with_a_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, receipt_folder: Path
) -> None:
    head = _checkout_with_file(tmp_path, monkeypatch)
    exit_code = merge_review_receipt.main(
        ["acme/tools", "open", head, "2", "--ruled-out", "2", "--rulings", "docs/my notes.txt:2,a.py:3"],
        StringIO(),
    )
    assert exit_code == 0
    receipt = json.loads((receipt_folder / "heads" / f"acme__tools__{head}.json").read_text())
    assert receipt["ruling_lines"] == ["docs/my notes.txt:2", "a.py:3"]


@pytest.mark.parametrize(
    "rulings",
    [
        "a.py:1",
        "a.py:1,a.py:9",
        "a.py:1,missing.py:1",
        "a.py:1,docs:1",
        "a.py:1,a.py:0",
        "a.py:1,a.py:1",
        "a.py:1,./a.py:1",
        "a.py:1,docs/../a.py:1",
        "a.py:1,docs\\notes.txt:1",
        "a.py:1,odd.txt:2",
        "a.py:1,unterminated.txt:3",
        "see the thread,a.py:3",
    ],
)
def test_should_refuse_an_open_pass_whose_rulings_do_not_prove_each_finding(
    rulings: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, receipt_folder: Path
) -> None:
    head = _checkout_with_file(tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        merge_review_receipt.main(
            ["acme/tools", "open", head, "2", "--ruled-out", "2", "--rulings", rulings],
            StringIO(),
        )
    assert not (receipt_folder / "heads").exists()


def test_should_name_the_path_form_when_a_ruling_is_malformed_not_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    receipt_folder: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    head = _checkout_with_file(tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        merge_review_receipt.main(
            ["acme/tools", "open", head, "2", "--ruled-out", "2", "--rulings", "a.py:1,docs\\notes.txt:1"],
            StringIO(),
        )
    error_text = capsys.readouterr().err
    assert "docs\\notes.txt:1" in error_text
    assert "segment" in error_text
    assert "run this in the checkout" not in error_text


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


def _record_passes_with_findings(pass_count: int) -> None:
    for each_pass_number in range(1, pass_count + 1):
        merge_review_receipt.record_review("acme/tools", 12, format(each_pass_number, "040x"), 2)


def _stored_receipt(receipt_folder: Path) -> dict[str, object]:
    return json.loads((receipt_folder / "acme__tools__12.json").read_text(encoding="utf-8"))


def test_should_count_the_first_record_as_pass_one(receipt_folder: Path) -> None:
    merge_review_receipt.main(["acme/tools", "12", HEAD, "2"], StringIO())
    assert _stored_receipt(receipt_folder)["pass"] == 1


def test_should_count_each_new_head_as_the_next_pass(receipt_folder: Path) -> None:
    _record_passes_with_findings(3)
    merge_review_receipt.main(["acme/tools", "12", HEAD, "0"], StringIO())
    assert _stored_receipt(receipt_folder)["pass"] == 4


EARLIER_COMMITS = ["1" * 40, "2" * 40, "3" * 40]
COMMITS_API_PATH = "repos/acme/tools/pulls/12/commits?per_page=100&page=1"
SECOND_COMMITS_API_PATH = "repos/acme/tools/pulls/12/commits?per_page=100&page=2"
REVIEW_APP = {"login": "repo-rulefile-sync[bot]", "type": "Bot"}
FIRST_RUN_ID = 45052844890
REVIEW_WORKFLOW_PATH = ".github/workflows/efficient-review.yml@refs/heads/main"


def _run_page(run_id: int) -> str:
    return f"https://github.com/acme/reviews/actions/runs/{run_id}"


def _run_api_path(run_id: int) -> str:
    return f"repos/acme/reviews/actions/runs/{run_id}"


def _statuses_api_path(sha: str) -> str:
    return f"repos/acme/tools/commits/{sha}/statuses?per_page=100"


def _review_run(run_id: int, sha: str, number: int = 12) -> dict[str, object]:
    return {
        "id": run_id,
        "path": REVIEW_WORKFLOW_PATH,
        "status": "completed",
        "conclusion": "success",
        "display_title": f"Merge review acme/tools#{number} {sha} base main",
    }


def _serve_review_statuses(
    gh_issues: dict[str, object],
    all_creators: list[dict[str, str]] | None = None,
    run_changes_by_index: dict[int, dict[str, object]] | None = None,
    target_url_by_index: dict[int, str] | None = None,
) -> None:
    gh_issues[COMMITS_API_PATH] = [
        {"sha": each_sha} for each_sha in [*EARLIER_COMMITS, HEAD]
    ]
    all_creators = all_creators or [REVIEW_APP] * len(EARLIER_COMMITS)
    for each_index, (each_sha, each_creator) in enumerate(
        zip(EARLIER_COMMITS, all_creators)
    ):
        run_id = FIRST_RUN_ID + each_index
        target_url = (target_url_by_index or {}).get(each_index, _run_page(run_id))
        gh_issues[_statuses_api_path(each_sha)] = [
            {
                "context": "Merge review",
                "state": "failure",
                "creator": each_creator,
                "target_url": target_url,
            },
            {
                "context": "Merge review",
                "state": "success",
                "creator": each_creator,
                "target_url": target_url,
            },
        ]
        review_run = _review_run(run_id, each_sha)
        review_run.update((run_changes_by_index or {}).get(each_index, {}))
        gh_issues[_run_api_path(run_id)] = review_run
    _serve_issues(gh_issues)


def _filed_pass(receipt_folder: Path, head: str = HEAD) -> object:
    merge_review_receipt.record_review("acme/tools", 12, head, 2, filed=ISSUE_LINK)
    return _stored_receipt(receipt_folder)["pass"]


def test_should_count_earlier_failing_review_runs_when_no_receipt_is_kept(
    receipt_folder: Path, gh_issues: dict[str, object]
) -> None:
    _serve_review_statuses(gh_issues)
    verdict_stream = StringIO()

    exit_code = merge_review_receipt.main(
        ["acme/tools", "12", HEAD, "2", "--filed", ISSUE_LINK], verdict_stream
    )

    assert exit_code == 0
    assert verdict_stream.getvalue().startswith("FILED acme/tools#12")
    assert _stored_receipt(receipt_folder)["pass"] == 4


@pytest.mark.parametrize("other_login", ["github-actions[bot]", "other-app[bot]"])
def test_should_leave_another_bot_review_status_out_of_the_pass_count(
    other_login: str, receipt_folder: Path, gh_issues: dict[str, object]
) -> None:
    other_bot = {"login": other_login, "type": "Bot"}
    _serve_review_statuses(gh_issues, [REVIEW_APP, other_bot, other_bot])

    assert _filed_pass(receipt_folder) == 2


def test_should_leave_a_review_status_without_a_run_page_out_of_the_pass_count(
    receipt_folder: Path, gh_issues: dict[str, object]
) -> None:
    _serve_review_statuses(
        gh_issues, target_url_by_index={1: "https://example.com/x", 2: ""}
    )

    assert _filed_pass(receipt_folder) == 2


@pytest.mark.parametrize(
    "run_change",
    [
        {"display_title": f"Merge review acme/tools# {'2' * 40} base main"},
        {"display_title": f"Merge review acme/tools#13 {'2' * 40} base main"},
        {"display_title": f"Merge review acme/other#12 {'2' * 40} base main"},
        {"display_title": f"Merge review acme/tools#12 {'9' * 40} base main"},
        {"conclusion": "failure"},
        {"status": "in_progress"},
        {"path": ".github/workflows/other.yml@refs/heads/main"},
        {"id": 7},
    ],
)
def test_should_leave_a_run_that_is_not_this_reviews_out_of_the_pass_count(
    run_change: dict[str, object], receipt_folder: Path, gh_issues: dict[str, object]
) -> None:
    _serve_review_statuses(
        gh_issues, run_changes_by_index={1: run_change, 2: run_change}
    )

    assert _filed_pass(receipt_folder) == 2


def test_should_leave_review_statuses_after_the_recorded_head_out_of_the_pass_count(
    receipt_folder: Path, gh_issues: dict[str, object]
) -> None:
    _serve_review_statuses(gh_issues)

    assert _filed_pass(receipt_folder, EARLIER_COMMITS[1]) == 2


def test_should_read_the_next_page_of_pull_request_commits(
    receipt_folder: Path, gh_issues: dict[str, object]
) -> None:
    _serve_review_statuses(gh_issues)
    gh_issues[SECOND_COMMITS_API_PATH] = gh_issues[COMMITS_API_PATH]
    gh_issues[COMMITS_API_PATH] = [
        {"sha": f"{each_index:040d}"} for each_index in range(4, 104)
    ]
    _serve_issues(gh_issues)

    assert _filed_pass(receipt_folder) == 4


def test_should_count_nothing_when_a_later_page_of_commits_cannot_be_read(
    receipt_folder: Path, gh_issues: dict[str, object]
) -> None:
    _serve_review_statuses(gh_issues)
    gh_issues[COMMITS_API_PATH] = [
        {"sha": f"{each_index:040d}"} for each_index in range(4, 104)
    ]
    _serve_issues(gh_issues)

    assert _filed_pass(receipt_folder) == 1


def test_should_count_nothing_when_the_head_is_not_in_the_commit_list(
    receipt_folder: Path, gh_issues: dict[str, object]
) -> None:
    _serve_review_statuses(gh_issues)
    gh_issues[COMMITS_API_PATH] = [{"sha": each_sha} for each_sha in EARLIER_COMMITS]
    _serve_issues(gh_issues)

    assert _filed_pass(receipt_folder) == 1


def _serve_failing_reviews_below_newer_commits(
    gh_issues: dict[str, object], newer_commit_count: int
) -> None:
    _serve_review_statuses(gh_issues)
    all_newer_shas = [f"{each_index:040d}" for each_index in range(4, 4 + newer_commit_count)]
    gh_issues[COMMITS_API_PATH] = [
        {"sha": each_sha} for each_sha in [*EARLIER_COMMITS, *all_newer_shas, HEAD]
    ]
    _serve_issues(gh_issues)


def test_should_find_failing_reviews_below_a_long_series_of_fix_commits(
    receipt_folder: Path, gh_issues: dict[str, object]
) -> None:
    _serve_failing_reviews_below_newer_commits(gh_issues, 150)

    assert _filed_pass(receipt_folder) == 4


def test_should_reach_old_failing_reviews_within_the_deadline_by_reading_in_parallel(
    receipt_folder: Path, gh_issues: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve_failing_reviews_below_newer_commits(gh_issues, 150)
    all_answers = json.loads(Path(os.environ["GH_ISSUE_STUB"]).read_text(encoding="utf-8"))

    def slow_answer(
        api_path: str, deadline: float | None = None, stop_reading: threading.Event | None = None
    ) -> object:
        if deadline is not None and time.monotonic() >= deadline:
            return None
        if "/statuses" in api_path:
            time.sleep(0.05)
        return all_answers.get(api_path)

    monkeypatch.setattr(merge_review_receipt, "_github_answer", slow_answer)
    monkeypatch.setattr(merge_review_receipt, "STATUS_READ_WORKER_COUNT", 16)
    monkeypatch.setattr(merge_review_receipt, "GITHUB_COUNT_DEADLINE_SECONDS", 3)

    assert _filed_pass(receipt_folder) == 4


def test_should_keep_reading_while_one_read_stalls(
    receipt_folder: Path, gh_issues: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve_failing_reviews_below_newer_commits(gh_issues, 12)
    all_answers = json.loads(Path(os.environ["GH_ISSUE_STUB"]).read_text(encoding="utf-8"))
    held_sha = f"{15:040d}"
    all_status_reads: list[str] = []

    def stalling_answer(
        api_path: str, deadline: float | None = None, stop_reading: threading.Event | None = None
    ) -> object:
        if "/statuses" in api_path and api_path.split("/commits/")[1][:40] == held_sha:
            assert stop_reading is not None
            stop_reading.wait(60)
            return None
        if "/statuses" in api_path:
            all_status_reads.append(api_path)
        return all_answers.get(api_path)

    monkeypatch.setattr(merge_review_receipt, "_github_answer", stalling_answer)
    monkeypatch.setattr(merge_review_receipt, "STATUS_READ_WORKER_COUNT", 2)

    assert _filed_pass(receipt_folder) == 4
    assert len(all_status_reads) >= 14


def test_should_kill_a_gh_read_when_the_stop_signal_is_set() -> None:
    stop_reading = threading.Event()
    stalled_read = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.PIPE
    )
    threading.Timer(0.3, stop_reading.set).start()

    started_at = time.monotonic()
    with stalled_read:
        answer = merge_review_receipt._read_process_answer(stalled_read, 60, stop_reading)

    assert answer is None
    assert time.monotonic() - started_at < 10
    assert stalled_read.returncode is not None


def test_should_signal_stalled_reads_to_stop_once_three_failing_reviews_are_counted(
    receipt_folder: Path, gh_issues: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    stalled_sha = "4" * 40
    _serve_review_statuses(gh_issues)
    gh_issues[COMMITS_API_PATH] = [
        {"sha": each_sha} for each_sha in [stalled_sha, *EARLIER_COMMITS, HEAD]
    ]
    all_answers = {**gh_issues, _statuses_api_path(stalled_sha): []}

    def stalling_answer(
        api_path: str, deadline: float | None = None, stop_reading: threading.Event | None = None
    ) -> object:
        if stalled_sha in api_path and stop_reading is not None:
            stop_reading.wait(30)
            return None
        return all_answers.get(api_path)

    monkeypatch.setattr(merge_review_receipt, "_github_answer", stalling_answer)

    started_at = time.monotonic()
    pass_number = _filed_pass(receipt_folder)

    assert pass_number == 4
    assert time.monotonic() - started_at < 10


RUNS_REPOSITORY = "acme/reviews"
PULL_REQUEST_API_PATH = "repos/acme/tools/pulls/12"
RUNS_API_PATH = (
    "repos/acme/reviews/actions/workflows/efficient-review.yml/runs"
    "?per_page=100&page=1&created=%3E%3D2026-11-01"
)


def _serve_rebased_review_history(
    gh_issues: dict[str, object], titled_number: int = 12
) -> None:
    _serve_review_statuses(gh_issues)
    gh_issues[COMMITS_API_PATH] = [{"sha": "6" * 40}, {"sha": HEAD}]
    gh_issues[_statuses_api_path("6" * 40)] = []
    gh_issues[PULL_REQUEST_API_PATH] = {"created_at": "2026-11-01T10:00:00Z"}
    gh_issues[RUNS_API_PATH] = {
        "workflow_runs": [
            {"display_title": f"Merge review acme/tools#{titled_number} {each_sha} base main"}
            for each_sha in EARLIER_COMMITS
        ]
    }
    if titled_number != 12:
        for each_index, each_sha in enumerate(EARLIER_COMMITS):
            gh_issues[_run_api_path(FIRST_RUN_ID + each_index)] = _review_run(
                FIRST_RUN_ID + each_index, each_sha, titled_number
            )
    _serve_issues(gh_issues)


def test_should_count_reviews_a_rebase_dropped_when_the_runs_repository_is_set(
    receipt_folder: Path, gh_issues: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_RUNS_REPOSITORY", RUNS_REPOSITORY)
    _serve_rebased_review_history(gh_issues)

    assert _filed_pass(receipt_folder) == 4


def test_should_list_a_head_once_when_two_runs_carry_its_title(
    gh_issues: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_RUNS_REPOSITORY", RUNS_REPOSITORY)
    _serve_rebased_review_history(gh_issues)
    gh_issues[RUNS_API_PATH] = {
        "workflow_runs": [
            {"display_title": f"Merge review acme/tools#12 {each_sha} base main"}
            for each_sha in [*EARLIER_COMMITS, *EARLIER_COMMITS]
        ]
    }
    _serve_issues(gh_issues)

    all_heads = merge_review_receipt._reviewed_heads_by_run_title(
        "acme", "tools", 12, time.monotonic() + 30
    )

    assert all_heads == EARLIER_COMMITS


def test_should_count_nothing_from_run_titles_when_the_commit_list_cannot_be_read(
    receipt_folder: Path, gh_issues: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_RUNS_REPOSITORY", RUNS_REPOSITORY)
    _serve_rebased_review_history(gh_issues)
    del gh_issues[COMMITS_API_PATH]
    _serve_issues(gh_issues)

    merge_review_receipt.record_review("acme/tools", 12, HEAD, 2)

    assert _stored_receipt(receipt_folder)["pass"] == 1


def test_should_read_no_more_heads_than_the_read_limit_when_run_titles_add_heads(
    receipt_folder: Path, gh_issues: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_RUNS_REPOSITORY", RUNS_REPOSITORY)
    monkeypatch.setattr(merge_review_receipt, "EARLIER_COMMIT_READ_LIMIT", 2)
    _serve_rebased_review_history(gh_issues)

    assert _filed_pass(receipt_folder) == 2


def test_should_refuse_a_runs_repository_setting_with_a_dot_segment() -> None:
    all_malformed_settings = ["../x", "x/..", "./x", ".x/y"]

    assert [
        each_setting
        for each_setting in all_malformed_settings
        if merge_review_receipt.REVIEW_RUNS_REPOSITORY_PATTERN.fullmatch(each_setting)
    ] == []


def test_should_keep_the_commit_list_count_when_the_runs_repository_is_unset(
    receipt_folder: Path, gh_issues: dict[str, object]
) -> None:
    _serve_rebased_review_history(gh_issues)

    merge_review_receipt.record_review("acme/tools", 12, HEAD, 2)

    assert _stored_receipt(receipt_folder)["pass"] == 1


def test_should_leave_out_runs_titled_for_another_pull_request(
    receipt_folder: Path, gh_issues: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_RUNS_REPOSITORY", RUNS_REPOSITORY)
    _serve_rebased_review_history(gh_issues, titled_number=13)

    merge_review_receipt.record_review("acme/tools", 12, HEAD, 2)

    assert _stored_receipt(receipt_folder)["pass"] == 1


def test_should_ignore_a_malformed_runs_repository_setting(
    receipt_folder: Path, gh_issues: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_RUNS_REPOSITORY", "not a repository")
    _serve_rebased_review_history(gh_issues)

    merge_review_receipt.record_review("acme/tools", 12, HEAD, 2)

    assert _stored_receipt(receipt_folder)["pass"] == 1


def test_should_read_only_the_newest_earlier_commits(
    receipt_folder: Path, gh_issues: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve_failing_reviews_below_newer_commits(gh_issues, 10)
    monkeypatch.setattr(merge_review_receipt, "EARLIER_COMMIT_READ_LIMIT", 5)

    assert _filed_pass(receipt_folder) == 1


def test_should_not_read_github_for_a_later_record_without_filed(
    receipt_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_read_paths: list[str] = []
    monkeypatch.setattr(
        merge_review_receipt,
        "_github_answer",
        lambda api_path, deadline=None, stop_reading=None: all_read_paths.append(api_path),
    )
    (receipt_folder / "acme__tools__12.json").write_text(
        json.dumps({"head": "0" * 40, "findings": 2, "pass": 1}), encoding="utf-8"
    )

    merge_review_receipt.main(["acme/tools", "12", HEAD, "2"], StringIO())

    assert _stored_receipt(receipt_folder)["pass"] == 2
    assert all_read_paths == []


def test_should_recover_the_pass_count_on_the_first_record_without_filed(
    receipt_folder: Path, gh_issues: dict[str, object]
) -> None:
    _serve_review_statuses(gh_issues)
    verdict_stream = StringIO()

    exit_code = merge_review_receipt.main(["acme/tools", "12", HEAD, "2"], verdict_stream)

    assert exit_code == 1
    assert "pass 4" in verdict_stream.getvalue()
    assert "--filed <issue url>" in verdict_stream.getvalue()
    assert _stored_receipt(receipt_folder)["pass"] == 4


@pytest.mark.parametrize(
    ("previous_pass", "previous_head", "expected_pass"),
    [
        (1, "0" * 40, 4),
        (4, "0" * 40, 5),
        (4, HEAD, 4),
    ],
)
def test_should_take_the_higher_of_the_receipt_and_the_review_runs(
    previous_pass: int,
    previous_head: str,
    expected_pass: int,
    receipt_folder: Path,
    gh_issues: dict[str, object],
) -> None:
    _serve_review_statuses(gh_issues)
    (receipt_folder / "acme__tools__12.json").write_text(
        json.dumps({"head": previous_head, "findings": 2, "pass": previous_pass}),
        encoding="utf-8",
    )

    assert _filed_pass(receipt_folder) == expected_pass


def test_should_skip_the_github_read_once_the_receipt_is_past_the_full_pass_count(
    receipt_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_read_paths: list[str] = []
    monkeypatch.setattr(
        merge_review_receipt,
        "_github_answer",
        lambda api_path, deadline=None, stop_reading=None: all_read_paths.append(api_path),
    )
    (receipt_folder / "acme__tools__12.json").write_text(
        json.dumps({"head": "0" * 40, "findings": 2, "pass": 3}), encoding="utf-8"
    )

    assert _filed_pass(receipt_folder) == 4
    assert all_read_paths == []


def test_should_read_nothing_after_the_deadline(
    receipt_folder: Path, gh_issues: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve_review_statuses(gh_issues)
    monkeypatch.setattr(merge_review_receipt, "GITHUB_COUNT_DEADLINE_SECONDS", 0)

    assert _filed_pass(receipt_folder) == 1
def test_should_keep_the_pass_count_when_the_same_head_is_recorded_again(
    receipt_folder: Path,
) -> None:
    merge_review_receipt.main(["acme/tools", "12", HEAD, "2"], StringIO())
    merge_review_receipt.main(
        ["acme/tools", "12", HEAD[:7], "2", "--ruled-out", "2", "--rulings", RULINGS_LINK],
        StringIO(),
    )
    assert _stored_receipt(receipt_folder)["pass"] == 1


@pytest.mark.parametrize(
    ("previous_text", "expected_pass"),
    [
        ("not json", 1),
        ("[1, 2]", 1),
        ('{"head": "' + "0" * 40 + '", "findings": 2}', 2),
        ('{"head": "' + "0" * 40 + '", "findings": 2, "pass": "3"}', 2),
    ],
)
def test_should_read_a_previous_receipt_it_cannot_count_as_at_most_one_pass(
    previous_text: str, expected_pass: int, receipt_folder: Path
) -> None:
    (receipt_folder / "acme__tools__12.json").write_text(previous_text, encoding="utf-8")
    merge_review_receipt.main(["acme/tools", "12", HEAD, "2"], StringIO())
    assert _stored_receipt(receipt_folder)["pass"] == expected_pass


@pytest.mark.parametrize("earlier_pass_count", [0, 1, 2])
def test_should_refuse_filed_findings_before_three_full_passes(
    earlier_pass_count: int, receipt_folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _record_passes_with_findings(earlier_pass_count)
    all_files_before = {
        each_path: each_path.read_text(encoding="utf-8") for each_path in receipt_folder.iterdir()
    }
    with pytest.raises(SystemExit):
        merge_review_receipt.main(
            ["acme/tools", "12", HEAD, "2", "--filed", ISSUE_LINK], StringIO()
        )
    assert "3 full passes with fixes come first" in capsys.readouterr().err
    assert {
        each_path: each_path.read_text(encoding="utf-8") for each_path in receipt_folder.iterdir()
    } == all_files_before


def test_should_print_filed_and_exit_zero_for_filed_findings_on_pass_four(
    receipt_folder: Path,
) -> None:
    _record_passes_with_findings(3)
    verdict_stream = StringIO()
    exit_code = merge_review_receipt.main(
        ["acme/tools", "12", HEAD, "2", "--filed", ISSUE_LINK], verdict_stream
    )
    assert exit_code == 0
    assert verdict_stream.getvalue() == (
        f"FILED acme/tools#12 {HEAD} (2 findings filed: {ISSUE_LINK})\n"
    )
    assert _stored_receipt(receipt_folder) == {
        "head": HEAD,
        "findings": 2,
        "pass": 4,
        "filed": ISSUE_LINK,
    }


def test_should_file_only_the_findings_left_after_the_ruled_out_ones() -> None:
    _record_passes_with_findings(3)
    verdict_stream = StringIO()
    exit_code = merge_review_receipt.main(
        [
            "acme/tools",
            "12",
            HEAD,
            "3",
            "--ruled-out",
            "1",
            "--rulings",
            RULINGS_LINK,
            "--filed",
            ISSUE_LINK,
        ],
        verdict_stream,
    )
    assert exit_code == 0
    assert verdict_stream.getvalue() == (
        f"FILED acme/tools#12 {HEAD} (2 findings filed: {ISSUE_LINK})\n"
    )


def test_should_file_under_an_issue_whose_title_the_local_code_page_cannot_decode(
    gh_issues: dict[str, object],
) -> None:
    gh_issues[ISSUE_API_PATH] = {"html_url": ISSUE_LINK, "number": 40, "title": "Fix \u00c1 view"}
    _serve_issues(gh_issues)
    _record_passes_with_findings(3)
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(merge_review_receipt.__file__)),
            "acme/tools",
            "12",
            HEAD,
            "1",
            "--filed",
            ISSUE_LINK,
        ],
        env={**os.environ, "LC_ALL": "C", "PYTHONCOERCECLOCALE": "0", "PYTHONUTF8": "0"},
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0


def test_should_report_reviewed_when_a_filed_pass_links_rulings_on_another_pull_request() -> None:
    _record_passes_with_findings(3)
    verdict_stream = StringIO()
    exit_code = merge_review_receipt.main(
        [
            "acme/tools",
            "12",
            HEAD,
            "3",
            "--ruled-out",
            "1",
            "--rulings",
            "https://github.com/acme/tools/pull/99#issuecomment-1",
            "--filed",
            ISSUE_LINK,
        ],
        verdict_stream,
    )
    assert exit_code == 1
    verdict = verdict_stream.getvalue()
    assert verdict.startswith(f"REVIEWED acme/tools#12 {HEAD} 3 findings")
    assert "--rulings https://github.com/acme/tools/pull/99#issuecomment-1 is not an issue comment link" in verdict
    assert "--filed <issue url>" not in verdict


@pytest.mark.parametrize(
    "filed_link",
    [
        "https://github.com/acme/other/issues/40",
        "https://github.com/acme/tools/pull/40",
        "https://github.com/acme/tools/issues/40#issuecomment-1",
        "https://github.com/acme/tools/issues/12",
        "acme/tools#40",
    ],
)
def test_should_refuse_a_filed_link_that_is_not_an_issue_in_this_repository(
    filed_link: str, receipt_folder: Path
) -> None:
    _record_passes_with_findings(3)
    with pytest.raises(SystemExit):
        merge_review_receipt.main(
            ["acme/tools", "12", HEAD, "2", "--filed", filed_link], StringIO()
        )
    assert _stored_receipt(receipt_folder)["pass"] == 3


@pytest.mark.parametrize(
    "issue_answer",
    [
        None,
        {"html_url": "https://github.com/acme/tools/pull/40", "number": 40, "pull_request": {}},
        {"html_url": "https://github.com/acme/elsewhere/issues/7", "number": 7},
    ],
)
def test_should_refuse_a_filed_link_github_does_not_serve_as_that_issue(
    issue_answer: object,
    gh_issues: dict[str, object],
    receipt_folder: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _record_passes_with_findings(3)
    gh_issues.pop(ISSUE_API_PATH)
    if issue_answer is not None:
        gh_issues[ISSUE_API_PATH] = issue_answer
    _serve_issues(gh_issues)
    with pytest.raises(SystemExit):
        merge_review_receipt.main(
            ["acme/tools", "12", HEAD, "2", "--filed", ISSUE_LINK], StringIO()
        )
    assert "is not an issue GitHub serves in acme/tools" in capsys.readouterr().err
    assert _stored_receipt(receipt_folder)["pass"] == 3


@pytest.mark.parametrize(
    "counts",
    [["0"], ["2", "--ruled-out", "2", "--rulings", RULINGS_LINK]],
)
def test_should_refuse_filed_when_no_finding_is_left_to_file(
    counts: list[str], receipt_folder: Path
) -> None:
    _record_passes_with_findings(3)
    with pytest.raises(SystemExit):
        merge_review_receipt.main(
            ["acme/tools", "12", HEAD, *counts, "--filed", ISSUE_LINK], StringIO()
        )
    assert _stored_receipt(receipt_folder)["pass"] == 3


def test_should_refuse_filed_on_an_open_pass(
    receipt_folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        merge_review_receipt.main(
            ["acme/tools", "open", HEAD, "2", "--filed", ISSUE_LINK], StringIO()
        )
    assert "fix its findings in new commits and open the pull request" in capsys.readouterr().err
    assert list(receipt_folder.iterdir()) == []


def test_should_name_the_fix_commits_route_when_an_open_pass_reports_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = _checkout_with_file(tmp_path, monkeypatch)
    verdict_stream = StringIO()
    assert merge_review_receipt.main(["acme/tools", "open", head, "2"], verdict_stream) == 1
    assert verdict_stream.getvalue() == (
        f"REVIEWED acme/tools open {head} 2 findings (fix them in new commits on top of "
        f"{head}, then open the pull request; the fix commits need no second pass)\n"
    )


@pytest.mark.parametrize("place", ["outside any checkout", "detached HEAD"])
def test_should_say_to_record_again_from_the_branch_checkout_when_a_pass_with_findings_names_no_branch(
    place: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = _checkout_with_file(tmp_path, monkeypatch)
    if place == "detached HEAD":
        subprocess.run(["git", "checkout", "--quiet", "--detach", head], check=True)
    else:
        outside_folder = tmp_path / "outside"
        outside_folder.mkdir()
        monkeypatch.chdir(outside_folder)
    verdict_stream = StringIO()
    assert merge_review_receipt.main(["acme/tools", "open", head, "2"], verdict_stream) == 1
    verdict = verdict_stream.getvalue()
    assert verdict.startswith(f"REVIEWED acme/tools open {head} 2 findings, recorded with no branch")
    assert f"counts only at {head} itself" in verdict
    assert "Run this command again from the checkout of the branch you will open" in verdict
    assert "the fix commits need no second pass" not in verdict


def test_should_describe_only_a_same_branch_pass_as_covering_fix_commits_in_the_module_docstring() -> None:
    module_text = merge_review_receipt.__doc__ or ""
    assert "above the\nhead of any ``open`` pass" not in module_text
    assert "recorded on the same branch" in module_text


def test_should_name_the_filed_route_when_a_pass_after_the_third_reports_findings() -> None:
    _record_passes_with_findings(3)
    verdict_stream = StringIO()
    exit_code = merge_review_receipt.main(["acme/tools", "12", HEAD, "2"], verdict_stream)
    assert exit_code == 1
    verdict = verdict_stream.getvalue()
    assert verdict.startswith(f"REVIEWED acme/tools#12 {HEAD} 2 findings")
    assert "--filed" in verdict


def test_should_leave_the_filed_route_out_of_the_third_pass_verdict() -> None:
    _record_passes_with_findings(2)
    verdict_stream = StringIO()
    merge_review_receipt.main(["acme/tools", "12", HEAD, "2"], verdict_stream)
    assert verdict_stream.getvalue() == f"REVIEWED acme/tools#12 {HEAD} 2 findings\n"
