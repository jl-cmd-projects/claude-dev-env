import io
import json
from pathlib import Path

import pytest

import session_title_turn_gate

REMOTE_TITLE_TOOL = "mcp__claude-code-remote__set_session_title"
DESKTOP_TITLE_TOOL = "mcp__ccd_session_mgmt__set_session_title"
TOOL_LISTING = {
    "type": "attachment",
    "attachment": {
        "type": "prompt_snapshot",
        "tools": [{"name": "Bash"}, {"name": REMOTE_TITLE_TOOL}],
    },
}
DEFERRED_LISTING = {
    "type": "attachment",
    "attachment": {"type": "deferred_tools_delta", "addedNames": [DESKTOP_TITLE_TOOL]},
}
PROMPT = {"type": "user", "message": {"role": "user", "content": "Fix the gate"}}
WORK_CALL = {
    "type": "assistant",
    "message": {"content": [{"type": "tool_use", "id": "w1", "name": "Bash", "input": {}}]},
}
WORK_RESULT = {
    "type": "user",
    "message": {"content": [{"type": "tool_result", "tool_use_id": "w1", "content": "ok"}]},
}
REPLY = {"type": "assistant", "message": {"content": [{"type": "text", "text": "Done."}]}}


def title_call(tool_use_id: str, tool_name: str = REMOTE_TITLE_TOOL) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": tool_name,
                    "input": {"title": "✅ Gate"},
                }
            ]
        },
    }


def title_result(tool_use_id: str, is_error: bool = False) -> dict[str, object]:
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": "ok",
                    "is_error": is_error,
                }
            ]
        },
    }


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_entries: list[dict[str, object]],
    is_stop_hook_active: bool = False,
) -> tuple[int, str]:
    transcript_path = tmp_path / "transcript.jsonl"
    transcript_path.write_text(
        "\n".join(json.dumps(each) for each in all_entries) + "\n", encoding="utf-8"
    )
    hook_input = {
        "hook_event_name": "Stop",
        "stop_hook_active": is_stop_hook_active,
        "transcript_path": str(transcript_path),
    }
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = session_title_turn_gate.main()
    return exit_code, capsys.readouterr().out


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_should_hold_a_turn_that_set_no_title(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exit_code, stdout_text = run_gate(
        monkeypatch, capsys, tmp_path, [TOOL_LISTING, PROMPT, WORK_CALL, WORK_RESULT, REPLY]
    )
    block_output = json.loads(stdout_text)
    assert exit_code == 0
    assert block_output["decision"] == "block"
    assert REMOTE_TITLE_TOOL in block_output["reason"]
    assert all(
        each_emoji in block_output["reason"]
        for each_emoji in ("\U0001f6a9", "\U0001f6a7", "✅", "⏳")
    )


def test_should_pass_a_turn_that_set_a_title(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [
        TOOL_LISTING,
        PROMPT,
        WORK_CALL,
        WORK_RESULT,
        title_call("t1"),
        title_result("t1"),
        REPLY,
    ]
    assert run_gate(monkeypatch, capsys, tmp_path, all_entries) == (0, "")


def test_should_hold_a_turn_whose_title_call_was_denied(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [TOOL_LISTING, PROMPT, title_call("t1"), title_result("t1", is_error=True), REPLY]
    assert (
        json.loads(run_gate(monkeypatch, capsys, tmp_path, all_entries)[1])["decision"] == "block"
    )


def test_should_pass_a_held_turn_whose_title_call_failed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [TOOL_LISTING, PROMPT, title_call("t1"), title_result("t1", is_error=True), REPLY]
    assert run_gate(monkeypatch, capsys, tmp_path, all_entries, is_stop_hook_active=True) == (
        0,
        "",
    )


def test_should_hold_a_held_turn_with_no_title_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [TOOL_LISTING, PROMPT, WORK_CALL, WORK_RESULT, REPLY]
    stdout_text = run_gate(monkeypatch, capsys, tmp_path, all_entries, is_stop_hook_active=True)[1]
    assert json.loads(stdout_text)["decision"] == "block"


def test_should_hold_when_the_title_was_set_only_in_an_earlier_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [
        PROMPT,
        title_call("t1"),
        title_result("t1"),
        REPLY,
        PROMPT,
        WORK_CALL,
        WORK_RESULT,
        REPLY,
    ]
    block_output = json.loads(run_gate(monkeypatch, capsys, tmp_path, all_entries)[1])
    assert block_output["decision"] == "block"


def test_should_start_a_turn_at_an_image_only_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    image_prompt = {
        "type": "user",
        "message": {"content": [{"type": "image", "source": {"type": "base64", "data": ""}}]},
    }
    all_entries = [TOOL_LISTING, PROMPT, title_call("t1"), title_result("t1"), REPLY, image_prompt, REPLY]
    assert json.loads(run_gate(monkeypatch, capsys, tmp_path, all_entries)[1])["decision"] == "block"


def test_should_keep_the_turn_across_a_stop_block_and_a_meta_entry(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    stop_block = {
        "type": "attachment",
        "attachment": {"type": "hook_blocking_error", "hookEvent": "Stop"},
    }
    meta_entry = {"type": "user", "isMeta": True, "message": {"content": "Stop hook feedback"}}
    all_entries = [
        TOOL_LISTING,
        PROMPT,
        title_call("t1"),
        title_result("t1"),
        REPLY,
        stop_block,
        meta_entry,
        REPLY,
    ]
    assert run_gate(monkeypatch, capsys, tmp_path, all_entries) == (0, "")


def test_should_name_a_deferred_title_tool_in_the_reason(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    block_output = json.loads(
        run_gate(monkeypatch, capsys, tmp_path, [DEFERRED_LISTING, PROMPT, REPLY])[1]
    )
    assert DESKTOP_TITLE_TOOL in block_output["reason"]


@pytest.mark.parametrize(
    "all_entries",
    [
        [PROMPT, WORK_CALL, WORK_RESULT, REPLY],
        [
            DEFERRED_LISTING,
            {
                "type": "attachment",
                "attachment": {
                    "type": "deferred_tools_delta",
                    "removedNames": [DESKTOP_TITLE_TOOL],
                },
            },
            PROMPT,
            REPLY,
        ],
    ],
)
def test_should_pass_a_session_without_the_title_tool(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_entries: list[dict[str, object]],
) -> None:
    assert run_gate(monkeypatch, capsys, tmp_path, all_entries) == (0, "")


def test_should_pass_when_the_transcript_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    hook_input = {"hook_event_name": "Stop", "transcript_path": str(tmp_path / "missing.jsonl")}
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    assert (session_title_turn_gate.main(), capsys.readouterr().out) == (0, "")
