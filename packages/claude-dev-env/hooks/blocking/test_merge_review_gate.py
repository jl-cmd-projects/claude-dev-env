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
RULINGS_LINK = "https://github.com/acme/tools/pull/12#issuecomment-1"


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
