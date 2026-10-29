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


def _create_payload(head: str, folder: Path) -> dict[str, object]:
    return {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "acme", "repo": "tools", "head": head},
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


def test_should_read_a_branch_no_checkout_holds_from_the_named_repository(
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


def test_should_read_a_fork_branch_from_the_fork_not_a_same_named_local_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    local_head = _commit(checkout, "local")
    _git(checkout, "checkout", "--quiet", "-b", "fork-work")
    fork_head = _commit(checkout, "fork")
    _git(checkout, "checkout", "--quiet", "feature")
    github = tmp_path / "github.com"
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "someone")), "fork-work:feature")
    assert local_head != fork_head
    _redirect_github(monkeypatch, github)
    assert open_request_from(_create_payload("someone:feature", checkout)) == OpenRequest(
        owner="acme", repo="tools", head=fork_head
    )


def test_should_read_the_github_branch_before_a_diverged_local_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    local_head = _commit(checkout, "local")
    _git(checkout, "checkout", "--quiet", "-b", "pushed-work")
    pushed_head = _commit(checkout, "pushed")
    _git(checkout, "checkout", "--quiet", "feature")
    github = tmp_path / "github.com"
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "acme")), "pushed-work:feature")
    assert local_head != pushed_head
    _redirect_github(monkeypatch, github)
    assert open_request_from(_create_payload("feature", checkout)) == OpenRequest(
        owner="acme", repo="tools", head=pushed_head
    )


def test_should_read_no_head_when_the_github_lookup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    _commit(checkout, "local")
    github = tmp_path / "github.com"
    github.mkdir()
    _redirect_github(monkeypatch, github)
    assert open_request_from(_create_payload("feature", checkout)) == OpenRequest(
        owner="acme", repo="tools", head=None
    )


def test_should_look_up_the_github_branch_with_every_sign_in_prompt_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_captured_environments: list[dict[str, str]] = []

    def stand_in_run(
        all_arguments: list[str], **keyword_arguments: object
    ) -> subprocess.CompletedProcess[str]:
        all_captured_environments.append(dict(keyword_arguments["env"]))
        return subprocess.CompletedProcess(all_arguments, 1, stdout="", stderr="")

    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "1")
    monkeypatch.setenv("GCM_INTERACTIVE", "always")
    monkeypatch.setattr(subprocess, "run", stand_in_run)
    assert open_request_from(_create_payload("feature", tmp_path)) == OpenRequest(
        owner="acme", repo="tools", head=None
    )
    (lookup_environment,) = all_captured_environments
    assert lookup_environment["GIT_TERMINAL_PROMPT"] == "0"
    assert lookup_environment["GCM_INTERACTIVE"] == "never"


def test_should_return_none_for_a_command_that_opens_nothing(tmp_path: Path) -> None:
    assert open_request_from(_shell_payload("gh pr merge 12", tmp_path)) is None


def test_should_name_the_slug_from_owner_and_repo() -> None:
    assert OpenRequest(owner="acme", repo="tools", head=None).slug == "acme/tools"
