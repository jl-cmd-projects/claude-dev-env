"""Behavioral tests for reading a pull request open from a PreToolUse payload.

gh pr create --repo acme/tools --title "--head evil" -> acme/tools, quoted option ignored
mcp create_pull_request {owner, repo, head}          -> acme/tools, head listed by GitHub
mcp create_pull_request {owner, repo, head: u:b}     -> acme/tools, head listed for u
gh pr merge 12                                       -> no open
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from blocking.merge_review_gate_parts import open_request
from blocking.merge_review_gate_parts.open_request import OpenRequest, open_request_from


def _shell_payload(command: str, folder: Path) -> dict[str, object]:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(folder)}


def _create_payload(head: str, folder: Path, owner: str = "acme") -> dict[str, object]:
    return {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": owner, "repo": "tools", "head": head},
        "cwd": str(folder),
    }


def _git(folder: Path, *all_arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(folder), *all_arguments], capture_output=True, text=True, check=True
    )
    return completed.stdout.strip()


def _commit(folder: Path, message: str) -> str:
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
        message,
    )
    return _git(folder, "rev-parse", "HEAD")


def _checkout_on(tmp_path: Path, branch: str) -> Path:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _git(checkout, "init", "--quiet", "--initial-branch", branch)
    return checkout


def _bare_remote(github: Path, owner: str) -> Path:
    remote = github / owner / "tools.git"
    remote.mkdir(parents=True)
    _git(remote, "init", "--quiet", "--bare")
    return remote


def _redirect_github(monkeypatch: pytest.MonkeyPatch, github: Path) -> None:
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{github}/.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://github.com/")


def test_should_read_the_repository_and_ignore_options_quoted_in_the_title(tmp_path: Path) -> None:
    payload = _shell_payload('gh pr create --repo acme/tools --title "--head evil"', tmp_path)
    assert open_request_from(payload) == OpenRequest(owner="acme", repo="tools", head=None)


def test_should_read_the_create_tool_with_no_head_branch(tmp_path: Path) -> None:
    payload = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "acme", "repo": "tools"},
        "cwd": str(tmp_path),
    }
    assert open_request_from(payload) == OpenRequest(owner="acme", repo="tools", head=None)


def test_should_read_a_pushed_branch_from_outside_any_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    head = _commit(checkout, "first")
    github = tmp_path / "github.com"
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "acme")), "feature")
    _redirect_github(monkeypatch, github)
    assert open_request_from(_create_payload("feature", tmp_path)) == OpenRequest(
        owner="acme", repo="tools", head=head
    )


def test_should_read_a_fork_branch_from_the_fork_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    base_head = _commit(checkout, "base")
    github = tmp_path / "github.com"
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "acme")), "feature")
    fork_head = _commit(checkout, "fork")
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "someone")), "feature")
    _redirect_github(monkeypatch, github)
    assert base_head != fork_head
    assert open_request_from(_create_payload("someone:feature", tmp_path)).head == fork_head


def test_should_read_no_head_for_a_branch_the_repository_does_not_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    github = tmp_path / "github.com"
    _bare_remote(github, "acme")
    _redirect_github(monkeypatch, github)
    assert open_request_from(_create_payload("feature", tmp_path)).head is None


def test_should_list_in_an_empty_folder_so_the_checkout_config_never_applies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    head = _commit(checkout, "first")
    github = tmp_path / "github.com"
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "acme")), "feature")
    _redirect_github(monkeypatch, github)
    decoy = tmp_path / "decoy"
    _commit(checkout, "decoy")
    _git(checkout, "push", "--quiet", str(_bare_remote(decoy, "acme")), "feature")
    _git(checkout, "config", f"url.{decoy}/acme/.insteadOf", "https://github.com/acme/")
    monkeypatch.chdir(checkout)
    assert open_request_from(_create_payload("feature", tmp_path)).head == head


def test_should_read_no_head_when_the_listing_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    def time_out(all_arguments: list[str], **_all_keyword_arguments: object) -> None:
        raise subprocess.TimeoutExpired(all_arguments, 1)

    monkeypatch.setattr(open_request.subprocess, "run", time_out)
    assert open_request_from(_create_payload("feature", Path("."))).head is None


def test_should_run_the_listing_without_a_terminal_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GIT_TERMINAL_PROMPT", raising=False)
    monkeypatch.delenv("GCM_INTERACTIVE", raising=False)
    all_environments: list[dict[str, str]] = []

    def record_environment(
        all_arguments: list[str], **all_keyword_arguments: dict[str, str]
    ) -> subprocess.CompletedProcess[bytes]:
        if "env" in all_keyword_arguments:
            all_environments.append(all_keyword_arguments["env"])
        return subprocess.CompletedProcess(all_arguments, 1)

    monkeypatch.setattr(open_request.subprocess, "run", record_environment)
    open_request_from(_create_payload("feature", Path(".")))
    assert all_environments[0]["GIT_TERMINAL_PROMPT"] == "0"
    assert all_environments[0]["GCM_INTERACTIVE"] == "never"


def test_should_pick_the_listed_line_that_names_the_branch_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing = f"{'1' * 40}\trefs/heads/feature-two\n{'2' * 40}\trefs/heads/feature\n"

    def list_branches(
        all_arguments: list[str], **all_keyword_arguments: object
    ) -> subprocess.CompletedProcess[bytes]:
        all_keyword_arguments["stdout"].write(listing.encode())
        return subprocess.CompletedProcess(all_arguments, 0)

    monkeypatch.setattr(open_request.subprocess, "run", list_branches)
    assert open_request_from(_create_payload("feature", Path("."))).head == "2" * 40


def test_should_run_no_listing_for_a_call_that_names_no_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    all_commands: list[list[str]] = []

    def record_command(
        all_arguments: list[str], **_all_keyword_arguments: object
    ) -> subprocess.CompletedProcess[bytes]:
        all_commands.append(all_arguments)
        return subprocess.CompletedProcess(all_arguments, 1)

    monkeypatch.setattr(open_request.subprocess, "run", record_command)
    assert open_request_from(_create_payload("feature", Path("."), owner="")).head is None
    assert not any("ls-remote" in each_command for each_command in all_commands)


def test_should_read_the_checkout_branch_when_github_lists_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    head = _commit(checkout, "first")
    github = tmp_path / "github.com"
    _bare_remote(github, "acme")
    _redirect_github(monkeypatch, github)
    assert open_request_from(_create_payload("feature", checkout)).head == head


def test_should_read_a_shell_open_branch_from_the_checkout(tmp_path: Path) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    head = _commit(checkout, "first")
    payload = _shell_payload("gh pr create --repo acme/tools --head feature", checkout)
    assert open_request_from(payload) == OpenRequest(owner="acme", repo="tools", head=head)


def test_should_read_no_open_from_a_merge_command(tmp_path: Path) -> None:
    assert open_request_from(_shell_payload("gh pr merge 12", tmp_path)) is None
