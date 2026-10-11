"""Behavior tests for the clean-review merge gate."""

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


@pytest.fixture(autouse=True)
def receipt_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CLAUDE_MERGE_REVIEW_RECEIPT_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_MERGE_REVIEW_EXEMPT_REPOSITORIES", raising=False)
    monkeypatch.delenv("CLAUDE_MERGE_REVIEW_COMMAND", raising=False)
    return tmp_path


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


def test_should_deny_a_merge_pinned_to_a_head_pushed_after_the_review() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    assert "Review the new head" in _reason(_merge_tool(NEW_HEAD))


def test_should_deny_an_unpinned_merge_after_a_clean_review() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    assert "names no head" in _reason(_merge_tool())


def test_should_deny_auto_merge_even_after_a_clean_review() -> None:
    merge_review_receipt.record_review("acme/tools", 12, CLEAN_HEAD, 0)
    payload = {
        "tool_name": "mcp__github__enable_pr_auto_merge",
        "tool_input": {"owner": "acme", "repo": "tools", "pullNumber": 12},
    }
    assert "Auto-merge" in _reason(payload)


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
