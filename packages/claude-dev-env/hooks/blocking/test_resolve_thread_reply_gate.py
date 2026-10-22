"""Behavior tests for the gate that holds a review thread resolve until a reply posts."""

import json
import subprocess
import sys
from pathlib import Path

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import resolve_thread_reply_gate as gate
from hooks_constants.resolve_thread_reply_gate_constants import MISSING_REPLY_REASON
from transcript_skill_scan import TranscriptToolCall

GATE_PATH = Path(__file__).resolve().parent / "resolve_thread_reply_gate.py"
RESOLVE_TOOL_NAME = "mcp__github__resolve_review_thread"
REPLY_TOOL_NAME = "mcp__github__add_reply_to_pull_request_comment"
HOOK_DENIAL_TEXT = "PreToolUse:mcp__github__add_reply_to_pull_request_comment hook error: too many sentences"


def _prompt(text: str) -> str:
    return json.dumps({"type": "user", "message": {"content": text}})


def _call(tool_use_id: str, tool_name: str, tool_input: dict[str, object] | None = None) -> str:
    tool_use = {"type": "tool_use", "id": tool_use_id, "name": tool_name, "input": tool_input or {}}
    return json.dumps({"type": "assistant", "message": {"content": [tool_use]}})


def _result(tool_use_id: str, is_error: bool = False, text: str = "ok") -> str:
    tool_result = {"type": "tool_result", "tool_use_id": tool_use_id, "is_error": is_error, "content": text}
    return json.dumps({"type": "user", "message": {"content": [tool_result]}})


def _write_transcript(tmp_path: Path, all_lines: list[str]) -> Path:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text("\n".join(all_lines) + "\n", encoding="utf-8")
    return transcript_path


def _resolve_payload(transcript_path: Path) -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": RESOLVE_TOOL_NAME,
        "tool_input": {"threadId": "PRRT_1"},
        "transcript_path": str(transcript_path),
    }


def _deny_reason(decision: dict[str, object] | None) -> str | None:
    if decision is None:
        return None
    hook_output = decision["hookSpecificOutput"]
    assert isinstance(hook_output, dict)
    assert hook_output["permissionDecision"] == "deny"
    return str(hook_output["permissionDecisionReason"])


def should_allow_a_resolve_after_a_reply_that_posted(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            _call("reply-1", REPLY_TOOL_NAME, {"body": "Fixed in `abc1234`."}),
            _result("reply-1"),
            _call("resolve-1", RESOLVE_TOOL_NAME),
        ],
    )
    assert gate.decision_for(_resolve_payload(transcript_path)) is None


def should_deny_a_resolve_after_a_reply_a_hook_refused(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            _call("reply-1", REPLY_TOOL_NAME, {"body": "A long reply."}),
            _result("reply-1", is_error=True, text=HOOK_DENIAL_TEXT),
            _call("resolve-1", RESOLVE_TOOL_NAME),
        ],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_deny_a_resolve_with_no_reply(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [_prompt("Address the review threads."), _call("resolve-1", RESOLVE_TOOL_NAME)],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_deny_a_second_resolve_after_one_reply(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            _call("reply-1", REPLY_TOOL_NAME, {"body": "Fixed in `abc1234`."}),
            _result("reply-1"),
            _call("resolve-1", RESOLVE_TOOL_NAME),
            _result("resolve-1"),
            _call("resolve-2", RESOLVE_TOOL_NAME),
        ],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_deny_a_resolve_whose_reply_came_before_the_last_prompt(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Reply on the thread."),
            _call("reply-1", REPLY_TOOL_NAME, {"body": "Fixed in `abc1234`."}),
            _result("reply-1"),
            _prompt("Now resolve the other thread."),
            _call("resolve-1", RESOLVE_TOOL_NAME),
        ],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_allow_a_retry_after_a_resolve_error(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            _call("reply-1", REPLY_TOOL_NAME, {"body": "Fixed in `abc1234`."}),
            _result("reply-1"),
            _call("resolve-1", RESOLVE_TOOL_NAME),
            _result("resolve-1", is_error=True, text="Bad gateway"),
            _call("resolve-2", RESOLVE_TOOL_NAME),
        ],
    )
    assert gate.decision_for(_resolve_payload(transcript_path)) is None


def should_allow_a_resolve_when_the_transcript_cannot_be_read(tmp_path: Path) -> None:
    assert gate.decision_for(_resolve_payload(tmp_path / "missing.jsonl")) is None


def should_ignore_tools_other_than_a_resolve(tmp_path: Path) -> None:
    transcript_path = _write_transcript(tmp_path, [_prompt("Reply on the thread.")])
    payload = _resolve_payload(transcript_path) | {"tool_name": REPLY_TOOL_NAME}
    assert gate.decision_for(payload) is None


def should_read_a_resolve_tool_from_any_mcp_server() -> None:
    assert gate.is_resolve_call("mcp__github_enterprise__resolve_review_thread")
    assert not gate.is_resolve_call("mcp__github__resolve_review_threads")
    assert not gate.is_resolve_call(None)


def should_count_a_gh_api_reply_command_as_a_reply() -> None:
    reply_command = "gh api repos/o/r/pulls/7/comments/99/replies -f body=Fixed."
    assert gate.is_reply_call(TranscriptToolCall("Bash", {"command": reply_command}, True))
    graphql_command = "gh api graphql -f query='mutation { addPullRequestReviewThreadReply(input: {}) { comment { id } } }'"
    assert gate.is_reply_call(TranscriptToolCall("Bash", {"command": graphql_command}, True))
    assert gate.is_reply_call(TranscriptToolCall(REPLY_TOOL_NAME, {}, True))
    assert not gate.is_reply_call(TranscriptToolCall("mcp__github__add_issue_comment", {}, True))


def should_report_a_posted_reply_from_transcript_lines() -> None:
    all_lines = [_prompt("Go."), _call("reply-1", REPLY_TOOL_NAME), _result("reply-1")]
    assert gate.has_posted_reply_since_last_resolve(all_lines)
    assert not gate.has_posted_reply_since_last_resolve(all_lines[:2])


def should_print_the_deny_when_run_as_a_hook(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [_prompt("Address the review threads."), _call("resolve-1", RESOLVE_TOOL_NAME)],
    )
    completed_process = subprocess.run(
        [sys.executable, str(GATE_PATH)],
        input=json.dumps(_resolve_payload(transcript_path)),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed_process.returncode == 0
    assert _deny_reason(json.loads(completed_process.stdout)) == MISSING_REPLY_REASON
