"""Behavior tests for the clean-review merge gate."""

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
SCRIPTS_DIRECTORY = HOOKS_DIRECTORY.parent / "scripts"
for each_directory in (HOOKS_DIRECTORY, SCRIPTS_DIRECTORY):
    if str(each_directory) not in sys.path:
        sys.path.insert(0, str(each_directory))

import merge_review_receipt
from blocking import merge_review_gate as gate

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


def test_should_deny_a_merge_with_no_review() -> None:
    assert "no clean review" in _reason(_merge_tool(CLEAN_HEAD))


def test_should_deny_a_merge_whose_last_pass_found_findings() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 2)
    assert "no clean review" in _reason(_merge_tool(CLEAN_HEAD))


def test_should_allow_a_merge_pinned_to_the_clean_head() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    assert _reason(_merge_tool(CLEAN_HEAD)) is None


def test_should_allow_a_merge_whose_findings_are_all_ruled_out_with_a_link() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 2, 2, RULINGS_LINK)
    assert _reason(_merge_tool(CLEAN_HEAD)) is None


def test_should_deny_a_merge_with_a_finding_left_open() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 3, 2, RULINGS_LINK)
    assert "no clean review" in _reason(_merge_tool(CLEAN_HEAD))


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
def test_is_clean_receipt_should_reject_a_receipt_it_cannot_back(receipt: dict[str, object]) -> None:
    assert gate.is_clean_receipt(receipt, "acme", "tools", 12) is False


def test_is_clean_receipt_should_accept_zero_findings() -> None:
    assert gate.is_clean_receipt({"head": CLEAN_HEAD, "findings": 0}, "acme", "tools", 12) is True


@pytest.mark.parametrize(
    "rulings", ["x", "https://github.com/acme/tools/pull/13#issuecomment-1"]
)
def test_should_deny_a_merge_whose_rulings_link_is_not_a_comment_on_this_pull_request(
    rulings: str,
) -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 2, 2, rulings)
    assert "no clean review" in _reason(_merge_tool(CLEAN_HEAD))


def test_should_name_the_ruled_out_route_in_the_deny_reason() -> None:
    assert "--ruled-out" in _reason(_merge_tool(CLEAN_HEAD))


def test_should_deny_a_merge_pinned_to_a_head_pushed_after_the_review() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    assert "Review the new head" in _reason(_merge_tool(NEW_HEAD))


def test_should_deny_an_unpinned_merge_after_a_clean_review() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    assert "names no head" in _reason(_merge_tool())


def test_should_deny_auto_merge_that_names_no_head() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    payload = {
        "tool_name": "mcp__github__enable_pr_auto_merge",
        "tool_input": {"owner": "acme", "repo": "tools", "pullNumber": 12},
    }
    assert f"--match-head-commit {CLEAN_HEAD}" in _reason(payload)


def test_should_allow_any_merge_in_an_exempt_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES", "other/x, ACME/Tools")
    assert _reason(_merge_tool()) is None


def test_should_read_a_gh_pr_merge_pinned_with_a_short_head() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    command = f"gh pr merge --squash 12 --repo acme/tools --match-head-commit {CLEAN_HEAD[:7]}"
    assert _reason(_bash(command)) is None


def test_should_deny_gh_pr_merge_auto() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    assert "Auto-merge" in _reason(
        _bash("gh pr merge https://github.com/acme/tools/pull/12 --auto")
    )


def test_should_deny_gh_pr_merge_with_no_repository() -> None:
    assert "names no repository" in _reason(_bash("gh pr merge 12 --squash"))


def test_should_read_a_gh_api_merge_with_a_sha_field() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    command = f"gh api -X PUT repos/acme/tools/pulls/12/merge -f sha={CLEAN_HEAD}"
    assert _reason(_bash(command)) is None


def test_should_ignore_commands_that_merge_nothing() -> None:
    assert gate.decision_for(_bash("gh pr view 12 --repo acme/tools")) is None
    assert gate.decision_for(_bash("git merge origin/main")) is None


def test_should_name_the_configured_review_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_COMMAND", "/team-review")
    assert "`/team-review`" in _reason(_merge_tool(CLEAN_HEAD))


def test_should_name_the_low_fix_pass_after_three_full_reviews_in_the_deny_reason() -> None:
    reason = _reason(_merge_tool(CLEAN_HEAD))
    assert "three full passes" in reason
    assert "`/code-review low --fix 12`" in reason


def test_should_allow_auto_merge_pinned_to_the_clean_head() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    command = f"gh pr merge 12 --repo acme/tools --auto --match-head-commit {CLEAN_HEAD}"
    assert _reason(_bash(command)) is None


def test_should_deny_pinned_auto_merge_with_no_clean_review() -> None:
    command = f"gh pr merge 12 --repo acme/tools --auto --match-head-commit {CLEAN_HEAD}"
    assert "no clean review" in _reason(_bash(command))


def test_should_deny_auto_merge_pinned_to_a_newer_head() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    command = f"gh pr merge 12 --repo acme/tools --auto --match-head-commit {NEW_HEAD}"
    assert "Review the new head" in _reason(_bash(command))


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
    reason = _reason(_create_tool(folder))
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
    assert "no clean review" in _reason(_create_tool(folder))


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
    assert "no clean review" in _reason(_create_tool(folder))


def test_should_deny_a_pull_request_open_after_a_push_past_the_review(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, _head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", NEW_HEAD, 0)
    assert "no clean review" in _reason(_create_tool(folder))


def test_should_read_gh_pr_create_with_repo_and_head(branch_checkout: tuple[Path, str]) -> None:
    folder, head = branch_checkout
    command = "gh pr create --repo acme/tools --head feature --title t --body b"
    assert "no clean review" in _reason(_bash_in(folder, command))
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    assert _reason(_bash_in(folder, command)) is None


def test_should_read_gh_pr_create_repository_from_origin(branch_checkout: tuple[Path, str]) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    assert _reason(_bash_in(folder, "gh pr create --fill")) is None


def test_should_read_the_pull_request_script_create(branch_checkout: tuple[Path, str]) -> None:
    folder, head = branch_checkout
    command = "python scripts/pull_request.py create --repo acme/tools --head feature"
    assert f"head {head}" in _reason(_bash_in(folder, command))


def test_should_deny_a_pull_request_open_whose_head_cannot_be_read(tmp_path: Path) -> None:
    reason = _reason(_create_tool(tmp_path, head="missing-branch"))
    assert "names no repository or head commit" in reason


def test_should_read_the_pushed_head_of_a_branch_outside_any_checkout(
    branch_checkout: tuple[Path, str], tmp_path: Path
) -> None:
    _folder, head = branch_checkout
    outside = tmp_path / "outside"
    outside.mkdir()
    assert f"no clean review for head {head}" in _reason(_create_tool(outside))
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
    assert "no clean review" in _reason(_merge_tool(head))


def test_should_deny_a_merge_pinned_past_the_head_reviewed_before_open() -> None:
    merge_review_receipt.record_open_review("acme/tools", CLEAN_HEAD, 0)
    assert "no clean review" in _reason(_merge_tool(NEW_HEAD))


def test_should_deny_an_unpinned_merge_with_only_an_open_review() -> None:
    merge_review_receipt.record_open_review("acme/tools", CLEAN_HEAD, 0)
    assert "no clean review" in _reason(_merge_tool())


def test_should_not_accept_an_open_review_from_another_repository() -> None:
    merge_review_receipt.record_open_review("acme/other", CLEAN_HEAD, 0)
    assert "no clean review" in _reason(_merge_tool(CLEAN_HEAD))


def test_should_accept_an_open_review_recorded_under_the_old_owner() -> None:
    merge_review_receipt.record_open_review("oldowner/tools", CLEAN_HEAD, 0)
    assert _reason(_merge_tool(CLEAN_HEAD)) is None


def test_should_deny_a_merge_whose_numbered_pass_found_findings_at_the_open_reviewed_head() -> None:
    merge_review_receipt.record_open_review("acme/tools", CLEAN_HEAD, 0)
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 2)
    assert "no clean review" in _reason(_merge_tool(CLEAN_HEAD))


def test_should_ignore_an_open_receipt_whose_head_is_not_a_commit(receipt_folder: Path) -> None:
    heads_folder = receipt_folder / "heads"
    heads_folder.mkdir()
    (heads_folder / "acme__tools__a.json").write_text('{"head": "a", "findings": 0}', encoding="utf-8")
    assert "no clean review" in _reason(_merge_tool(CLEAN_HEAD))


def test_should_check_a_merge_chained_after_a_reviewed_open(
    branch_checkout: tuple[Path, str],
) -> None:
    folder, head = branch_checkout
    merge_review_receipt.record_open_review("acme/tools", head, 0)
    command = (
        "gh pr create --repo acme/tools --head feature --fill && "
        f"gh pr merge 12 --repo acme/tools --match-head-commit {NEW_HEAD}"
    )
    assert "no clean review" in _reason(_bash_in(folder, command))


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
    assert f"head {pushed_head}" in _reason(_create_tool(folder))


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
    assert f"head {fetched_head}" in _reason(_bash_in(folder, command))


def test_should_not_match_an_open_receipt_on_a_short_pinned_head() -> None:
    merge_review_receipt.record_open_review("acme/tools", CLEAN_HEAD, 0)
    assert "no clean review" in _reason(_merge_tool(CLEAN_HEAD[:3]))


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
    assert "names no repository or head commit" in _reason(
        _bash_in(folder, f'cd "{elsewhere}" && gh pr create --repo acme/tools --fill')
    )
