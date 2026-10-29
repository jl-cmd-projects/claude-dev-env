"""Behavioral tests for reading a pull request open from a PreToolUse payload.

gh pr create --repo acme/tools --title "--head evil" -> acme/tools, quoted option ignored
mcp create_pull_request {owner, repo}                -> acme/tools, no head
gh pr merge 12                                       -> no open
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from blocking.merge_review_gate_parts.open_request import OpenRequest, open_request_from


def _shell_payload(command: str, folder: Path) -> dict[str, object]:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(folder)}


def _git(folder: Path, *all_arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(folder), *all_arguments], capture_output=True, text=True, check=True
    )
    return completed.stdout.strip()


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


def test_should_read_a_branch_no_checkout_holds_from_the_named_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _git(checkout, "init", "--quiet", "--initial-branch", "feature")
    _git(
        checkout,
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
    head = _git(checkout, "rev-parse", "HEAD")
    remotes = tmp_path / "remotes"
    (remotes / "acme" / "tools.git").mkdir(parents=True)
    _git(remotes / "acme" / "tools.git", "init", "--quiet", "--bare")
    _git(checkout, "push", "--quiet", str(remotes / "acme" / "tools.git"), "feature")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{remotes}/.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://github.com/")
    payload = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "acme", "repo": "tools", "head": "feature"},
        "cwd": str(tmp_path),
    }
    assert open_request_from(payload) == OpenRequest(owner="acme", repo="tools", head=head)


def test_should_read_a_fork_branch_from_the_fork_not_a_same_named_local_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _git(checkout, "init", "--quiet", "--initial-branch", "feature")
    _git(
        checkout,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        "local",
    )
    local_head = _git(checkout, "rev-parse", "HEAD")
    _git(checkout, "checkout", "--quiet", "-b", "fork-work")
    _git(
        checkout,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        "fork",
    )
    fork_head = _git(checkout, "rev-parse", "HEAD")
    _git(checkout, "checkout", "--quiet", "feature")
    remotes = tmp_path / "remotes"
    (remotes / "someone" / "tools.git").mkdir(parents=True)
    _git(remotes / "someone" / "tools.git", "init", "--quiet", "--bare")
    _git(checkout, "push", "--quiet", str(remotes / "someone" / "tools.git"), "fork-work:feature")
    assert local_head != fork_head
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{remotes}/.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://github.com/")
    payload = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "acme", "repo": "tools", "head": "someone:feature"},
        "cwd": str(checkout),
    }
    assert open_request_from(payload) == OpenRequest(owner="acme", repo="tools", head=fork_head)


def test_should_read_the_github_branch_before_a_diverged_local_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _git(checkout, "init", "--quiet", "--initial-branch", "feature")
    _git(
        checkout,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        "local",
    )
    local_head = _git(checkout, "rev-parse", "HEAD")
    _git(checkout, "checkout", "--quiet", "-b", "pushed-work")
    _git(
        checkout,
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
    pushed_head = _git(checkout, "rev-parse", "HEAD")
    _git(checkout, "checkout", "--quiet", "feature")
    remotes = tmp_path / "github.com"
    (remotes / "acme" / "tools.git").mkdir(parents=True)
    _git(remotes / "acme" / "tools.git", "init", "--quiet", "--bare")
    _git(checkout, "push", "--quiet", str(remotes / "acme" / "tools.git"), "pushed-work:feature")
    assert local_head != pushed_head
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{remotes}/.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://github.com/")
    payload = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "acme", "repo": "tools", "head": "feature"},
        "cwd": str(checkout),
    }
    assert open_request_from(payload) == OpenRequest(
        owner="acme", repo="tools", head=pushed_head
    )


def test_should_read_no_head_when_the_github_lookup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _git(checkout, "init", "--quiet", "--initial-branch", "feature")
    _git(
        checkout,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        "local",
    )
    (tmp_path / "github.com").mkdir()
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{tmp_path / 'github.com'}/.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://github.com/")
    payload = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "acme", "repo": "tools", "head": "feature"},
        "cwd": str(checkout),
    }
    assert open_request_from(payload) == OpenRequest(owner="acme", repo="tools", head=None)


def test_should_return_none_for_a_command_that_opens_nothing(tmp_path: Path) -> None:
    assert open_request_from(_shell_payload("gh pr merge 12", tmp_path)) is None


def test_should_name_the_slug_from_owner_and_repo() -> None:
    assert OpenRequest(owner="acme", repo="tools", head=None).slug == "acme/tools"
