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
READ_TOOL_NAME = "mcp__github__pull_request_read"
FIRST_THREAD_ID = "PRRT_kwDOfirst"
SECOND_THREAD_ID = "PRRT_kwDOsecond"
FIRST_COMMENT_ID = 350000001
SECOND_COMMENT_ID = 350000005
HOOK_DENIAL_TEXT = "PreToolUse:mcp__github__add_reply_to_pull_request_comment hook error: too many sentences"


def _prompt(text: str) -> str:
    return json.dumps({"type": "user", "message": {"content": text}})


def _call(tool_use_id: str, tool_name: str, tool_input: dict[str, object] | None = None) -> str:
    tool_use = {"type": "tool_use", "id": tool_use_id, "name": tool_name, "input": tool_input or {}}
    return json.dumps({"type": "assistant", "message": {"content": [tool_use]}})


def _result(tool_use_id: str, is_error: bool = False, text: str = "ok") -> str:
    tool_result = {"type": "tool_result", "tool_use_id": tool_use_id, "is_error": is_error, "content": text}
    return json.dumps({"type": "user", "message": {"content": [tool_result]}})


def _threads_read(tool_use_id: str = "read-1") -> list[str]:
    all_threads = [
        {
            "id": each_thread_id,
            "is_resolved": False,
            "comments": [
                {"path": "a.py", "html_url": f"https://github.com/o/r/pull/7#discussion_r{each_comment_id}"},
                {"path": "a.py", "html_url": f"https://github.com/o/r/pull/7#discussion_r{each_comment_id + 1}"},
            ],
        }
        for each_thread_id, each_comment_id in ((FIRST_THREAD_ID, FIRST_COMMENT_ID), (SECOND_THREAD_ID, SECOND_COMMENT_ID))
    ]
    return [
        _call(tool_use_id, READ_TOOL_NAME, {"method": "get_review_comments", "pullNumber": 7}),
        _result(tool_use_id, text=json.dumps({"review_threads": all_threads, "totalCount": 2})),
    ]


def _reply(tool_use_id: str, comment_id: int = FIRST_COMMENT_ID) -> str:
    return _call(tool_use_id, REPLY_TOOL_NAME, {"commentId": comment_id, "body": "Fixed in `abc1234`."})


def _resolve(tool_use_id: str, thread_id: str = FIRST_THREAD_ID) -> str:
    return _call(tool_use_id, RESOLVE_TOOL_NAME, {"threadID": thread_id})


def _shell_resolve_command(thread_id: str = FIRST_THREAD_ID) -> str:
    return (
        "gh api graphql -f query='mutation { resolveReviewThread(input: {threadId: \""
        + thread_id
        + "\"}) { thread { isResolved } } }'"
    )


def _write_transcript(tmp_path: Path, all_lines: list[str]) -> Path:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text("\n".join(all_lines) + "\n", encoding="utf-8")
    return transcript_path


def _resolve_payload(transcript_path: Path, thread_id: str = FIRST_THREAD_ID) -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": RESOLVE_TOOL_NAME,
        "tool_input": {"threadID": thread_id},
        "transcript_path": str(transcript_path),
    }


def _shell_resolve_payload(transcript_path: Path, command: str) -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
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
            *_threads_read(),
            _reply("reply-1"),
            _result("reply-1"),
            _resolve("resolve-1"),
        ],
    )
    assert gate.decision_for(_resolve_payload(transcript_path)) is None


def should_deny_a_resolve_after_a_reply_a_hook_refused(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            *_threads_read(),
            _reply("reply-1"),
            _result("reply-1", is_error=True, text=HOOK_DENIAL_TEXT),
            _resolve("resolve-1"),
        ],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_deny_a_resolve_with_no_reply(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [_prompt("Address the review threads."), *_threads_read(), _resolve("resolve-1")],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_deny_a_second_resolve_after_one_reply(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            *_threads_read(),
            _reply("reply-1"),
            _result("reply-1"),
            _resolve("resolve-1"),
            _result("resolve-1"),
            _resolve("resolve-2"),
        ],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_allow_a_second_resolve_after_a_reply_on_each_thread(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            *_threads_read(),
            _reply("reply-1"),
            _result("reply-1"),
            _reply("reply-2", SECOND_COMMENT_ID),
            _result("reply-2"),
            _resolve("resolve-1"),
            _result("resolve-1"),
            _resolve("resolve-2", SECOND_THREAD_ID),
        ],
    )
    assert gate.decision_for(_resolve_payload(transcript_path, SECOND_THREAD_ID)) is None


def should_deny_a_resolve_on_a_thread_the_reply_did_not_answer(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            *_threads_read(),
            _reply("reply-1"),
            _result("reply-1"),
            _resolve("resolve-1", SECOND_THREAD_ID),
        ],
    )
    decision = gate.decision_for(_resolve_payload(transcript_path, SECOND_THREAD_ID))
    assert _deny_reason(decision) == MISSING_REPLY_REASON


def should_deny_a_second_resolve_of_one_thread_after_replies_on_two_threads(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            *_threads_read(),
            _reply("reply-1"),
            _result("reply-1"),
            _reply("reply-2", SECOND_COMMENT_ID),
            _result("reply-2"),
            _resolve("resolve-1"),
            _result("resolve-1"),
            _resolve("resolve-2"),
        ],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_match_a_reply_on_a_later_comment_in_the_thread(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            *_threads_read(),
            _reply("reply-1", SECOND_COMMENT_ID + 1),
            _result("reply-1"),
            _resolve("resolve-1", SECOND_THREAD_ID),
        ],
    )
    assert gate.decision_for(_resolve_payload(transcript_path, SECOND_THREAD_ID)) is None


def should_read_the_thread_map_from_before_the_last_prompt(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("List the review threads."),
            *_threads_read(),
            _prompt("Reply and resolve."),
            _reply("reply-1"),
            _result("reply-1"),
            _resolve("resolve-1"),
        ],
    )
    assert gate.decision_for(_resolve_payload(transcript_path)) is None


def should_deny_a_resolve_when_no_read_ties_the_reply_to_the_thread(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            _reply("reply-1"),
            _result("reply-1"),
            _resolve("resolve-1"),
        ],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_allow_a_resolve_after_a_graphql_reply_on_the_thread(tmp_path: Path) -> None:
    reply_command = (
        "gh api graphql -f query='mutation { addPullRequestReviewThreadReply(input: "
        f'{{pullRequestReviewThreadId: "{FIRST_THREAD_ID}", body: "Fixed."}}) {{ comment {{ id }} }} }}\''
    )
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            _call("reply-1", "Bash", {"command": reply_command}),
            _result("reply-1"),
            _resolve("resolve-1"),
        ],
    )
    assert gate.decision_for(_resolve_payload(transcript_path)) is None


def should_deny_a_shell_resolve_with_no_reply(tmp_path: Path) -> None:
    transcript_path = _write_transcript(tmp_path, [_prompt("Address the review threads."), *_threads_read()])
    decision = gate.decision_for(_shell_resolve_payload(transcript_path, _shell_resolve_command()))
    assert _deny_reason(decision) == MISSING_REPLY_REASON


def should_allow_a_shell_resolve_after_a_rest_reply_on_the_thread(tmp_path: Path) -> None:
    reply_command = f"gh api repos/o/r/pulls/7/comments/{FIRST_COMMENT_ID}/replies -f body=Fixed."
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            *_threads_read(),
            _call("reply-1", "Bash", {"command": reply_command}),
            _result("reply-1"),
        ],
    )
    assert gate.decision_for(_shell_resolve_payload(transcript_path, _shell_resolve_command())) is None


def should_deny_a_shell_resolve_on_a_thread_the_reply_did_not_answer(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [_prompt("Address the review threads."), *_threads_read(), _reply("reply-1"), _result("reply-1")],
    )
    decision = gate.decision_for(_shell_resolve_payload(transcript_path, _shell_resolve_command(SECOND_THREAD_ID)))
    assert _deny_reason(decision) == MISSING_REPLY_REASON


def should_deny_a_shell_resolve_that_names_no_thread_id(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [_prompt("Address the review threads."), *_threads_read(), _reply("reply-1"), _result("reply-1")],
    )
    command = "gh api graphql -f threadId=\"$thread\" -f query='mutation($threadId: ID!) { resolveReviewThread(input: {threadId: $threadId}) { thread { isResolved } } }'"
    assert _deny_reason(gate.decision_for(_shell_resolve_payload(transcript_path, command))) == MISSING_REPLY_REASON


def should_spend_the_reply_on_a_shell_resolve(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            *_threads_read(),
            _reply("reply-1"),
            _result("reply-1"),
            _call("resolve-1", "Bash", {"command": _shell_resolve_command()}),
            _result("resolve-1"),
            _resolve("resolve-2"),
        ],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def _ccr_resolve_command(comment_id: int = FIRST_COMMENT_ID) -> str:
    return f"gh api -X POST repos/o/r/pulls/7/ccr/comments/{comment_id}/resolve"


def should_deny_a_ccr_resolve_with_no_reply(tmp_path: Path) -> None:
    transcript_path = _write_transcript(tmp_path, [_prompt("Address the review threads.")])
    decision = gate.decision_for(_shell_resolve_payload(transcript_path, _ccr_resolve_command()))
    assert _deny_reason(decision) == MISSING_REPLY_REASON


def should_allow_a_ccr_resolve_of_the_comment_the_reply_answered(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [_prompt("Address the review threads."), _reply("reply-1"), _result("reply-1")],
    )
    assert gate.decision_for(_shell_resolve_payload(transcript_path, _ccr_resolve_command())) is None


def should_deny_a_ccr_resolve_of_a_comment_in_another_thread(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [_prompt("Address the review threads."), *_threads_read(), _reply("reply-1"), _result("reply-1")],
    )
    decision = gate.decision_for(_shell_resolve_payload(transcript_path, _ccr_resolve_command(SECOND_COMMENT_ID)))
    assert _deny_reason(decision) == MISSING_REPLY_REASON


def should_spend_the_reply_on_a_ccr_resolve_of_the_same_thread(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            *_threads_read(),
            _reply("reply-1"),
            _result("reply-1"),
            _call("resolve-1", "Bash", {"command": _ccr_resolve_command(FIRST_COMMENT_ID + 1)}),
            _result("resolve-1"),
            _resolve("resolve-2"),
        ],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_ignore_shell_commands_other_than_a_resolve(tmp_path: Path) -> None:
    transcript_path = _write_transcript(tmp_path, [_prompt("Address the review threads.")])
    assert gate.decision_for(_shell_resolve_payload(transcript_path, "gh pr view 7")) is None
    unresolve_command = _shell_resolve_command().replace("resolveReviewThread", "unresolveReviewThread")
    assert gate.decision_for(_shell_resolve_payload(transcript_path, unresolve_command)) is None
    ccr_unresolve_command = _ccr_resolve_command().replace("/resolve", "/unresolve")
    assert gate.decision_for(_shell_resolve_payload(transcript_path, ccr_unresolve_command)) is None


def should_deny_a_resolve_whose_reply_came_before_the_last_prompt(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Reply on the thread."),
            *_threads_read(),
            _reply("reply-1"),
            _result("reply-1"),
            _prompt("Now resolve the thread."),
            _resolve("resolve-1"),
        ],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_allow_a_retry_after_a_resolve_error(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            *_threads_read(),
            _reply("reply-1"),
            _result("reply-1"),
            _resolve("resolve-1"),
            _result("resolve-1", is_error=True, text="Bad gateway"),
            _resolve("resolve-2"),
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


def should_name_the_threads_a_call_resolves() -> None:
    assert gate.resolved_thread_ids(RESOLVE_TOOL_NAME, {"threadID": FIRST_THREAD_ID}) == {FIRST_THREAD_ID}
    assert gate.resolved_thread_ids(RESOLVE_TOOL_NAME, {"threadId": FIRST_THREAD_ID}) == {FIRST_THREAD_ID}
    assert gate.resolved_thread_ids("Bash", {"command": _shell_resolve_command()}) == {FIRST_THREAD_ID}
    assert gate.resolved_thread_ids("PowerShell", {"command": _shell_resolve_command()}) == {FIRST_THREAD_ID}
    assert gate.resolved_thread_ids("Bash", {"command": _ccr_resolve_command()}) == {str(FIRST_COMMENT_ID)}
    assert gate.resolved_thread_ids("Bash", {"command": "gh pr view 7"}) is None
    assert gate.resolved_thread_ids(REPLY_TOOL_NAME, {"commentId": FIRST_COMMENT_ID}) is None


def should_map_comment_ids_to_threads_from_tool_results() -> None:
    graphql_text = json.dumps(
        {"nodes": [{"id": SECOND_THREAD_ID, "comments": {"nodes": [{"databaseId": SECOND_COMMENT_ID}]}}]}
    )
    graphql_result = json.dumps(
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "read-2", "content": [{"type": "text", "text": graphql_text}]}
                ]
            },
        }
    )
    refused_text = json.dumps({"id": SECOND_THREAD_ID, "html_url": "x#discussion_r1"})
    thread_id_by_comment_id = gate.thread_ids_by_comment_id(
        [*_threads_read(), graphql_result, _result("read-3", is_error=True, text=refused_text), "not json"]
    )
    assert thread_id_by_comment_id[str(FIRST_COMMENT_ID)] == FIRST_THREAD_ID
    assert thread_id_by_comment_id[str(FIRST_COMMENT_ID + 1)] == FIRST_THREAD_ID
    assert thread_id_by_comment_id[str(SECOND_COMMENT_ID)] == SECOND_THREAD_ID
    assert "1" not in thread_id_by_comment_id


def should_report_a_posted_reply_from_transcript_lines() -> None:
    all_lines = [_prompt("Go."), *_threads_read(), _reply("reply-1"), _result("reply-1")]
    assert gate.has_posted_reply_on_threads(all_lines, frozenset({FIRST_THREAD_ID}))
    assert not gate.has_posted_reply_on_threads(all_lines, frozenset({SECOND_THREAD_ID}))
    assert not gate.has_posted_reply_on_threads(all_lines[:-1], frozenset({FIRST_THREAD_ID}))
    assert not gate.has_posted_reply_on_threads(all_lines, frozenset())


def should_print_the_deny_when_run_as_a_hook(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [_prompt("Address the review threads."), _resolve("resolve-1")],
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


def _review_write_payload(transcript_path: Path, method: str, thread_id: str = FIRST_THREAD_ID) -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "mcp__github__pull_request_review_write",
        "tool_input": {"method": method, "threadId": thread_id, "owner": "o", "repo": "r", "pullNumber": 7},
        "transcript_path": str(transcript_path),
    }


def should_deny_a_review_write_resolve_with_no_reply(tmp_path: Path) -> None:
    transcript_path = _write_transcript(tmp_path, [_prompt("Address the review threads.")])
    decision = gate.decision_for(_review_write_payload(transcript_path, "resolve_thread"))
    assert _deny_reason(decision) == MISSING_REPLY_REASON


def should_allow_a_review_write_resolve_after_a_reply_on_that_thread(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [_prompt("Address the review threads."), *_threads_read(), _reply("reply-1"), _result("reply-1")],
    )
    assert gate.decision_for(_review_write_payload(transcript_path, "resolve_thread")) is None


def should_leave_a_review_write_that_submits_a_review_alone(tmp_path: Path) -> None:
    transcript_path = _write_transcript(tmp_path, [_prompt("Review the pull request.")])
    assert gate.decision_for(_review_write_payload(transcript_path, "create")) is None


REPLY_SCRIPT_COMMAND = (
    f"python .github/ci/review_reply_post.py request --pull 7 --comment-id {FIRST_COMMENT_ID}"
    f" --thread-id {FIRST_THREAD_ID} --body-file reply.md"
)


def _script_reply(tool_use_id: str, command: str = REPLY_SCRIPT_COMMAND, is_background: bool = False) -> str:
    tool_input: dict[str, object] = {"command": command}
    if is_background:
        tool_input["run_in_background"] = True
    return _call(tool_use_id, "Bash", tool_input)


def _task_notice(tool_use_id: str, exit_code: int = 0) -> str:
    status = "completed" if exit_code == 0 else "failed"
    text = (
        f"<task-notification>\n<task-id>b1</task-id>\n<tool-use-id>{tool_use_id}</tool-use-id>\n"
        f"<status>{status}</status>\n<summary>Background command {status} (exit code {exit_code})</summary>\n"
        "</task-notification>"
    )
    return json.dumps({"type": "user", "origin": {"kind": "task-notification"}, "message": {"content": text}})


def should_allow_a_resolve_after_the_reply_script_posted(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            _script_reply("reply-1"),
            _result("reply-1", text="already posted https://github.com/o/r/pull/7#discussion_r1"),
        ],
    )
    assert gate.decision_for(_resolve_payload(transcript_path)) is None


def should_allow_a_comment_id_resolve_after_the_reply_script_named_no_thread(tmp_path: Path) -> None:
    command = f"python review_reply_post.py request --pull 7 --comment-id={FIRST_COMMENT_ID} --body-file reply.md"
    transcript_path = _write_transcript(
        tmp_path,
        [_prompt("Address the review threads."), *_threads_read(), _script_reply("reply-1", command), _result("reply-1")],
    )
    assert gate.decision_for(_resolve_payload(transcript_path)) is None
    resolve_command = f"gh api -X POST repos/o/r/pulls/7/ccr/comments/{FIRST_COMMENT_ID}/resolve"
    assert gate.decision_for(_shell_resolve_payload(transcript_path, resolve_command)) is None


def should_deny_a_resolve_when_the_reply_script_did_not_post(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            _script_reply("reply-1"),
            _result("reply-1", is_error=True, text="not posted"),
        ],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_deny_a_resolve_of_another_thread_after_the_reply_script(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [_prompt("Address the review threads."), *_threads_read(), _script_reply("reply-1"), _result("reply-1")],
    )
    decision = gate.decision_for(_resolve_payload(transcript_path, SECOND_THREAD_ID))
    assert _deny_reason(decision) == MISSING_REPLY_REASON


def should_deny_a_resolve_after_a_script_call_that_requests_no_reply(tmp_path: Path) -> None:
    all_commands = [
        f"python review_reply_post.py post --request review-reply.json --branch b --sender s # {FIRST_THREAD_ID}",
        f"cat review_reply_post.py; echo request --comment-id {FIRST_COMMENT_ID} {FIRST_THREAD_ID}",
        f"python review_reply_post.py request --help; echo {FIRST_THREAD_ID}",
    ]
    for each_command in all_commands:
        transcript_path = _write_transcript(
            tmp_path,
            [_prompt("Address the review threads."), _script_reply("reply-1", each_command), _result("reply-1")],
        )
        assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_allow_a_resolve_after_a_background_reply_script_exits_zero(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            _script_reply("reply-1", is_background=True),
            _result("reply-1", text="Command running in background with ID: b1"),
            _task_notice("reply-1"),
        ],
    )
    assert gate.decision_for(_resolve_payload(transcript_path)) is None


def should_deny_a_resolve_while_a_background_reply_script_still_runs(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            _script_reply("reply-1", is_background=True),
            _result("reply-1", text="Command running in background with ID: b1"),
        ],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_deny_a_resolve_after_a_background_reply_script_fails(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            _script_reply("reply-1", is_background=True),
            _result("reply-1", text="Command running in background with ID: b1"),
            _task_notice("reply-1", exit_code=3),
            _task_notice("another-call"),
        ],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_keep_a_posted_reply_across_a_background_task_notice(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            *_threads_read(),
            _reply("reply-1"),
            _result("reply-1"),
            _task_notice("another-call"),
        ],
    )
    assert gate.decision_for(_resolve_payload(transcript_path)) is None


def should_credit_only_the_thread_the_reply_script_names_as_its_own_argument(tmp_path: Path) -> None:
    command = (
        f"python review_reply_post.py request --pull 7 --comment-id {FIRST_COMMENT_ID}"
        f" --thread-id {FIRST_THREAD_ID} --body-file {SECOND_THREAD_ID}.md"
    )
    transcript_path = _write_transcript(
        tmp_path, [_prompt("Address the review threads."), _script_reply("reply-1", command), _result("reply-1")]
    )
    assert gate.decision_for(_resolve_payload(transcript_path)) is None
    decision = gate.decision_for(_resolve_payload(transcript_path, SECOND_THREAD_ID))
    assert _deny_reason(decision) == MISSING_REPLY_REASON


def should_not_count_a_reply_script_call_the_parser_can_read_another_way() -> None:
    plain_call = (
        f"python3 .github/ci/review_reply_post.py request --pull 7 --comment-id {FIRST_COMMENT_ID}"
        f" --thread-id {FIRST_THREAD_ID} --body-file reply.md"
    )
    assert gate.reply_script_targets(plain_call) == (frozenset({FIRST_THREAD_ID}), frozenset({str(FIRST_COMMENT_ID)}))
    assert gate.reply_script_targets(plain_call + " --wait-seconds 30 --supersede") is not None
    assert gate.reply_script_targets("/usr/bin/" + plain_call) is not None
    all_misread_commands = [
        f"{plain_call} --he",
        f"{plain_call} --h",
        f"{plain_call} --hel",
        f"{plain_call} --hel{{p,p}}",
        f"{plain_call} {{--help,--help}}",
        f"{plain_call} --comment {SECOND_COMMENT_ID}",
        f"{plain_call} --comment-i={SECOND_COMMENT_ID}",
        f"{plain_call} --c {SECOND_COMMENT_ID}",
        f"{plain_call} --thread {SECOND_THREAD_ID}",
        f"{plain_call} --thread-i={SECOND_THREAD_ID}",
        f"{plain_call} --comment-id {SECOND_COMMENT_ID}",
        f"{plain_call} --thread-id={SECOND_THREAD_ID}",
        f"{plain_call} --supersede --supersede",
        f"{plain_call} --supersede=1",
        f"{plain_call} --unknown 1",
        f"{plain_call} extra",
        f"{plain_call} --wait-seconds -1",
        f"{plain_call} --wait-seconds",
        f"{plain_call} --wait-seconds=",
        f"{plain_call} --body-file repl?.md",
        f"{plain_call} --body-file ~/reply.md",
        f"{plain_call} --body-file reply[1].md",
        f"{plain_call} --body-file reply\\ one.md",
        "python3 review_reply_post.py request --pull 7 --thread-id not-a-thread --comment-id 9",
        f"./{plain_call}",
        f"bin/{plain_call}",
        "python3 -u review_reply_post.py request --comment-id 9",
        "py -3 review_reply_post.py request --comment-id 9",
        ".venv/bin/python review_reply_post.py request --comment-id 9",
        "python2 review_reply_post.py request --comment-id 9",
        "python3.12x review_reply_post.py request --comment-id 9",
        "pythonw.exe review_reply_post.py request --comment-id 9",
        "python review_reply_post.py request --comment-id 9 --body-file 'reply (1).md'",
        "uv run review_reply_post.py request --comment-id 9",
        "~/bin/python3 review_reply_post.py request --comment-id 9",
    ]
    for each_command in all_misread_commands:
        assert gate.reply_script_targets(each_command) is None, each_command


def should_not_count_a_reply_script_whose_exit_code_the_command_can_hide() -> None:
    plain_call = f"python .github/ci/review_reply_post.py request --pull 7 --comment-id {FIRST_COMMENT_ID}"
    assert gate.reply_script_targets(plain_call) is not None
    all_masked_commands = [
        f"{plain_call} || true",
        f"{plain_call}; true",
        f"{plain_call} | cat",
        f"({plain_call}) || true",
        f"{plain_call} &",
        f"{plain_call} > out.txt",
        f"{plain_call}\ntrue",
        f"echo $({plain_call})",
        f"{plain_call} --thread-id $THREAD",
        f"{plain_call} # --comment-id {SECOND_COMMENT_ID}",
        f"{plain_call} --help",
        f"{plain_call} -h",
        f"echo {plain_call}",
        f"env X=1 {plain_call}",
        f"python -c pass review_reply_post.py request --comment-id {FIRST_COMMENT_ID}",
        "python review_reply_post.py request --comment-id abc",
        "python review_reply_post.py request --pull 7",
        f"python review_reply_post.py post --comment-id {FIRST_COMMENT_ID}",
        f"python other_review_reply_post.py request --comment-id {FIRST_COMMENT_ID}",
        f"python review_reply_post.py request --comment-id '{FIRST_COMMENT_ID}",
    ]
    for each_command in all_masked_commands:
        assert gate.reply_script_targets(each_command) is None, each_command


def should_deny_a_resolve_after_a_masked_reply_script_call(tmp_path: Path) -> None:
    transcript_path = _write_transcript(
        tmp_path,
        [
            _prompt("Address the review threads."),
            _script_reply("reply-1", REPLY_SCRIPT_COMMAND + " || true"),
            _result("reply-1"),
        ],
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def _raw_notice(text: str) -> str:
    return json.dumps({"type": "user", "origin": {"kind": "task-notification"}, "message": {"content": text}})


def should_deny_a_resolve_when_a_failed_notice_carries_a_passing_one(tmp_path: Path) -> None:
    passing_block = (
        "<task-notification><tool-use-id>other</tool-use-id><status>completed</status>"
        "<summary>Background command completed (exit code 0)</summary></task-notification>"
    )
    failed_block = (
        "<task-notification><tool-use-id>reply-1</tool-use-id><status>failed</status>"
        "<summary>Background command failed (exit code 3)</summary></task-notification>"
    )
    quoting_summary = (
        "<task-notification><tool-use-id>reply-1</tool-use-id><status>failed</status>"
        '<summary>Background command "post (exit code 0)</summary></task-notification>'
        "<task-notification><tool-use-id>reply-1</tool-use-id><status>completed</status>"
        '<summary>(exit code 0)" failed (exit code 3)</summary></task-notification>'
    )
    quoted_status = (
        "<task-notification><tool-use-id>reply-1</tool-use-id><status>failed</status>"
        '<summary>Background command "<status>completed</status> (exit code 0)" failed (exit code 3)</summary>'
        "</task-notification>"
    )
    for each_text in (passing_block + failed_block, failed_block + passing_block, quoting_summary, quoted_status):
        transcript_path = _write_transcript(
            tmp_path,
            [
                _prompt("Address the review threads."),
                _script_reply("reply-1", is_background=True),
                _result("reply-1", text="Command running in background with ID: b1"),
                _raw_notice(each_text),
            ],
        )
        assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON, each_text


BACKGROUND_STARTED_TEXT = "Command running in background with ID: b1"


def _queued_command(text: str, origin_kind: str, command_mode: str) -> str:
    return json.dumps(
        {
            "parentUuid": "00000000-0000-4000-8000-000000000001",
            "isSidechain": False,
            "attachment": {
                "type": "queued_command",
                "prompt": text,
                "source_uuid": "00000000-0000-4000-8000-000000000002",
                "delivery_id": "00000000-0000-4000-8000-000000000003",
                "commandMode": command_mode,
                "origin": {"kind": origin_kind},
                "timestamp": "2026-01-01T00:00:00.000Z",
            },
            "type": "attachment",
            "uuid": "00000000-0000-4000-8000-000000000004",
            "timestamp": "2026-01-01T00:00:00.000Z",
            "rendered": [{"content": text}],
            "renderedRole": "system",
        }
    )


def _notice_text(tool_use_id: str, status: str = "completed", exit_code: int = 0) -> str:
    return (
        f"<task-notification>\n<task-id>b1</task-id>\n<tool-use-id>{tool_use_id}</tool-use-id>\n"
        f"<output-file>/tmp/b1.output</output-file>\n<status>{status}</status>\n"
        f'<summary>Background command "Post the reply" {status} (exit code {exit_code})</summary>\n'
        "</task-notification>"
    )


def _background_reply(run_in_background: object = True) -> list[str]:
    return [
        _call("reply-1", "Bash", {"command": REPLY_SCRIPT_COMMAND, "run_in_background": run_in_background}),
        _result("reply-1", text=BACKGROUND_STARTED_TEXT),
    ]


def should_allow_a_resolve_after_a_notice_queued_mid_turn_reports_exit_code_zero(tmp_path: Path) -> None:
    all_lines = [_prompt("Address the review threads."), *_background_reply()]
    queued_notice = _queued_command(_notice_text("reply-1"), "task-notification", "task-notification")
    transcript_path = _write_transcript(tmp_path, [*all_lines, queued_notice])
    assert gate.decision_for(_resolve_payload(transcript_path)) is None
    for each_notice_text in (
        _notice_text("reply-1", "failed", 3),
        _notice_text("another-call"),
        _notice_text("another-call") + _notice_text("reply-1", "failed", 3),
    ):
        queued_notice = _queued_command(each_notice_text, "task-notification", "task-notification")
        transcript_path = _write_transcript(tmp_path, [*all_lines, queued_notice])
        assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_deny_a_resolve_after_a_prompt_the_user_queued_mid_turn(tmp_path: Path) -> None:
    all_lines = [_prompt("Address the review threads."), *_threads_read(), _reply("reply-1"), _result("reply-1")]
    transcript_path = _write_transcript(tmp_path, all_lines)
    assert gate.decision_for(_resolve_payload(transcript_path)) is None
    for each_origin_kind in ("human", "peer"):
        queued_prompt = _queued_command("Stop, leave the threads open.", each_origin_kind, "prompt")
        transcript_path = _write_transcript(tmp_path, [*all_lines, queued_prompt])
        assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_wait_for_the_notice_whatever_truthy_value_the_background_flag_holds(tmp_path: Path) -> None:
    for each_flag in ("true", 1):
        all_lines = [_prompt("Address the review threads."), *_background_reply(each_flag)]
        transcript_path = _write_transcript(tmp_path, all_lines)
        assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON
        transcript_path = _write_transcript(tmp_path, [*all_lines, _task_notice("reply-1")])
        assert gate.decision_for(_resolve_payload(transcript_path)) is None


def should_wait_for_the_notice_when_a_result_says_the_call_moved_to_the_background(tmp_path: Path) -> None:
    for each_result_text in (
        "Command was manually backgrounded by user with ID: b1",
        "partial output\nCommand did not complete within its 120s timeout and was moved to the background (ID: b1).",
    ):
        all_lines = [
            _prompt("Address the review threads."),
            _script_reply("reply-1"),
            _result("reply-1", text=each_result_text),
        ]
        transcript_path = _write_transcript(tmp_path, all_lines)
        assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON
        transcript_path = _write_transcript(tmp_path, [*all_lines, _raw_notice(_notice_text("reply-1"))])
        assert gate.decision_for(_resolve_payload(transcript_path)) is None


def should_deny_a_resolve_when_a_notice_appends_exit_code_zero_after_a_failure(tmp_path: Path) -> None:
    appended_text = (
        "<task-notification>\n<tool-use-id>reply-1</tool-use-id>\n<status>completed</status>\n"
        '<summary>Background command "d" failed (exit code 3) (exit code 0)</summary>\n</task-notification>'
    )
    transcript_path = _write_transcript(
        tmp_path, [_prompt("Address the review threads."), *_background_reply(), _raw_notice(appended_text)]
    )
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_read_a_versioned_or_exe_launcher_and_a_bare_script_path() -> None:
    all_plain_commands = [
        "python3.12 review_reply_post.py request --comment-id 9",
        "python.exe review_reply_post.py request --comment-id 9",
        "py.exe ci/review_reply_post.py request --comment-id 9",
        "/usr/bin/python3.13 review_reply_post.py request --comment-id 9",
        "ci/review_reply_post.py request --comment-id 9",
    ]
    for each_command in all_plain_commands:
        assert gate.reply_script_targets(each_command) == (frozenset(), frozenset({"9"})), each_command


BACKGROUND_WORDS_IN_A_BODY = (
    "Command running in background with ID: b1\nThe job is backgrounded and running in the background."
)


def should_count_a_reply_tool_whose_result_quotes_the_background_words(tmp_path: Path) -> None:
    all_lines = [
        _prompt("Address the review threads."),
        *_threads_read(),
        _reply("reply-1"),
        _result("reply-1", text=BACKGROUND_WORDS_IN_A_BODY),
    ]
    assert gate.decision_for(_resolve_payload(_write_transcript(tmp_path, all_lines))) is None


def should_spend_the_reply_when_a_resolve_result_quotes_the_background_words(tmp_path: Path) -> None:
    all_lines = [
        _prompt("Address the review threads."),
        *_threads_read(),
        _reply("reply-1"),
        _result("reply-1"),
        _resolve("resolve-1"),
        _result("resolve-1", text=BACKGROUND_WORDS_IN_A_BODY),
    ]
    transcript_path = _write_transcript(tmp_path, all_lines)
    assert _deny_reason(gate.decision_for(_resolve_payload(transcript_path))) == MISSING_REPLY_REASON


def should_count_a_shell_reply_whose_output_mentions_the_background_mid_line(tmp_path: Path) -> None:
    all_lines = [
        _prompt("Address the review threads."),
        _script_reply("reply-1"),
        _result("reply-1", text="posted: the job is backgrounded and running in the background"),
    ]
    assert gate.decision_for(_resolve_payload(_write_transcript(tmp_path, all_lines))) is None
