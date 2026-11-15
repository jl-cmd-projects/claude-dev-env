"""Behavior tests for the clean-review merge gate."""

import io
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
SCRIPTS_DIRECTORY = HOOKS_DIRECTORY.parent / "scripts"
for each_directory in (HOOKS_DIRECTORY, SCRIPTS_DIRECTORY):
    if str(each_directory) not in sys.path:
        sys.path.insert(0, str(each_directory))

import merge_review_receipt
from blocking import gate_run_reads
from blocking import merge_review_gate as gate
from blocking.gate_run_reads import read_deadlines_started
from blocking.merge_review_gate_parts import open_request
from hooks_constants.gate_run_reads_constants import READS_RAN_OUT_SENTENCE
from hooks_constants.merge_review_gate_constants import UNKNOWN_OPEN_TARGET_REASON

CLEAN_HEAD = "abc1234def5678abc1234def5678abc1234def56"
NEW_HEAD = "9999999aaaaaaa9999999aaaaaaa9999999aaaaa"
RULINGS_LINK = "https://github.com/acme/tools/pull/12#issuecomment-1"


@pytest.fixture(autouse=True)
def receipt_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_RECEIPT_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES", raising=False)
    monkeypatch.delenv("CLAUDE_MERGE_REVIEW_COMMAND", raising=False)
    remotes = tmp_path / "github.com"
    subprocess.run(
        ["git", "init", "--quiet", "--bare", str(remotes / "acme" / "tools.git")], check=True
    )
    index = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", str(index + 1))
    monkeypatch.setenv(f"GIT_CONFIG_KEY_{index}", f"url.{remotes}/.insteadOf")
    monkeypatch.setenv(f"GIT_CONFIG_VALUE_{index}", "https://github.com/")
    return tmp_path


@pytest.fixture
def github_repository(receipt_folder: Path) -> Path:
    return receipt_folder / "github.com" / "acme" / "tools.git"


def _merge_tool(head: str | None = None) -> dict[str, object]:
    tool_input: dict[str, object] = {"owner": "acme", "repo": "tools", "pullNumber": 12}
    if head is not None:
        tool_input["expectedHeadSha"] = head
    return {"tool_name": "mcp__github__merge_pull_request", "tool_input": tool_input}


def _bash(command: str) -> dict[str, object]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _reason(payload: dict[str, object]) -> str | None:
    decision = gate.decision_for(payload)
    if decision is None:
        return None
    return decision["hookSpecificOutput"]["permissionDecisionReason"]


def _deny_reason(payload: dict[str, object]) -> str:
    reason = _reason(payload)
    assert reason is not None, "the gate allowed the call"
    return reason


def test_should_deny_a_merge_with_no_review() -> None:
    assert "no clean review" in _deny_reason(_merge_tool(CLEAN_HEAD))


def test_should_deny_a_merge_whose_last_pass_found_findings() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 2)
    assert "no clean review" in _deny_reason(_merge_tool(CLEAN_HEAD))


def test_should_allow_a_merge_pinned_to_the_clean_head() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    assert _reason(_merge_tool(CLEAN_HEAD)) is None


def test_should_allow_a_merge_whose_findings_are_all_ruled_out_with_a_link() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 2, 2, RULINGS_LINK)
    assert _reason(_merge_tool(CLEAN_HEAD)) is None


def test_should_deny_a_merge_with_a_finding_left_open() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 3, 2, RULINGS_LINK)
    assert "no clean review" in _deny_reason(_merge_tool(CLEAN_HEAD))


@pytest.mark.parametrize(
    "receipt",
    [
        {"head": CLEAN_HEAD, "findings": 2, "ruled_out": 2},
        {"head": CLEAN_HEAD, "findings": 2, "ruled_out": 2, "rulings": "  "},
        {"head": CLEAN_HEAD, "findings": 2, "ruled_out": 2, "rulings": "x"},
        {
            "head": CLEAN_HEAD,
            "findings": 2,
            "ruled_out": 2,
            "rulings": "https://github.com/acme/other/pull/12#issuecomment-1",
        },
        {
            "head": CLEAN_HEAD,
            "findings": 2,
            "ruled_out": 2,
            "rulings": "https://github.com/acme/tools/pull/13#issuecomment-1",
        },
        {
            "head": CLEAN_HEAD,
            "findings": 2,
            "ruled_out": 2,
            "rulings": "https://evil.example/?https://github.com/acme/tools/pull/12#issuecomment-1",
        },
        {"head": CLEAN_HEAD, "findings": True},
        {"head": CLEAN_HEAD, "findings": "0"},
        {"head": CLEAN_HEAD, "findings": 1, "ruled_out": True, "rulings": RULINGS_LINK},
        {"head": CLEAN_HEAD, "findings": -1, "ruled_out": -1, "rulings": RULINGS_LINK},
    ],
)
def test_is_clean_receipt_should_reject_a_receipt_it_cannot_back(
    receipt: dict[str, object],
) -> None:
    assert gate.is_clean_receipt(receipt, "acme", "tools", 12) is False


def test_is_clean_receipt_should_accept_zero_findings() -> None:
    assert gate.is_clean_receipt({"head": CLEAN_HEAD, "findings": 0}, "acme", "tools", 12) is True


@pytest.mark.parametrize("rulings", ["x", "https://github.com/acme/tools/pull/13#issuecomment-1"])
def test_should_deny_a_merge_whose_rulings_link_is_not_a_comment_on_this_pull_request(
    rulings: str,
) -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 2, 2, rulings)
    assert "no clean review" in _deny_reason(_merge_tool(CLEAN_HEAD))


def test_should_name_the_ruled_out_route_in_the_deny_reason() -> None:
    assert "--ruled-out" in _deny_reason(_merge_tool(CLEAN_HEAD))


def test_should_deny_a_merge_pinned_to_a_head_pushed_after_the_review() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    assert "Review the new head" in _deny_reason(_merge_tool(NEW_HEAD))


def test_should_deny_an_unpinned_merge_after_a_clean_review() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    assert "names no head" in _deny_reason(_merge_tool())


def test_should_deny_auto_merge_that_names_no_head() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    payload = {
        "tool_name": "mcp__github__enable_pr_auto_merge",
        "tool_input": {"owner": "acme", "repo": "tools", "pullNumber": 12},
    }
    assert f"--match-head-commit {CLEAN_HEAD}" in _deny_reason(payload)


def test_should_allow_any_merge_in_an_exempt_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES", "other/x, ACME/Tools")
    assert _reason(_merge_tool()) is None


def test_should_read_a_gh_pr_merge_pinned_with_a_short_head() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    command = f"gh pr merge --squash 12 --repo acme/tools --match-head-commit {CLEAN_HEAD[:7]}"
    assert _reason(_bash(command)) is None


def test_should_deny_gh_pr_merge_auto() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    assert "Auto-merge" in _deny_reason(
        _bash("gh pr merge https://github.com/acme/tools/pull/12 --auto")
    )


def test_should_deny_gh_pr_merge_with_no_repository() -> None:
    assert "names no repository" in _deny_reason(_bash("gh pr merge 12 --squash"))


def test_should_read_a_gh_api_merge_with_a_sha_field() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    command = f"gh api -X PUT repos/acme/tools/pulls/12/merge -f sha={CLEAN_HEAD}"
    assert _reason(_bash(command)) is None


@pytest.mark.parametrize(
    "command",
    [
        "gh pr merge --disable-auto 7844",
        "gh pr merge 12 --repo acme/tools --disable-auto",
        "gh pr merge --disable-auto 12 --repo acme/tools; gh pr merge --disable-auto 13 --repo acme/tools",
        "gh pr merge 12 --repo acme/tools --body 'turn auto-merge off' --disable-auto",
        'gh pr merge 12 --repo acme/tools --disable-auto --body "Done (see notes); thanks"',
        'gh pr merge --disable-auto 12 --repo acme/tools --body "#12 done"',
        "gh pr merge --disable-auto 12 --repo acme/tools --body issue#12",
        'gh pr merge --body "" --disable-auto 12 --repo acme/tools',
    ],
)
def test_should_allow_a_merge_call_that_only_disables_auto_merge(command: str) -> None:
    assert gate.decision_for(_bash(command)) is None


@pytest.mark.parametrize(
    "command",
    [
        "gh pr merge --disable-auto 12 --repo acme/tools && gh pr merge 12 --repo acme/tools",
        "gh pr merge --disable-auto 12 --repo acme/tools\ngh pr merge 12 --repo acme/tools",
        "gh pr merge 12 --repo acme/tools && gh pr merge --disable-auto 12 --repo acme/tools",
        "gh pr merge 12 --repo acme/tools --body ' --disable-auto '",
        "gh pr merge --disable-auto 12 --repo acme/tools $(gh pr merge 12 --repo acme/tools)",
        "gh pr merge --disable-auto 12 --repo acme/tools `gh pr merge 12 --repo acme/tools`",
        "gh pr merge 12 --repo acme/tools --body x\\ --disable-auto",
        "gh pr merge 12 --repo acme/tools --body --disable-auto",
        "gh pr merge 12 --repo acme/tools --disable-auto --body 'unclosed",
        "gh pr merge 12 --repo acme/tools # --disable-auto",
        "gh pr merge --disable-auto 12 --repo acme/tools a#b; gh pr merge 12 --repo acme/tools",
        'gh pr merge --disable-auto 12 --repo acme/tools --body "$(gh pr merge 12 --repo acme/tools)"',
        'gh pr merge --disable-auto 12 --repo acme/tools && g""h pr merge --disable-auto 14 --repo acme/tools'
        " && echo x#y && gh pr merge 12 --repo acme/tools",
        "bash -c ' gh pr merge 12 --repo acme/tools --squash' sh --disable-auto",
        "gh pr merge 12 --repo acme/tools --auto --disable-auto",
        "gh pr merge 12 --repo acme/tools --disable-auto --auto=true",
        "gh pr merge 12 --repo acme/tools --disable-auto --disable-auto=false",
        "gh pr merge 12 --repo acme/tools -sb --disable-auto",
        "gh pr merge 12 --repo acme/tools -dt --disable-auto",
        "gh pr merge 12 --repo acme/tools -mF --disable-auto",
        "gh pr merge 12 --repo acme/tools -- --disable-auto",
    ],
)
def test_should_check_a_merge_chained_with_a_disable_auto_call(command: str) -> None:
    assert "no clean review" in _deny_reason(_bash(command))


def test_should_ignore_commands_that_merge_nothing() -> None:
    assert gate.decision_for(_bash("gh pr view 12 --repo acme/tools")) is None
    assert gate.decision_for(_bash("git merge origin/main")) is None


def test_should_name_the_configured_review_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_COMMAND", "/team-review")
    assert "`/team-review`" in _deny_reason(_merge_tool(CLEAN_HEAD))


def test_should_name_the_low_fix_pass_after_three_full_reviews_in_the_deny_reason() -> None:
    reason = _deny_reason(_merge_tool(CLEAN_HEAD))
    assert "three full passes" in reason
    assert "`/code-review low --fix 12`" in reason


def test_should_allow_auto_merge_pinned_to_the_clean_head() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    command = f"gh pr merge 12 --repo acme/tools --auto --match-head-commit {CLEAN_HEAD}"
    assert _reason(_bash(command)) is None


def test_should_deny_pinned_auto_merge_with_no_clean_review() -> None:
    command = f"gh pr merge 12 --repo acme/tools --auto --match-head-commit {CLEAN_HEAD}"
    assert "no clean review" in _deny_reason(_bash(command))


def test_should_deny_auto_merge_pinned_to_a_newer_head() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    command = f"gh pr merge 12 --repo acme/tools --auto --match-head-commit {NEW_HEAD}"
    assert "Review the new head" in _deny_reason(_bash(command))


def _git(folder: Path, *all_arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(folder), *all_arguments], capture_output=True, text=True, check=True
    )
    return completed.stdout.strip()


@pytest.fixture
def branch_checkout(tmp_path: Path, github_repository: Path) -> tuple[Path, str]:
    folder = tmp_path / "checkout"
    folder.mkdir()
    _git(folder, "init", "--quiet", "--initial-branch", "main")
    _git(folder, "remote", "add", "origin", "https://github.com/acme/tools.git")
    _git(folder, "checkout", "--quiet", "-b", "feature")
    _git(
        folder,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        "first",
    )
    _git(folder, "push", "--quiet", str(github_repository), "feature")
    return folder, _git(folder, "rev-parse", "HEAD")


@pytest.fixture
def ruled_checkout(
    branch_checkout: tuple[Path, str], github_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, str]:
    folder, _head = branch_checkout
    (folder / "a.py").write_text("one\n", encoding="utf-8")
    (folder / "b.py").write_text("one\ntwo\n", encoding="utf-8")
    _git(folder, "add", "a.py", "b.py")
    _git(
        folder,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "--quiet",
        "-m",
        "files",
    )
    _git(folder, "push", "--quiet", str(github_repository), "feature")
    monkeypatch.chdir(folder)
    return folder, _git(folder, "rev-parse", "HEAD")


def _record_open_pass(head: str, findings: int, ruled_out: int, rulings: str) -> None:
    merge_review_receipt.main(
        [
            "acme/tools",
            "open",
            head,
            str(findings),
            "--ruled-out",
            str(ruled_out),
            "--rulings",
            rulings,
        ],
        io.StringIO(),
    )


def _create_tool(folder: Path, head: str = "feature") -> dict[str, object]:
    return {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "acme", "repo": "tools", "head": head, "base": "main"},
        "cwd": str(folder),
    }


def _bash_in(folder: Path, command: str) -> dict[str, object]:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(folder)}


def test_should_deny_a_pull_request_open_with_no_review(branch_checkout: tuple[Path, str]) -> None:
    folder, head = branch_checkout
    reason = _deny_reason(_create_tool(folder))
    assert f"no clean review for head {head}" in reason
    assert f"acme/tools open {head} 0" in reason
    assert "--ruled-out" in reason
    assert "--rulings" in reason


def test_should_allow_a_pull_request_open_whose_findings_are_ruled_out_at_file_and_line(
    ruled_checkout: tuple[Path, str],
) -> None:
    folder, head = ruled_checkout
    _record_open_pass(head, 2, 2, "a.py:1,b.py:2")
    assert _reason(_create_tool(folder)) is None


def test_should_deny_a_pull_request_open_whose_rulings_leave_a_finding_unproven(
    ruled_checkout: tuple[Path, str],
) -> None:
    folder, head = ruled_checkout
    _record_open_pass(head, 3, 2, "a.py:1,b.py:2")
    assert "no clean review" in _deny_reason(_create_tool(folder))


def test_should_allow_a_pull_request_open_reviewed_clean_at_its_head(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    assert _reason(_create_tool(folder)) is None


def test_should_deny_a_pull_request_open_whose_pass_found_findings(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 2)
    assert "no clean review" in _deny_reason(_create_tool(folder))


def test_should_deny_a_pull_request_open_after_a_push_past_the_review(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, _head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", NEW_HEAD, 0)
    assert "no clean review" in _deny_reason(_create_tool(folder))


def test_should_read_gh_pr_create_with_repo_and_head(branch_checkout: tuple[Path, str]) -> None:
    folder, head = branch_checkout
    command = "gh pr create --repo acme/tools --head feature --title t --body b"
    assert "no clean review" in _deny_reason(_bash_in(folder, command))
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    assert _reason(_bash_in(folder, command)) is None


def test_should_read_gh_pr_create_repository_from_origin(branch_checkout: tuple[Path, str]) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    assert _reason(_bash_in(folder, "gh pr create --fill")) is None


def test_should_read_the_pull_request_script_create(branch_checkout: tuple[Path, str]) -> None:
    folder, head = branch_checkout
    command = "python scripts/pull_request.py create --repo acme/tools --head feature"
    assert f"head {head}" in _deny_reason(_bash_in(folder, command))


def test_should_deny_a_pull_request_open_whose_head_cannot_be_read(tmp_path: Path) -> None:
    reason = _deny_reason(_create_tool(tmp_path, head="missing-branch"))
    assert "names no repository or head commit" in reason


def test_should_read_the_pushed_head_of_a_branch_outside_any_checkout(
    branch_checkout: tuple[Path, str], tmp_path: Path
) -> None:
    _folder, head = branch_checkout
    outside = tmp_path / "outside"
    outside.mkdir()
    assert f"no clean review for head {head}" in _deny_reason(_create_tool(outside))
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    assert _reason(_create_tool(outside)) is None


def test_should_read_the_checkout_head_when_github_lists_no_such_repository(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/ghost", head, 0)
    unlisted_create = _create_tool(folder)
    unlisted_create["tool_input"]["repo"] = "ghost"
    assert _reason(unlisted_create) is None


def test_should_allow_a_pull_request_open_in_an_exempt_repository(
    branch_checkout: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _head = branch_checkout
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES", "acme/tools")
    assert _reason(_create_tool(folder)) is None


def test_should_allow_a_merge_pinned_to_the_head_reviewed_clean_before_open() -> None:
    merge_review_receipt.record_open_review("acme/tools", CLEAN_HEAD, 0)
    assert _reason(_merge_tool(CLEAN_HEAD)) is None
    command = f"gh pr merge 12 --repo acme/tools --match-head-commit {CLEAN_HEAD[:7]}"
    assert _reason(_bash(command)) is None


def test_should_deny_a_merge_pinned_to_a_head_whose_open_pass_only_ruled_findings_out(
    ruled_checkout: tuple[Path, str],
) -> None:
    _folder, head = ruled_checkout
    _record_open_pass(head, 2, 2, "a.py:1,b.py:2")
    assert "no clean review" in _deny_reason(_merge_tool(head))


def test_should_deny_a_merge_pinned_past_the_head_reviewed_before_open() -> None:
    merge_review_receipt.record_open_review("acme/tools", CLEAN_HEAD, 0)
    assert "no clean review" in _deny_reason(_merge_tool(NEW_HEAD))


def test_should_deny_an_unpinned_merge_with_only_an_open_review() -> None:
    merge_review_receipt.record_open_review("acme/tools", CLEAN_HEAD, 0)
    assert "no clean review" in _deny_reason(_merge_tool())


def test_should_not_accept_an_open_review_from_another_repository() -> None:
    merge_review_receipt.record_open_review("acme/other", CLEAN_HEAD, 0)
    assert "no clean review" in _deny_reason(_merge_tool(CLEAN_HEAD))


def test_should_accept_an_open_review_recorded_under_the_old_owner() -> None:
    merge_review_receipt.record_open_review("oldowner/tools", CLEAN_HEAD, 0)
    assert _reason(_merge_tool(CLEAN_HEAD)) is None


def test_should_deny_a_merge_whose_numbered_pass_found_findings_at_the_open_reviewed_head() -> None:
    merge_review_receipt.record_open_review("acme/tools", CLEAN_HEAD, 0)
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 2)
    assert "no clean review" in _deny_reason(_merge_tool(CLEAN_HEAD))


def test_should_ignore_an_open_receipt_whose_head_is_not_a_commit(receipt_folder: Path) -> None:
    heads_folder = receipt_folder / "heads"
    heads_folder.mkdir()
    (heads_folder / "acme__tools__a.json").write_text(
        '{"head": "a", "findings": 0}', encoding="utf-8"
    )
    assert "no clean review" in _deny_reason(_merge_tool(CLEAN_HEAD))


def test_should_check_a_merge_chained_after_a_reviewed_open(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    command = (
        "gh pr create --repo acme/tools --head feature --fill && "
        f"gh pr merge 12 --repo acme/tools --match-head-commit {NEW_HEAD}"
    )
    assert "no clean review" in _deny_reason(_bash_in(folder, command))


def test_should_read_the_pushed_branch_before_the_local_one(
    branch_checkout: tuple[Path, str], github_repository: Path
) -> None:
    folder, local_head = branch_checkout
    _git(
        folder,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        "pushed",
    )
    pushed_head = _git(folder, "rev-parse", "HEAD")
    _git(folder, "push", "--quiet", str(github_repository), "HEAD:feature")
    _git(folder, "reset", "--quiet", "--hard", local_head)
    merge_review_receipt.record_open_review("acme/tools", local_head, 0)
    assert f"head {pushed_head}" in _deny_reason(_create_tool(folder))


def test_should_read_the_fetched_branch_before_the_local_one_for_a_shell_open(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, local_head = branch_checkout
    _git(
        folder,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        "fetched",
    )
    fetched_head = _git(folder, "rev-parse", "HEAD")
    _git(folder, "update-ref", "refs/remotes/origin/feature", fetched_head)
    _git(folder, "reset", "--quiet", "--hard", local_head)
    merge_review_receipt.record_open_review("acme/tools", local_head, 0)
    command = "gh pr create --repo acme/tools --head feature"
    assert f"head {fetched_head}" in _deny_reason(_bash_in(folder, command))


def test_should_not_match_an_open_receipt_on_a_short_pinned_head() -> None:
    merge_review_receipt.record_open_review("acme/tools", CLEAN_HEAD, 0)
    assert "no clean review" in _deny_reason(_merge_tool(CLEAN_HEAD[:3]))


def test_should_allow_an_open_in_an_exempt_repository_with_an_unread_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES", "acme/tools")
    assert _reason(_create_tool(tmp_path, head="missing-branch")) is None


def test_should_skip_options_quoted_inside_the_title_or_body(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    command = (
        "gh pr create --repo acme/tools --title 'use -R other/x' "
        f"--body \"curl -H 'Accept: x'; -H {NEW_HEAD}\" --head feature"
    )
    assert _reason(_bash_in(folder, command)) is None


def test_should_read_the_head_in_the_folder_a_cd_moves_to(
    branch_checkout: tuple[Path, str], tmp_path: Path
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert _reason(_bash_in(elsewhere, f'cd "{folder}" && gh pr create --fill')) is None
    assert "names no repository or head commit" in _deny_reason(
        _bash_in(folder, f'cd "{elsewhere}" && gh pr create --repo acme/tools --fill')
    )


@pytest.fixture
def two_branch_checkout(branch_checkout: tuple[Path, str]) -> tuple[Path, str, str]:
    folder, first_head = branch_checkout
    _git(folder, "checkout", "--quiet", "-b", "second")
    _git(
        folder,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        "second",
    )
    return folder, first_head, _git(folder, "rev-parse", "HEAD")


def test_should_deny_the_second_chained_open_when_only_the_first_head_was_reviewed(
    two_branch_checkout: tuple[Path, str, str],
) -> None:
    folder, first_head, second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    command = (
        "gh pr create --repo acme/tools --head feature --fill && "
        "gh pr create --repo acme/tools --head second --fill"
    )
    assert f"no clean review for head {second_head}" in _deny_reason(_bash_in(folder, command))


def test_should_deny_a_script_create_chained_after_a_reviewed_gh_create(
    two_branch_checkout: tuple[Path, str, str],
) -> None:
    folder, first_head, second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    command = (
        "gh pr create --repo acme/tools --head feature --fill; "
        "python scripts/pull_request.py create --repo acme/tools --head second"
    )
    assert f"no clean review for head {second_head}" in _deny_reason(_bash_in(folder, command))


def test_should_deny_the_second_open_on_its_own_line_when_only_the_first_head_was_reviewed(
    two_branch_checkout: tuple[Path, str, str],
) -> None:
    folder, first_head, second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    command = (
        "gh pr create --repo acme/tools --head feature --fill\n"
        "gh pr create --repo acme/tools --head second --fill"
    )
    assert f"no clean review for head {second_head}" in _deny_reason(_bash_in(folder, command))


def test_should_read_the_origin_once_for_creates_in_one_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_started_commands: list[list[str]] = []

    def answer_origin_and_head(all_command_words: list[str], *_all_arguments: object) -> str:
        all_started_commands.append(all_command_words)
        if "get-url" in all_command_words:
            return "https://github.com/acme/tools.git\n"
        return CLEAN_HEAD + "\n"

    monkeypatch.setattr(open_request, "child_stdout", answer_origin_and_head)
    merge_review_receipt.record_open_review("acme/tools", CLEAN_HEAD, 0)
    command = "gh pr create --head one --fill && gh pr create --head two --fill"
    assert _reason(_bash_in(tmp_path, command)) is None
    all_origin_reads = [
        each_command for each_command in all_started_commands if "get-url" in each_command
    ]
    assert len(all_origin_reads) == 1
    assert len(all_started_commands) == 3


def test_should_name_the_first_unreviewed_open_in_command_order(
    two_branch_checkout: tuple[Path, str, str],
) -> None:
    folder, first_head, second_head = two_branch_checkout
    command = (
        "gh pr create --repo acme/tools --head second --fill && "
        "gh pr create --repo acme/tools --head feature --fill"
    )
    reason = _deny_reason(_bash_in(folder, command))
    assert f"no clean review for head {second_head}" in reason
    assert first_head not in reason


def test_should_allow_chained_opens_when_every_head_was_reviewed(
    two_branch_checkout: tuple[Path, str, str],
) -> None:
    folder, first_head, second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    merge_review_receipt.record_open_review("acme/tools", second_head, 0)
    command = (
        "gh pr create --repo acme/tools --head feature --fill && "
        "gh pr create --repo acme/tools --head second --fill"
    )
    assert _reason(_bash_in(folder, command)) is None


def _clock_past_the_read_deadline() -> Callable[[], float]:
    all_readings = iter([0.0])
    return lambda: next(all_readings, 1000.0)


def test_should_deny_a_reviewed_shell_open_whose_head_reads_ran_out_of_time(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    payload = _bash_in(folder, "gh pr create --repo acme/tools --head feature --fill")
    assert _reason(payload) is None
    with read_deadlines_started(clock=_clock_past_the_read_deadline()):
        assert "names no repository or head commit" in _deny_reason(payload)


def test_should_start_no_github_listing_once_the_read_deadline_passed(
    branch_checkout: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    all_started_commands: list[list[str]] = []
    start_before_patch = gate_run_reads.subprocess.Popen

    def record_and_start(
        all_arguments: list[str], **all_keyword_arguments: object
    ) -> subprocess.Popen[str]:
        all_started_commands.append(all_arguments)
        return start_before_patch(all_arguments, **all_keyword_arguments)

    monkeypatch.setattr(gate_run_reads.subprocess, "Popen", record_and_start)
    with read_deadlines_started(clock=_clock_past_the_read_deadline()):
        assert "names no repository or head commit" in _deny_reason(_create_tool(folder))
    assert all_started_commands == []


def test_should_say_a_second_run_may_pass_when_a_git_read_ran_out_of_time(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, _head = branch_checkout
    payload = _bash_in(folder, "gh pr create --repo acme/tools --head feature --fill")
    with read_deadlines_started(clock=_clock_past_the_read_deadline()):
        assert _reason(payload) == UNKNOWN_OPEN_TARGET_REASON + READS_RAN_OUT_SENTENCE


def test_should_say_a_second_run_may_pass_when_the_github_listing_was_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git_on_path(tmp_path, monkeypatch, "exit 1")
    with read_deadlines_started(clock=_clock_past_the_read_deadline()):
        reason = _reason(_create_tool(tmp_path))
    assert reason == UNKNOWN_OPEN_TARGET_REASON + READS_RAN_OUT_SENTENCE


def test_should_not_say_a_second_run_may_pass_when_no_read_ran_out_of_time(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, head = branch_checkout
    payload = _bash_in(folder, "gh pr create --repo acme/tools --head feature --fill")
    with read_deadlines_started(clock=lambda: 0.0):
        reason = _deny_reason(payload)
    assert f"no clean review for head {head}" in reason
    assert READS_RAN_OUT_SENTENCE not in reason


def _raise_check_fault(*_all_arguments: object) -> str | None:
    raise KeyError("head")


def test_should_deny_an_open_whose_check_raises(
    branch_checkout: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _head = branch_checkout
    monkeypatch.setattr(gate, "open_deny_reason", _raise_check_fault)
    reason = _deny_reason(_bash_in(folder, "gh pr create --repo acme/tools --head feature --fill"))
    assert "merge review gate hit a fault" in reason
    assert "KeyError" in reason


def test_should_deny_a_merge_whose_check_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "deny_reason", _raise_check_fault)
    reason = _deny_reason(_bash(f"gh pr merge 12 --repo acme/tools --match-head-commit {CLEAN_HEAD}"))
    assert "merge review gate hit a fault" in reason
    assert "KeyError" in reason


def test_should_leave_a_call_that_opens_and_merges_nothing_to_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gate, "open_deny_reason", _raise_check_fault)
    monkeypatch.setattr(gate, "deny_reason", _raise_check_fault)
    assert gate.decision_for(_bash("git status")) is None


@pytest.mark.parametrize(
    "command",
    [
        "gh pr new --head second --fill",
        "gh -R acme/tools pr create --head second",
        "gh --repo=acme/tools pr create --head second",
        "GH_REPO=acme/tools gh pr create --head second",
        'bash -c "gh pr create --head second"',
        "python3.11 pull_request.py create --head second",
        "python3 -u pull_request.py create --head second",
        "python -X dev pull_request.py create --head second",
        "py -3 pull_request.py create --head second",
        "uv run python pull_request.py create --head second",
        "uv run pull_request.py create --head second",
        "python3 ~/.agents/skills/pull-request/scripts/pull_request.py create --head second",
    ],
)
def test_should_deny_every_create_spelling_whose_head_has_no_review(
    two_branch_checkout: tuple[Path, str, str], command: str
) -> None:
    folder, first_head, second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    reviewed_command = command.replace("--head second", "--head feature")
    assert _reason(_bash_in(folder, reviewed_command)) is None
    assert f"no clean review for head {second_head}" in _deny_reason(_bash_in(folder, command))


def test_should_deny_a_create_whose_last_repository_flag_names_an_unreviewed_repository(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    assert _reason(_bash_in(folder, "gh -R o/r pr create --repo acme/tools --head feature")) is None
    assert "no clean review" in _deny_reason(
        _bash_in(folder, "gh -R o/r pr create -R acme/tools --repo=a/b --repo=a/b --head feature")
    )


@pytest.mark.parametrize(
    "command",
    [
        "export GH_REPO=a/b ; gh pr create --head feature",
        "export GH_REPO=acme/tools && gh pr create --head feature",
        "GH_REPO=a/b ; gh pr create --head feature",
        "export GH_REPO ; gh pr create --head feature",
        "declare -x GH_REPO=a/b ; gh pr create --head feature",
        "typeset -x GH_REPO=a/b ; gh pr create --head feature",
        "eval 'export GH_REPO=a/b' ; gh pr create --head feature",
        "bash -c 'export GH_REPO=a/b ; gh pr create --head feature'",
        "GH_REPO=a/b bash -c 'gh pr create --head feature'",
        "env GH_REPO=a/b sh -c 'gh pr create --head feature'",
        "gh pr create --head feature ; export GH_REPO=a/b",
        "export GH_REPO+=a/b ; gh pr create --head feature",
        "GH_REPO+=a/b ; gh pr create --head feature",
        "GH_REPO+=a/b gh pr create --head feature",
        "GH_REPO=acme/tools GH_REPO+=x gh pr create --head feature",
    ],
)
def test_should_deny_as_unread_a_create_with_no_repository_when_the_command_sets_gh_repo(
    branch_checkout: tuple[Path, str], command: str
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    reason = _deny_reason(_bash_in(folder, command))
    assert "names no repository or head commit" in reason
    assert "--repo owner/name" in reason


@pytest.mark.parametrize(
    "command",
    [
        "export GH_REPO=a/b ; gh pr create --repo acme/tools --head feature",
        "export GH_REPO=a/b ; gh pr create -R acme/tools --head feature",
        "export GH_REPO=a/b ; GH_REPO=acme/tools gh pr create --head feature",
        "GH_REPO=acme/tools gh pr create --head feature ; gh pr create --head feature",
        "echo GH_REPO=a/b ; gh pr create --head feature",
        "gh pr create --head feature --body 'export GH_REPO=a/b'",
        "GH_REPO+=a/b gh pr create --repo acme/tools --head feature",
        "GH_REPO=a/b GH_REPO=acme/tools gh pr create --head feature",
        "echo GH_REPO+=a/b ; gh pr create --head feature",
    ],
)
def test_should_read_a_create_that_names_its_own_repository_when_the_command_sets_gh_repo(
    branch_checkout: tuple[Path, str], command: str
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    assert _reason(_bash_in(folder, command)) is None


def test_should_deny_as_unread_a_create_past_the_unwrap_depth(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    assert _reason(_bash_in(folder, "eval " * 18 + "'echo hi'")) is None
    command = "eval " * 18 + "'gh pr create --head feature'"
    assert "names no repository or head commit" in _deny_reason(_bash_in(folder, command))


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create --title --repo=x/y --head feature",
        "gh pr create --head feature --title --repo x/y",
        "gh pr create --head feature --title -Hsecond",
        "gh pr create --head feature --body -H --title second",
        "gh pr create --head feature -bHsecond",
        "gh pr create --head feature -tH second",
    ],
)
def test_should_read_a_flag_word_that_is_the_value_of_another_option_as_that_value(
    two_branch_checkout: tuple[Path, str, str], command: str
) -> None:
    folder, first_head, _second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    assert _reason(_bash_in(folder, command)) is None


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create --head feature --body '$(gh pr create --head second)'",
        "gh pr create --head feature --title '`gh pr create --head second`'",
        "gh pr create --head feature ; echo '$(gh pr create --head second)'",
        "gh pr create --head feature ; echo \\$(gh pr create --head second)",
        "gh pr create --head feature ; echo \\`gh pr create --head second\\`",
    ],
)
def test_should_read_no_create_in_a_substitution_bash_does_not_run(
    two_branch_checkout: tuple[Path, str, str], command: str
) -> None:
    folder, first_head, _second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    assert _reason(_bash_in(folder, command)) is None


@pytest.mark.parametrize(
    "command",
    [
        'gh pr create --head feature --body "$(gh pr create --head second)"',
        'gh pr create --head feature --body "$(gh pr create --title \\"x\\" --head second)"',
        "gh pr create --head feature ; echo $(gh pr create --head second)",
    ],
)
def test_should_deny_a_create_in_a_substitution_bash_runs_on_an_unreviewed_head(
    two_branch_checkout: tuple[Path, str, str], command: str
) -> None:
    folder, first_head, second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    assert f"no clean review for head {second_head}" in _deny_reason(_bash_in(folder, command))


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create --head feature ; case x in x) gh pr create --head second ;; esac",
        "gh pr create --head feature ; case x in x) gh -R acme/tools pr create --head second ;; esac",
        "case x in x) gh pr create --head feature ;; y) gh pr create --head second ;; esac",
    ],
)
def test_should_deny_a_create_in_a_case_arm_on_an_unreviewed_head(
    two_branch_checkout: tuple[Path, str, str], command: str
) -> None:
    folder, first_head, second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    assert f"no clean review for head {second_head}" in _deny_reason(_bash_in(folder, command))


def test_should_deny_a_create_whose_short_flag_cluster_names_an_unreviewed_head(
    two_branch_checkout: tuple[Path, str, str],
) -> None:
    folder, first_head, second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", second_head, 0)
    assert _reason(_bash_in(folder, "gh pr create --repo acme/tools -dHsecond")) is None
    assert f"no clean review for head {first_head}" in _deny_reason(
        _bash_in(folder, "gh pr create --repo acme/tools -dHfeature")
    )
    assert f"no clean review for head {first_head}" in _deny_reason(
        _bash_in(folder, "gh pr create --repo acme/tools -dHfeature --head second")
    )
    assert f"no clean review for head {first_head}" in _deny_reason(
        _bash_in(folder, "gh pr create --repo acme/tools --head second -dH feature")
    )


@pytest.fixture
def reviewed_sibling(two_branch_checkout: tuple[Path, str, str]) -> tuple[Path, str]:
    folder, first_head, second_head = two_branch_checkout
    _git(folder, "worktree", "add", "--quiet", str(folder.parent / "sibling"), "feature")
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    return folder, second_head


@pytest.mark.parametrize(
    "command",
    [
        "(cd ../sibling && gh pr create --fill) ; gh pr create --fill",
        "pushd ../sibling && gh pr create --fill && popd && gh pr create --fill",
    ],
)
def test_should_read_the_create_after_a_subshell_or_popd_in_the_starting_folder(
    reviewed_sibling: tuple[Path, str], command: str
) -> None:
    folder, second_head = reviewed_sibling
    assert _reason(_bash_in(folder, "cd ../sibling && gh pr create --fill")) is None
    assert f"no clean review for head {second_head}" in _deny_reason(_bash_in(folder, command))


def test_should_deny_a_create_after_a_folder_change_it_cannot_follow(
    reviewed_sibling: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _second_head = reviewed_sibling
    monkeypatch.chdir(folder)
    assert _reason(_bash_in(folder, "gh pr create --repo acme/tools --head feature --fill")) is None
    command = 'cd "$SIBLING" && gh pr create --repo acme/tools --head feature --fill'
    assert _reason(_bash_in(folder, command)) == UNKNOWN_OPEN_TARGET_REASON


def test_should_read_no_create_in_a_heredoc_body(
    two_branch_checkout: tuple[Path, str, str],
) -> None:
    folder, first_head, _second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    command = "gh pr create --head feature --body-file - <<'EOF'\ngh pr create --head second\nEOF"
    assert _reason(_bash_in(folder, command)) is None


def test_should_read_the_repository_of_a_create_whose_label_quotes_a_create(
    two_branch_checkout: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _first_head, second_head = two_branch_checkout
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES", "acme/tools")
    assert _reason(_bash_in(folder, "gh pr create --head second")) is None
    command = 'gh pr create --head second --label "see gh pr create" --repo acme/other'
    assert f"no clean review for head {second_head}" in _deny_reason(_bash_in(folder, command))


def test_should_read_the_repository_gh_repo_names(
    two_branch_checkout: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _first_head, second_head = two_branch_checkout
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES", "acme/tools")
    command = "GH_REPO=acme/other gh pr create --head second"
    assert f"no clean review for head {second_head}" in _deny_reason(_bash_in(folder, command))


@pytest.mark.parametrize(
    "command",
    [
        "GH_REPO=acme/other gh pr create --head feature",
        "GH_REPO=acme/other env -u GH_REPO gh pr create --head feature",
        "GH_REPO=acme/other env -i gh pr create --head feature",
    ],
)
def test_should_ask_for_an_origin_review_of_a_first_create_behind_a_gh_repo_prefix(
    branch_checkout: tuple[Path, str], command: str
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.main(["acme/other", "open", head, "0"], io.StringIO())
    assert f"acme/tools has no clean review for head {head}" in _deny_reason(
        _bash_in(folder, command)
    )


ALL_LATER_PREFIXED_CREATES = [
    'gh pr create --head feature --label "see gh pr create" --repo acme/other ; '
    "GH_REPO=acme/other env -u GH_REPO gh pr create --head feature",
    *(
        f"gh pr create --head feature --repo acme/other {separator} "
        f"GH_REPO=acme/other {wrapper} gh pr create --head feature"
        for separator in (";", "&&")
        for wrapper in (
            "env -u GH_REPO",
            "env -i",
            "sudo",
            "env --unset=GH_REPO",
            "env -uGH_REPO",
            "env -",
            "env --ignore-environment",
            "sudo --preserve-env",
        )
    ),
    "echo 'gh pr create --head feature --label \"see gh pr create\" --repo acme/other' ; "
    "GH_REPO=acme/other env -u GH_REPO gh pr create --head feature",
    "gh pr create --head feature --repo acme/other ; GH_REPO=acme/other gh pr create --head feature",
    "gh pr create --head feature --repo acme/other ; env GH_REPO=acme/other gh pr create --head feature",
    "gh pr create --head feature --repo acme/other ; "
    "env -u GH_REPO GH_REPO=acme/other gh pr create --head feature",
    "gh pr create --head feature --repo acme/other ; "
    "GH_REPO=acme/other env -u GH_REPO python3 pull_request.py create --head feature",
]


@pytest.mark.parametrize("command", ALL_LATER_PREFIXED_CREATES)
def test_should_ask_for_an_origin_review_of_any_create_behind_a_gh_repo_prefix_with_the_prefix_repository_exempt(
    branch_checkout: tuple[Path, str], monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    folder, head = branch_checkout
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES", "acme/other")
    assert f"acme/tools has no clean review for head {head}" in _deny_reason(
        _bash_in(folder, command)
    )


@pytest.mark.parametrize("command", ALL_LATER_PREFIXED_CREATES)
def test_should_ask_for_an_origin_review_of_any_create_behind_a_gh_repo_prefix_with_the_prefix_repository_reviewed(
    branch_checkout: tuple[Path, str], command: str
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.main(["acme/other", "open", head, "0"], io.StringIO())
    assert f"acme/tools has no clean review for head {head}" in _deny_reason(
        _bash_in(folder, command)
    )


ALL_ORIGIN_CREATES_BESIDE_AN_OTHER_REPOSITORY = [
    "GH_REPO=acme/other sudo gh pr create --head feature",
    "gh pr create --head feature --repo acme/other ; gh pr create --head feature --repo acme/tools",
    "gh pr create --head feature --repo acme/other && gh pr create --head feature",
    "gh pr create --head feature --repo acme/other ; gh pr create --head feature",
]


@pytest.mark.parametrize("command", ALL_ORIGIN_CREATES_BESIDE_AN_OTHER_REPOSITORY)
def test_should_ask_for_an_origin_review_beside_an_exempt_other_repository(
    branch_checkout: tuple[Path, str], monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    folder, head = branch_checkout
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES", "acme/other")
    assert f"acme/tools has no clean review for head {head}" in _deny_reason(
        _bash_in(folder, command)
    )


@pytest.mark.parametrize("command", ALL_ORIGIN_CREATES_BESIDE_AN_OTHER_REPOSITORY)
def test_should_ask_for_an_origin_review_beside_a_reviewed_other_repository(
    branch_checkout: tuple[Path, str], command: str
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.main(["acme/other", "open", head, "0"], io.StringIO())
    assert f"acme/tools has no clean review for head {head}" in _deny_reason(
        _bash_in(folder, command)
    )


def test_should_tell_a_create_behind_a_gh_repo_prefix_to_name_its_repository_with_the_repo_flag(
    branch_checkout: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _head = branch_checkout
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES", "acme/other")
    reason = _deny_reason(
        _bash_in(folder, "GH_REPO=acme/other env -u GH_REPO gh pr create --head feature")
    )
    assert "GH_REPO=" in reason
    assert "--repo owner/name" in reason


def test_should_allow_a_create_that_names_an_exempt_repository_with_its_own_repo_flag(
    branch_checkout: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _head = branch_checkout
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES", "acme/other")
    assert _reason(_bash_in(folder, "gh pr create --head feature --repo acme/other")) is None


def _git_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script_body: str) -> None:
    bin_folder = tmp_path / "fake-bin"
    bin_folder.mkdir()
    fake_git = bin_folder / "git"
    fake_git.write_text("#!/bin/sh\n" + script_body + "\n", encoding="utf-8")
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_folder}{os.pathsep}{os.environ['PATH']}")


def test_should_say_a_second_run_may_pass_when_a_git_read_hits_its_own_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git_on_path(tmp_path, monkeypatch, "exec sleep 30")
    monkeypatch.setattr(open_request, "GIT_TIMEOUT_SECONDS", 0.3)
    payload = _bash_in(tmp_path, "gh pr create --repo acme/tools --head feature --fill")
    assert _reason(payload) == UNKNOWN_OPEN_TARGET_REASON + READS_RAN_OUT_SENTENCE


def test_should_not_say_a_second_run_may_pass_when_git_fails_fast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git_on_path(tmp_path, monkeypatch, "exit 1")
    monkeypatch.setattr(open_request, "GIT_TIMEOUT_SECONDS", 0.3)
    payload = _bash_in(tmp_path, "gh pr create --repo acme/tools --head feature --fill")
    assert _reason(payload) == UNKNOWN_OPEN_TARGET_REASON


def test_should_say_a_second_run_may_pass_when_the_tool_head_lookup_hits_its_own_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git_on_path(tmp_path, monkeypatch, 'if [ "$1" = ls-remote ]; then exec sleep 30; fi\nexit 1')
    monkeypatch.setattr(open_request, "REMOTE_LOOKUP_TIMEOUT_SECONDS", 0.3)
    reason = _reason(_create_tool(tmp_path))
    assert reason is not None
    assert reason.endswith(READS_RAN_OUT_SENTENCE)


def _is_running(process_id: int) -> bool:
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    status_file = Path(f"/proc/{process_id}/stat")
    if not status_file.exists():
        return True
    return status_file.read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0] != "Z"


def test_should_leave_no_process_behind_when_the_tool_head_lookup_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process_id_file = tmp_path / "grandchild.pid"
    _git_on_path(
        tmp_path,
        monkeypatch,
        'if [ "$1" = ls-remote ]; then\n'
        f"  sleep 30 </dev/null >/dev/null 2>&1 & echo $! > {process_id_file}\n"
        "  exec sleep 30\nfi\nexit 1",
    )
    monkeypatch.setattr(open_request, "REMOTE_LOOKUP_TIMEOUT_SECONDS", 0.5)
    reason = _reason(_create_tool(tmp_path))
    assert reason is not None
    assert reason.endswith(READS_RAN_OUT_SENTENCE)
    assert not _is_running(int(process_id_file.read_text(encoding="utf-8")))


def test_should_not_say_a_second_run_may_pass_when_the_tool_head_lookup_fails_fast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git_on_path(tmp_path, monkeypatch, "exit 1")
    monkeypatch.setattr(open_request, "REMOTE_LOOKUP_TIMEOUT_SECONDS", 0.3)
    reason = _reason(_create_tool(tmp_path))
    assert reason is not None
    assert READS_RAN_OUT_SENTENCE not in reason


@pytest.mark.parametrize(
    "command",
    [
        "cat <<'BODY' | bash\ngh pr create --head second\nBODY",
        "cat > x.sh <<'BODY'\ngh pr create --head second\nBODY\nbash x.sh",
        ". /dev/stdin <<'BODY'\ngh pr create --head second\nBODY",
        "eval \"$(cat <<'BODY'\ngh pr create --head second\nBODY\n)\"",
        "echo gh pr create --head second | bash; x=`gh pr create --head feature`",
        "echo gh pr create --head second | bash; bash -c 'gh pr create --head feature'",
        "echo gh pr create --head second | bash; eval 'gh pr create --head feature'",
    ],
)
def test_should_deny_an_unreviewed_first_create_a_shell_reads_from_its_input(
    two_branch_checkout: tuple[Path, str, str], command: str
) -> None:
    folder, first_head, second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    assert _reason(_bash_in(folder, "gh pr create --head feature")) is None
    assert f"no clean review for head {second_head}" in _deny_reason(_bash_in(folder, command))


def test_should_not_read_a_create_in_the_sibling_a_piped_brace_group_moves_to(
    reviewed_sibling: tuple[Path, str],
) -> None:
    folder, _second_head = reviewed_sibling
    assert _reason(_bash_in(folder, "cd ../sibling; gh pr create --fill")) is None
    assert _reason(_bash_in(folder, "{ cd ../sibling; } | true; gh pr create --fill")) is not None


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create -Hsecond",
        "gh pr create --head feature --head second",
        "gh pr create --head=feature -H second",
    ],
)
def test_should_deny_a_create_when_any_head_it_names_is_unreviewed(
    two_branch_checkout: tuple[Path, str, str], command: str
) -> None:
    folder, first_head, second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    assert f"no clean review for head {second_head}" in _deny_reason(_bash_in(folder, command))


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create --head feature",
        "gh pr create --head feature && gh pr create --head=feature --fill",
    ],
)
def test_should_open_reviewed_single_and_chained_creates(
    two_branch_checkout: tuple[Path, str, str], command: str
) -> None:
    folder, first_head, _second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    assert _reason(_bash_in(folder, command)) is None
    assert _reason(_create_tool(folder)) is None


def test_should_deny_a_tool_merge_whose_number_overflows() -> None:
    payload = _merge_tool(CLEAN_HEAD)
    payload["tool_input"]["pullNumber"] = float("1e999")
    assert "OverflowError" in _deny_reason(payload)


def _raise_value_error(_all_payload_fields: dict[str, object]) -> None:
    raise ValueError("parse broke")


@pytest.mark.parametrize(
    "payload",
    [
        _bash("gh pr create --fill"),
        _bash("python3 scripts/pull_request.py create"),
        _bash("gh pr merge 12"),
        _bash("gh api -X PUT repos/acme/tools/pulls/12/merge"),
        _bash("gh pr new --fill"),
        _bash("gh -R o/r pr create --fill"),
        _bash("gh --repo o/r pr merge 5"),
        _bash("cd sub && gh.exe pr create --fill"),
        _bash("env GH_REPO=o/r gh pr merge 5"),
        _bash("python3 scripts/pull_request.py  create --fill"),
        {"tool_name": "mcp__github__create_pull_request", "tool_input": {}},
        {"tool_name": "mcp__github__enable_pr_auto_merge", "tool_input": {}},
    ],
)
def test_should_deny_an_open_or_merge_whose_payload_read_raises(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    monkeypatch.setattr(gate, "open_calls_from", _raise_value_error)
    all_escaped_errors: list[ValueError] = []
    try:
        reason = _reason(payload)
    except ValueError as error:
        all_escaped_errors.append(error)
        reason = None
    assert all_escaped_errors == []
    assert reason is not None and "ValueError" in reason


@pytest.mark.parametrize("command", ["git status", "ls -la", "git log --oneline", "echo new"])
def test_should_pass_a_payload_read_fault_on_other_commands_to_the_shared_helper(
    monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    monkeypatch.setattr(gate, "open_calls_from", _raise_value_error)
    with pytest.raises(ValueError):
        gate.decision_for(_bash(command))


ALL_ESCAPED_QUOTE_VALUES = [
    'gh pr create --head feature --body "say \\"x\\" ; gh pr create --head second"',
    'gh pr create --head feature --label "say \\"x\\" gh pr create --head second"',
    'gh pr create --head feature --body "see \\"x\\" --head second"',
    "gh pr create --head feature --body 'say \\\"x\\\" ; gh pr create --head second'",
]


@pytest.mark.parametrize("command", ALL_ESCAPED_QUOTE_VALUES)
def test_should_read_no_create_or_head_inside_a_quoted_value_with_an_escaped_quote(
    two_branch_checkout: tuple[Path, str, str], command: str
) -> None:
    folder, first_head, _second_head = two_branch_checkout
    assert f"no clean review for head {first_head}" in _deny_reason(_bash_in(folder, command))
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    assert _reason(_bash_in(folder, command)) is None


def test_should_read_a_create_after_a_value_an_escaped_quote_does_not_close(
    two_branch_checkout: tuple[Path, str, str],
) -> None:
    folder, first_head, second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    command = 'gh pr create --head feature --body "a \\" b" ; gh pr create --head second'
    assert f"no clean review for head {second_head}" in _deny_reason(_bash_in(folder, command))


def test_should_check_the_checkout_head_too_when_a_create_joins_its_head_to_dash_h(
    two_branch_checkout: tuple[Path, str, str],
) -> None:
    folder, first_head, second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    assert _reason(_bash_in(folder, "gh pr create --head feature")) is None
    assert f"no clean review for head {second_head}" in _deny_reason(
        _bash_in(folder, "gh pr create -Hfeature")
    )


ALL_LATER_CREATES_BASH_RUNS = [
    "gh pr create --head feature --body $'it\\'s' ; gh pr create --head second",
    "gh pr create --head feature --body $'it\\'s' && gh pr create --head second",
    "gh pr create --head feature --body $'it\\'s' | gh pr create --head second",
    "gh pr create --head feature --body $'it\\'s' & gh pr create --head second",
    "gh pr create --head feature --body $'\\'' ; gh pr create --head second",
    'gh pr create --head feature && bash -c "true\ngh pr create --head second"',
    "gh pr create --head feature && sh -c 'true\ngh pr create --head second'",
    'gh pr create --head feature && eval "true\ngh pr create --head second"',
    "gh pr create --head feature ; eval 'ls\nenv gh pr create -Hsecond --repo acme/tools'",
    'gh pr create --head feature ; bash -c "if true; then X=1\n\n'
    'gh pr create --head feature --head second; fi"',
    "gh pr create --head feature --body \"$(echo '\"')\" ; gh pr create --head second",
    "gh pr create --head feature ; bash -c -- 'gh pr create --head second'",
    "gh pr create --head feature ; eval 'gh pr create --head second --body \"a b\"'",
    "gh pr create --head feature ; eval \"gh pr create --head second --body 'a b'\"",
    "gh pr create --head feature ; case x in x) eval 'gh pr create --head second';; esac",
    "gh pr create --head feature ; case x in (x) bash -c 'gh pr create --head second';; esac",
    "gh pr create --head feature ; (gh pr create --head second) > log",
    "gh pr create --head feature ; (bash -c 'gh pr create --head second') 2>&1 | tee log",
    "gh pr create --head feature ; case x in x) (gh pr create --head second) > log;; esac",
]


@pytest.mark.parametrize("command", ALL_LATER_CREATES_BASH_RUNS)
def test_should_deny_a_later_create_bash_runs_on_an_unreviewed_head(
    two_branch_checkout: tuple[Path, str, str], command: str
) -> None:
    folder, first_head, second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    assert f"no clean review for head {second_head}" in _deny_reason(_bash_in(folder, command))


def test_should_check_a_create_after_a_line_break_in_bash_c_in_the_folder_before_it(
    two_branch_checkout: tuple[Path, str, str],
) -> None:
    folder, first_head, second_head = two_branch_checkout
    _git(folder, "checkout", "--quiet", "feature")
    _git(folder, "worktree", "add", "--quiet", str(folder.parent / "usub"), "second")
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    command = 'gh pr create ; cd ../usub && bash -c "true\ngh pr create"'
    assert f"no clean review for head {second_head}" in _deny_reason(_bash_in(folder, command))


def test_should_allow_a_later_create_inside_a_quoted_value_after_a_line_break(
    two_branch_checkout: tuple[Path, str, str],
) -> None:
    folder, first_head, _second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    command = 'gh pr create --head feature --body "a\ngh pr create --head second"'
    assert _reason(_bash_in(folder, command)) is None


def test_should_allow_a_reviewed_create_in_a_substitution_whose_body_holds_a_line_break(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    command = "x=$(gh pr create --head feature --body 'a\nb'\nls '')"
    assert _reason(_bash_in(folder, command)) is None


def test_should_allow_a_reviewed_create_after_an_eval_script_bash_cannot_parse(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    command = "bash -c \"eval 'gh pr create --title 'a b' --body \"x; gh pr create --head feature --body \"y\""
    assert _reason(_bash_in(folder, command)) is None


def test_should_allow_a_reviewed_create_a_wrapped_script_runs_before_another_line(
    two_branch_checkout: tuple[Path, str, str],
) -> None:
    folder, first_head, _second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    command = "gh pr create --head feature && bash -c 'gh pr create --head feature\nls'"
    assert _reason(_bash_in(folder, command)) is None


def test_should_allow_a_body_a_heredoc_substitution_writes_with_quotes_inside(
    two_branch_checkout: tuple[Path, str, str],
) -> None:
    folder, first_head, _second_head = two_branch_checkout
    merge_review_receipt.record_open_review("acme/tools", first_head, 0)
    command = (
        "gh pr create --head feature --body \"$(cat <<'BODY'\n"
        'see "q" ; gh pr create --head second\nBODY\n)"'
    )
    assert _reason(_bash_in(folder, command)) is None
