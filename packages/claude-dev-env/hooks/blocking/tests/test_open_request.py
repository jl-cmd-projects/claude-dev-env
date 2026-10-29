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


def _bare_remote(github: Path, owner: str, name: str = "tools") -> Path:
    remote = github / owner / f"{name}.git"
    remote.mkdir(parents=True)
    _git(remote, "init", "--quiet", "--bare")
    return remote


def _redirect_prefixes(
    monkeypatch: pytest.MonkeyPatch, all_rewrites: list[tuple[str, Path]]
) -> None:
    monkeypatch.setenv("GIT_CONFIG_COUNT", str(len(all_rewrites)))
    for each_index, (each_prefix, each_folder) in enumerate(all_rewrites):
        monkeypatch.setenv(f"GIT_CONFIG_KEY_{each_index}", f"url.{each_folder}/.insteadOf")
        monkeypatch.setenv(f"GIT_CONFIG_VALUE_{each_index}", each_prefix)


def _redirect_github(monkeypatch: pytest.MonkeyPatch, github: Path) -> None:
    _redirect_prefixes(monkeypatch, [("https://github.com/", github)])


def _redirect_ssh_only(monkeypatch: pytest.MonkeyPatch, github: Path, unreachable: Path) -> None:
    _redirect_prefixes(
        monkeypatch, [("https://github.com/", unreachable), ("git@github.com:", github)]
    )


def _completed(
    all_arguments: list[str],
    all_keyword_arguments: dict[str, object],
    output: str | None,
) -> subprocess.CompletedProcess[str]:
    if output is None:
        return subprocess.CompletedProcess(all_arguments, 1)
    all_keyword_arguments["stdout"].write(output.encode())
    return subprocess.CompletedProcess(all_arguments, 0)


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
        return _completed(all_arguments, keyword_arguments, None)

    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "1")
    monkeypatch.setenv("GCM_INTERACTIVE", "always")
    monkeypatch.setattr(subprocess, "run", stand_in_run)
    assert open_request_from(_create_payload("feature", tmp_path)) == OpenRequest(
        owner="acme", repo="tools", head=None
    )
    assert len(all_captured_environments) >= 2
    for each_environment in all_captured_environments:
        assert each_environment["GIT_TERMINAL_PROMPT"] == "0"
        assert each_environment["GCM_INTERACTIVE"] == "never"


def test_should_read_a_branch_through_an_ssh_checkout_remote_when_https_is_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    head = _commit(checkout, "first")
    github = tmp_path / "github.com"
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "acme")), "feature")
    _git(checkout, "remote", "add", "origin", "git@github.com:acme/tools.git")
    _redirect_ssh_only(monkeypatch, github, tmp_path / "unreachable")
    assert open_request_from(_create_payload("feature", checkout)) == OpenRequest(
        owner="acme", repo="tools", head=head
    )


def test_should_ignore_a_checkout_remote_that_is_a_local_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    _commit(checkout, "first")
    origin = _bare_remote(tmp_path / "github.com", "acme")
    _git(checkout, "push", "--quiet", str(origin), "feature")
    _git(checkout, "remote", "add", "origin", str(origin))
    _redirect_github(monkeypatch, tmp_path / "unreachable")
    assert open_request_from(_create_payload("feature", checkout)).head is None


def test_should_ignore_a_checkout_remote_that_only_contains_a_github_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    _commit(checkout, "first")
    foreign = tmp_path / "foreign"
    lookalike = foreign / "https:" / "github.com" / "acme" / "tools.git"
    lookalike.mkdir(parents=True)
    _git(lookalike, "init", "--quiet", "--bare")
    _git(checkout, "push", "--quiet", str(lookalike), "feature")
    _git(checkout, "remote", "add", "origin", "https://foreign.example/https://github.com/acme/tools.git")
    _redirect_prefixes(
        monkeypatch,
        [("https://github.com/", tmp_path / "unreachable"), ("https://foreign.example/", foreign)],
    )
    assert open_request_from(_create_payload("feature", checkout)).head is None


def test_should_list_the_branch_from_the_literal_remote_url_in_an_empty_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    monkeypatch.delenv("GIT_SSH", raising=False)
    all_calls: list[tuple[list[str], object, bool]] = []

    def stand_in_run(
        all_arguments: list[str], **keyword_arguments: object
    ) -> subprocess.CompletedProcess[str]:
        folder = keyword_arguments["cwd"]
        all_calls.append((list(all_arguments), folder, folder is not None and Path(folder).is_dir()))
        if "--get-regexp" in all_arguments:
            remote_line = "remote.origin.url git@github.com:acme/tools.git\n"
            return _completed(all_arguments, keyword_arguments, remote_line)
        return _completed(all_arguments, keyword_arguments, None)

    monkeypatch.setattr(subprocess, "run", stand_in_run)
    open_request_from(_create_payload("feature", tmp_path))
    all_outside_calls = [each_call for each_call in all_calls if "--get-regexp" not in each_call[0]]
    assert [each_call[0][1] for each_call in all_outside_calls] == ["config", "ls-remote"]
    assert all_outside_calls[-1][0] == [
        "git",
        "ls-remote",
        "--",
        "git@github.com:acme/tools.git",
        "refs/heads/feature",
    ]
    for each_call in all_outside_calls:
        assert each_call[2]
        assert each_call[1] != str(tmp_path)


def test_should_read_a_branch_through_a_checkout_remote_that_names_a_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    head = _commit(checkout, "first")
    github = tmp_path / "github.com"
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "acme")), "feature")
    deploy_user_prefix = "https://deploy-user@github.com/"
    _git(checkout, "remote", "add", "origin", f"{deploy_user_prefix}acme/tools.git")
    _redirect_prefixes(
        monkeypatch, [("https://github.com/", tmp_path / "unreachable"), (deploy_user_prefix, github)]
    )
    assert open_request_from(_create_payload("feature", checkout)) == OpenRequest(
        owner="acme", repo="tools", head=head
    )


@pytest.mark.parametrize(
    ("remote_url", "ssh_command", "ssh_program", "configured_command", "expected_command"),
    [
        ("git@github.com:acme/tools.git", None, None, None, "ssh -o BatchMode=yes"),
        ("git@github.com:acme/tools.git", "ssh -i key", None, None, "ssh -i key -o BatchMode=yes"),
        ("git@github.com:acme/tools.git", None, None, "ssh -F cfg", "ssh -F cfg -o BatchMode=yes"),
        ("git@github.com:acme/tools.git", None, "plink", None, None),
        ("https://github.com/acme/tools.git", None, None, None, None),
    ],
)
def test_should_keep_ssh_from_prompting_while_it_lists_the_branch(
    remote_url: str,
    ssh_command: str | None,
    ssh_program: str | None,
    configured_command: str | None,
    expected_command: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for each_name, each_value in (("GIT_SSH_COMMAND", ssh_command), ("GIT_SSH", ssh_program)):
        if each_value is None:
            monkeypatch.delenv(each_name, raising=False)
        else:
            monkeypatch.setenv(each_name, each_value)
    all_listing_commands: list[str | None] = []

    def stand_in_run(
        all_arguments: list[str], **keyword_arguments: object
    ) -> subprocess.CompletedProcess[str]:
        if "--get-regexp" in all_arguments:
            return _completed(all_arguments, keyword_arguments, f"remote.origin.url {remote_url}\n")
        if "core.sshCommand" in all_arguments:
            return _completed(all_arguments, keyword_arguments, configured_command)
        if "ls-remote" in all_arguments:
            all_listing_commands.append(keyword_arguments["env"].get("GIT_SSH_COMMAND"))
        return _completed(all_arguments, keyword_arguments, None)

    monkeypatch.setattr(subprocess, "run", stand_in_run)
    open_request_from(_create_payload("feature", tmp_path))
    assert all_listing_commands == [expected_command]


def test_should_read_the_local_branch_before_a_stale_remote_tracking_branch_when_github_lists_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    stale_head = _commit(checkout, "stale")
    _git(checkout, "update-ref", "refs/remotes/origin/feature", stale_head)
    local_head = _commit(checkout, "local")
    github = tmp_path / "github.com"
    _bare_remote(github, "acme")
    _redirect_github(monkeypatch, github)
    assert open_request_from(_create_payload("feature", checkout)) == OpenRequest(
        owner="acme", repo="tools", head=local_head
    )


def test_should_ignore_a_remote_of_the_fork_owner_that_is_another_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    _commit(checkout, "fork")
    github = tmp_path / "github.com"
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "someone", "tools-fork")), "feature")
    _git(checkout, "remote", "add", "fork", "git@github.com:someone/tools-fork.git")
    _redirect_ssh_only(monkeypatch, github, tmp_path / "unreachable")
    assert open_request_from(_create_payload("someone:feature", checkout)).head is None


def test_should_ignore_a_remote_url_whose_user_part_hides_another_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    _commit(checkout, "first")
    github = tmp_path / "github.com"
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "acme")), "feature")
    disguised_prefix = "https://other.example#@github.com/"
    _git(checkout, "remote", "add", "origin", f"{disguised_prefix}acme/tools.git")
    _redirect_prefixes(
        monkeypatch, [("https://github.com/", tmp_path / "unreachable"), (disguised_prefix, github)]
    )
    assert open_request_from(_create_payload("feature", checkout)).head is None


def test_should_prefer_the_fork_remote_named_like_the_base_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feat")
    other_head = _commit(checkout, "other repository")
    github = tmp_path / "github.com"
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "jon", "other")), "feat")
    tools_head = _commit(checkout, "tools repository")
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "jon", "tools")), "feat")
    assert other_head != tools_head
    _git(checkout, "remote", "add", "origin", "git@github.com:jon/other.git")
    _git(checkout, "remote", "add", "fork", "git@github.com:jon/tools.git")
    _redirect_ssh_only(monkeypatch, github, tmp_path / "unreachable")
    assert open_request_from(_create_payload("jon:feat", checkout)) == OpenRequest(
        owner="acme", repo="tools", head=tools_head
    )


def test_should_read_the_pushed_branch_when_the_open_names_no_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    pushed_head = _commit(checkout, "pushed")
    github = tmp_path / "github.com"
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "acme")), "feature")
    local_head = _commit(checkout, "local only")
    assert pushed_head != local_head
    _redirect_github(monkeypatch, github)
    payload = _shell_payload("gh pr create --repo acme/tools", checkout)
    assert open_request_from(payload) == OpenRequest(owner="acme", repo="tools", head=pushed_head)


def test_should_read_the_checked_out_commit_when_the_open_names_no_head_and_head_is_detached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    detached_head = _commit(checkout, "detached")
    _git(checkout, "checkout", "--quiet", "--detach")
    _redirect_github(monkeypatch, tmp_path / "unreachable")
    payload = _shell_payload("gh pr create --repo acme/tools", checkout)
    assert open_request_from(payload) == OpenRequest(
        owner="acme", repo="tools", head=detached_head
    )


def test_should_return_none_for_a_command_that_opens_nothing(tmp_path: Path) -> None:
    assert open_request_from(_shell_payload("gh pr merge 12", tmp_path)) is None


def test_should_name_the_slug_from_owner_and_repo() -> None:
    assert OpenRequest(owner="acme", repo="tools", head=None).slug == "acme/tools"
