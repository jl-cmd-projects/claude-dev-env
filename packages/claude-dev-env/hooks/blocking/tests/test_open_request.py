"""Behavioral tests for reading a pull request open from a PreToolUse payload.

gh pr create --repo acme/tools --title "--head evil" -> acme/tools, quoted option ignored
mcp create_pull_request {owner, repo}                -> acme/tools, no head
gh pr merge 12                                       -> no open
"""

from __future__ import annotations

from pathlib import Path

from blocking.merge_review_gate_parts.open_request import OpenRequest, open_request_from


def _shell_payload(command: str, folder: Path) -> dict[str, object]:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(folder)}


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


def test_should_return_none_for_a_command_that_opens_nothing(tmp_path: Path) -> None:
    assert open_request_from(_shell_payload("gh pr merge 12", tmp_path)) is None


def test_should_name_the_slug_from_owner_and_repo() -> None:
    assert OpenRequest(owner="acme", repo="tools", head=None).slug == "acme/tools"
