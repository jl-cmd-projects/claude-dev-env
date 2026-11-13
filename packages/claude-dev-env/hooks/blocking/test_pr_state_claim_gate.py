"""Behavior tests for the gate that holds a pull request status claim until this turn read that pull request's state."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import pr_state_claim_gate as gate

GATE_PATH = Path(__file__).resolve().parent / "pr_state_claim_gate.py"
POST_TOOL_NAME = "mcp__hearthbot__post_message"
COORDINATOR_TOOL_NAME = "mcp__hearthbot__message_coordinator"
READ_TOOL_NAME = "mcp__github__pull_request_read"
READY_MESSAGE = "PR 29 is ready to merge."
MERGED_MESSAGE = "PR 29 merged at 13:22 UTC."
INCIDENT_READ_METHODS = ("get_check_runs", "get_reviews", "get_comments")


def _prompt(text: str) -> str:
    return json.dumps({"type": "user", "message": {"content": text}})


def _call(tool_use_id: str, tool_name: str, tool_input: dict[str, object]) -> str:
    tool_use = {"type": "tool_use", "id": tool_use_id, "name": tool_name, "input": tool_input}
    return json.dumps({"type": "assistant", "message": {"content": [tool_use]}})


def _result(tool_use_id: str, is_error: bool = False) -> str:
    tool_result = {"type": "tool_result", "tool_use_id": tool_use_id, "is_error": is_error, "content": "ok"}
    return json.dumps({"type": "user", "message": {"content": [tool_result]}})


def _successful_call(tool_use_id: str, tool_name: str, tool_input: dict[str, object]) -> list[str]:
    return [_call(tool_use_id, tool_name, tool_input), _result(tool_use_id)]


def _read(tool_use_id: str, method: str, number: int = 29) -> list[str]:
    return _successful_call(
        tool_use_id, READ_TOOL_NAME, {"method": method, "owner": "o", "repo": "r", "pullNumber": number}
    )


def _shell(tool_use_id: str, command: str) -> list[str]:
    return _successful_call(tool_use_id, "Bash", {"command": command})


def _incident_turn() -> list[str]:
    all_lines = [_prompt("check PR 29")]
    for each_index, each_method in enumerate(INCIDENT_READ_METHODS):
        all_lines.extend(_read(f"read-{each_index}", each_method))
    return all_lines


def _payload(tmp_path: Path, all_lines: list[str], message_text: str, tool_name: str = POST_TOOL_NAME) -> dict[str, object]:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text("\n".join(all_lines) + "\n", encoding="utf-8")
    return {
        "tool_name": tool_name,
        "tool_input": {"text": message_text},
        "transcript_path": str(transcript_path),
    }


def _is_denied(decision: dict[str, object] | None) -> bool:
    return decision is not None and "PR 29" in json.dumps(decision)


def test_ready_claim_after_check_run_review_and_comment_reads_is_denied(tmp_path: Path) -> None:
    decision = gate.decision_for(_payload(tmp_path, _incident_turn(), READY_MESSAGE))

    assert _is_denied(decision)


def test_ready_claim_after_a_state_read_this_turn_passes(tmp_path: Path) -> None:
    all_lines = _incident_turn() + _read("read-get", "get")

    assert gate.decision_for(_payload(tmp_path, all_lines, READY_MESSAGE)) is None


def test_merged_pull_request_reported_as_merged_passes(tmp_path: Path) -> None:
    assert gate.decision_for(_payload(tmp_path, _incident_turn(), MERGED_MESSAGE)) is None


def test_state_read_from_before_the_last_prompt_is_denied(tmp_path: Path) -> None:
    all_lines = _read("read-old", "get") + [_prompt("status?")]

    assert _is_denied(gate.decision_for(_payload(tmp_path, all_lines, READY_MESSAGE)))


def test_state_read_of_another_pull_request_is_denied(tmp_path: Path) -> None:
    all_lines = [_prompt("go")] + _read("read-30", "get", number=30)

    assert _is_denied(gate.decision_for(_payload(tmp_path, all_lines, READY_MESSAGE)))


def test_failed_state_read_is_denied(tmp_path: Path) -> None:
    all_lines = [_prompt("go"), _call("read-1", READ_TOOL_NAME, {"method": "get", "pullNumber": 29}), _result("read-1", True)]

    assert _is_denied(gate.decision_for(_payload(tmp_path, all_lines, READY_MESSAGE)))


@pytest.mark.parametrize(
    "command",
    [
        "gh pr view 29",
        "gh pr view 29 --json state,mergedAt",
        "gh pr view https://github.com/o/r/pull/29 --json mergedAt",
        "gh api repos/o/r/pulls/29",
        "gh api repos/o/r/pulls/29 --jq '.merged'",
        "gh pr view 29 --json state,title --jq .state",
    ],
)
def test_shell_state_read_of_the_pull_request_passes(tmp_path: Path, command: str) -> None:
    all_lines = [_prompt("go")] + _shell("shell-1", command)

    assert gate.decision_for(_payload(tmp_path, all_lines, READY_MESSAGE)) is None


@pytest.mark.parametrize(
    "command",
    [
        "gh pr view 29 --json title,body",
        "gh pr view 290",
        "gh pr view",
        "gh api repos/o/r/pulls/29/reviews",
        "gh api repos/o/r/pulls/290",
        "gh pr checks 29",
        "gh api repos/o/r/pulls/29 --jq .title",
        "gh pr view 29 --json state,title --jq .title",
    ],
)
def test_shell_call_that_returns_no_state_is_denied(tmp_path: Path, command: str) -> None:
    all_lines = [_prompt("go")] + _shell("shell-1", command)

    assert _is_denied(gate.decision_for(_payload(tmp_path, all_lines, READY_MESSAGE)))


def test_view_url_of_another_repository_is_denied_for_a_linked_claim(tmp_path: Path) -> None:
    message_text = "[PR 29](https://github.com/o/r/pull/29) is ready to merge."
    all_lines = [_prompt("go")] + _shell("shell-1", "gh pr view https://github.com/other/repo/pull/29 --json state")

    assert _is_denied(gate.decision_for(_payload(tmp_path, all_lines, message_text)))


def test_view_of_the_linked_repository_passes(tmp_path: Path) -> None:
    message_text = "[PR 29](https://github.com/o/r/pull/29) is ready to merge."
    all_lines = [_prompt("go")] + _shell("shell-1", "gh pr view https://github.com/o/r/pull/29 --json state")

    assert gate.decision_for(_payload(tmp_path, all_lines, message_text)) is None


def test_claim_that_links_another_repository_needs_a_read_of_that_repository(tmp_path: Path) -> None:
    message_text = "[PR 29](https://github.com/other/repo/pull/29) is ready to merge."
    all_lines = [_prompt("go")] + _read("read-1", "get")

    assert _is_denied(gate.decision_for(_payload(tmp_path, all_lines, message_text)))


def test_cross_session_message_is_held_like_a_reply(tmp_path: Path) -> None:
    payload = _payload(tmp_path, _incident_turn(), READY_MESSAGE, tool_name=COORDINATOR_TOOL_NAME)

    assert _is_denied(gate.decision_for(payload))


def test_other_tool_is_not_checked(tmp_path: Path) -> None:
    payload = _payload(tmp_path, _incident_turn(), READY_MESSAGE, tool_name="Write")

    assert gate.decision_for(payload) is None


def test_unreadable_transcript_passes(tmp_path: Path) -> None:
    payload = _payload(tmp_path, _incident_turn(), READY_MESSAGE)
    payload["transcript_path"] = str(tmp_path / "missing.jsonl")

    assert gate.decision_for(payload) is None


@pytest.mark.parametrize(
    ("message_text", "expected_claims"),
    [
        ("PR 29 is ready to merge.", [(29, None)]),
        ("Pull request #29 needs your approval.", [(29, None)]),
        ("#29 is mergeable.", [(29, None)]),
        ("PR 29 is still open.", [(29, None)]),
        ("Queue PR 29.", [(29, None)]),
        ("PR 29 landed. It is ready to merge.", [(29, None)]),
        ("PR 7 and 8 are ready to merge.", [(7, None), (8, None)]),
        ("[PR 7](https://github.com/O/R/pull/7) is open.", [(7, "o/r")]),
        ("PR 29 merged at 13:22 UTC.", []),
        ("PR 29 merged. The build is ready.", []),
        ("PR 29 landed. The PR is ready to merge.", [(29, None)]),
        ("PR 29 was closed.", []),
        ("The build is ready.", []),
        ("PR 29 is not ready to merge.", []),
        ("```\nPR 29 is ready to merge.\n```", []),
    ],
)
def test_claimed_pull_requests_reads_each_status_claim(
    message_text: str, expected_claims: list[tuple[int, str | None]]
) -> None:
    assert gate.claimed_pull_requests(message_text) == expected_claims


def test_hook_script_denies_the_incident_payload_on_stdin(tmp_path: Path) -> None:
    payload = _payload(tmp_path, _incident_turn(), READY_MESSAGE)

    completed = subprocess.run(
        [sys.executable, str(GATE_PATH)], input=json.dumps(payload), capture_output=True, text=True, check=False
    )

    output_fields = json.loads(completed.stdout)
    assert output_fields["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "PR 29" in output_fields["hookSpecificOutput"]["permissionDecisionReason"]

