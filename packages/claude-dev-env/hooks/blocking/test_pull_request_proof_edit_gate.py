"""Behavior tests for the gate that holds an edit to the proof gate until its named route is taken."""

import json
import sys
from pathlib import Path

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import pull_request_proof_edit_gate as gate
from hooks_constants.pull_request_proof_constants import (
    GATE_EDIT_BEFORE_ROUTE_REASON,
    UNREADABLE_CHANGES_REASON,
)


def _transcript(tmp_path: Path, all_entries: list[dict[str, object]]) -> str:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(
        "\n".join(json.dumps(each_entry) for each_entry in all_entries) + "\n", encoding="utf-8"
    )
    return str(transcript_path)


def _tool_use(tool_use_id: object, name: str, tool_input: dict[str, object]) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "id": tool_use_id, "name": name, "input": tool_input}]},
    }


def _tool_result(tool_use_id: object, content: object, is_error: bool) -> dict[str, object]:
    return {
        "type": "user",
        "message": {
            "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id, "content": content, "is_error": is_error}
            ]
        },
    }


SHELL_CREATE_INPUT = {"command": "gh pr create --title t --body-file body.md"}
DENIED_CREATE_ENTRIES = [
    _tool_use("create-1", "Bash", SHELL_CREATE_INPUT),
    _tool_result("create-1", UNREADABLE_CHANGES_REASON, True),
]


def _edit_payload(transcript_path: str, file_path: str) -> dict[str, object]:
    return {
        "tool_name": "Edit",
        "tool_input": {"file_path": file_path, "old_string": "a", "new_string": "b"},
        "transcript_path": transcript_path,
    }


GATE_FILE_PATH = "C:/workspace/x/packages/claude-dev-env/hooks/blocking/pull_request_proof.py"
GATE_CONSTANTS_PATH = "/w/packages/claude-dev-env/hooks/hooks_constants/pull_request_proof_constants.py"


def test_should_deny_an_edit_to_the_gate_after_its_deny_with_no_passing_create(tmp_path: Path) -> None:
    transcript_path = _transcript(tmp_path, DENIED_CREATE_ENTRIES)
    assert gate.gate_edit_reason(_edit_payload(transcript_path, GATE_FILE_PATH)) == GATE_EDIT_BEFORE_ROUTE_REASON


def test_should_deny_an_edit_to_the_gate_constants_after_its_deny(tmp_path: Path) -> None:
    transcript_path = _transcript(tmp_path, DENIED_CREATE_ENTRIES)
    payload = _edit_payload(transcript_path, GATE_CONSTANTS_PATH)
    payload["tool_name"] = "Write"
    assert gate.gate_edit_reason(payload) == GATE_EDIT_BEFORE_ROUTE_REASON


def test_should_read_a_deny_carried_as_text_blocks(tmp_path: Path) -> None:
    all_text_blocks = [{"type": "text", "text": "Error: " + UNREADABLE_CHANGES_REASON}]
    transcript_path = _transcript(
        tmp_path,
        [_tool_use("create-1", "Bash", SHELL_CREATE_INPUT), _tool_result("create-1", all_text_blocks, True)],
    )
    assert gate.gate_edit_reason(_edit_payload(transcript_path, GATE_FILE_PATH)) == GATE_EDIT_BEFORE_ROUTE_REASON


def test_should_allow_a_gate_edit_once_a_later_create_passed(tmp_path: Path) -> None:
    transcript_path = _transcript(
        tmp_path,
        [
            *DENIED_CREATE_ENTRIES,
            _tool_use("create-2", "mcp__github__create_pull_request", {"owner": "o", "repo": "r", "body": "b"}),
            _tool_result("create-2", "https://github.com/o/r/pull/7", False),
        ],
    )
    assert gate.gate_edit_reason(_edit_payload(transcript_path, GATE_FILE_PATH)) is None


def test_should_deny_again_when_a_deny_follows_the_passing_create(tmp_path: Path) -> None:
    transcript_path = _transcript(
        tmp_path,
        [
            _tool_use("create-1", "Bash", SHELL_CREATE_INPUT),
            _tool_result("create-1", "https://github.com/o/r/pull/7", False),
            *DENIED_CREATE_ENTRIES,
        ],
    )
    assert gate.gate_edit_reason(_edit_payload(transcript_path, GATE_FILE_PATH)) == GATE_EDIT_BEFORE_ROUTE_REASON


def test_should_allow_an_edit_to_another_file_after_the_deny(tmp_path: Path) -> None:
    transcript_path = _transcript(tmp_path, DENIED_CREATE_ENTRIES)
    assert gate.gate_edit_reason(_edit_payload(transcript_path, "/w/hooks/blocking/other_gate.py")) is None


def test_should_allow_a_gate_edit_in_a_session_this_gate_never_denied(tmp_path: Path) -> None:
    transcript_path = _transcript(
        tmp_path,
        [
            _tool_use("read-1", "Read", {"file_path": GATE_CONSTANTS_PATH}),
            _tool_result("read-1", UNREADABLE_CHANGES_REASON, False),
            _tool_use("other-1", "Bash", {"command": "pytest"}),
            _tool_result("other-1", "1 failed", True),
        ],
    )
    assert gate.gate_edit_reason(_edit_payload(transcript_path, GATE_FILE_PATH)) is None


def test_should_allow_a_gate_edit_without_a_readable_transcript(tmp_path: Path) -> None:
    payload = _edit_payload(str(tmp_path / "missing.jsonl"), GATE_FILE_PATH)
    assert gate.gate_edit_reason(payload) is None


def test_should_deny_an_apply_patch_to_the_edit_gate_after_its_deny(tmp_path: Path) -> None:
    transcript_path = _transcript(tmp_path, DENIED_CREATE_ENTRIES)
    patch_text = (
        "*** Begin Patch\n*** Update File: hooks/blocking/pull_request_proof_edit_gate.py\n"
        "@@\n-a\n+b\n*** End Patch\n"
    )
    payload = {
        "tool_name": "apply_patch",
        "tool_input": {"command": patch_text},
        "cwd": str(tmp_path),
        "transcript_path": transcript_path,
    }
    assert gate.gate_edit_reason(payload) == GATE_EDIT_BEFORE_ROUTE_REASON


def test_should_ignore_an_errored_result_of_another_tool_that_names_the_guide(tmp_path: Path) -> None:
    transcript_path = _transcript(
        tmp_path,
        [
            _tool_use("cat-1", "Bash", {"command": "cat proof-before-pull-request.md"}),
            _tool_result("cat-1", "cat: " + UNREADABLE_CHANGES_REASON, True),
        ],
    )
    assert gate.gate_edit_reason(_edit_payload(transcript_path, GATE_FILE_PATH)) is None


def test_should_skip_malformed_transcript_entries_and_keep_the_deny(tmp_path: Path) -> None:
    transcript_path = _transcript(
        tmp_path,
        [
            {"type": "user", "message": "plain text"},
            _tool_use(["not", "a", "string"], "Bash", SHELL_CREATE_INPUT),
            _tool_result(["not", "a", "string"], "done", False),
            *DENIED_CREATE_ENTRIES,
        ],
    )
    assert gate.gate_edit_reason(_edit_payload(transcript_path, GATE_FILE_PATH)) == GATE_EDIT_BEFORE_ROUTE_REASON


def test_should_deny_a_multi_edit_of_a_case_variant_windows_path_from_the_agent_transcript(tmp_path: Path) -> None:
    transcript_path = _transcript(tmp_path, DENIED_CREATE_ENTRIES)
    payload = {
        "tool_name": "MultiEdit",
        "tool_input": {"file_path": "C:\\workspace\\x\\hooks\\blocking\\Pull_Request_Proof.PY", "edits": []},
        "agent_transcript_path": transcript_path,
    }
    assert gate.gate_edit_reason(payload) == GATE_EDIT_BEFORE_ROUTE_REASON


def test_should_deny_a_subagent_edit_after_a_deny_in_its_own_transcript(tmp_path: Path) -> None:
    session_path = _transcript(tmp_path, [])
    subagent_directory = tmp_path / "session" / "subagents"
    subagent_directory.mkdir(parents=True)
    (subagent_directory / "agent-a8865a3f3c71595ce.jsonl").write_text(
        "\n".join(json.dumps(each_entry) for each_entry in DENIED_CREATE_ENTRIES) + "\n", encoding="utf-8"
    )
    payload = _edit_payload(session_path, GATE_FILE_PATH)
    payload["agent_id"] = "a8865a3f3c71595ce"
    assert gate.gate_edit_reason(payload) == GATE_EDIT_BEFORE_ROUTE_REASON


def test_should_allow_an_apply_patch_the_patch_parser_cannot_resolve(tmp_path: Path) -> None:
    payload = {
        "tool_name": "apply_patch",
        "tool_input": {"command": "*** Begin Patch\n*** Add File: a\x00b.py\n+x\n*** End Patch\n"},
        "cwd": str(tmp_path),
        "transcript_path": _transcript(tmp_path, DENIED_CREATE_ENTRIES),
    }
    assert gate.gate_edit_reason(payload) is None
