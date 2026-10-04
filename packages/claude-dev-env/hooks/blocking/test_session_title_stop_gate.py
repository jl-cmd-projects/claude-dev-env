import io
import json
from pathlib import Path

import pytest

import session_title_stop_gate

REMOTE_TITLE_TOOL = "mcp__claude-code-remote__set_session_title"
DESKTOP_TITLE_TOOL = "mcp__ccd_session_mgmt__set_session_title"
REMOTE_SESSION_VARIABLE = "CLAUDE_CODE_REMOTE_SESSION_ID"


def prompt(text: str) -> dict[str, object]:
    return {"type": "user", "message": {"role": "user", "content": text}}


def meta_prompt(text: str) -> dict[str, object]:
    return {
        "type": "user",
        "isMeta": True,
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def tool_call(tool_use_id: str, name: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_use_id, "name": name, "input": {}}],
        },
    }


def tool_result(tool_use_id: str, is_error: bool = False) -> dict[str, object]:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": "ok",
                    "is_error": is_error,
                }
            ],
        },
    }


def deferred_tools(*all_names: str) -> dict[str, object]:
    return {
        "type": "attachment",
        "attachment": {"type": "deferred_tools_delta", "addedNames": list(all_names)},
    }


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_entries: list[dict[str, object]],
    stop_hook_active: bool = False,
) -> tuple[int, str]:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(
        "".join(json.dumps(each) + "\n" for each in all_entries), encoding="utf-8"
    )
    hook_input = {
        "hook_event_name": "Stop",
        "transcript_path": str(transcript_path),
        "stop_hook_active": stop_hook_active,
    }
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = session_title_stop_gate.main()
    return exit_code, capsys.readouterr().out


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv(REMOTE_SESSION_VARIABLE, raising=False)


def test_should_block_a_remote_turn_that_set_no_title(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv(REMOTE_SESSION_VARIABLE, "cse_1")
    exit_code, stdout_text = run_gate(
        monkeypatch,
        capsys,
        tmp_path,
        [prompt("Fix the runner"), tool_call("t1", "Bash"), tool_result("t1")],
    )
    decision = json.loads(stdout_text)
    assert exit_code == 0
    assert decision["decision"] == "block"
    assert REMOTE_TITLE_TOOL in decision["reason"]


def test_should_pass_a_turn_whose_title_call_succeeded(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv(REMOTE_SESSION_VARIABLE, "cse_1")
    all_entries = [prompt("Fix the runner"), tool_call("t1", REMOTE_TITLE_TOOL), tool_result("t1")]
    assert run_gate(monkeypatch, capsys, tmp_path, all_entries) == (0, "")


def test_should_block_when_the_only_title_call_was_denied(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv(REMOTE_SESSION_VARIABLE, "cse_1")
    all_entries = [
        prompt("Fix the runner"),
        tool_call("t1", REMOTE_TITLE_TOOL),
        tool_result("t1", is_error=True),
    ]
    _, stdout_text = run_gate(monkeypatch, capsys, tmp_path, all_entries)
    assert json.loads(stdout_text)["decision"] == "block"


def test_should_block_when_the_title_was_set_only_in_an_earlier_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [
        prompt("Fix the runner"),
        tool_call("t1", DESKTOP_TITLE_TOOL),
        tool_result("t1"),
        prompt("Now open the pull request"),
        tool_call("t2", "Bash"),
        tool_result("t2"),
    ]
    _, stdout_text = run_gate(monkeypatch, capsys, tmp_path, all_entries)
    assert DESKTOP_TITLE_TOOL in json.loads(stdout_text)["reason"]


def test_should_keep_a_title_set_before_a_meta_entry_in_the_same_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv(REMOTE_SESSION_VARIABLE, "cse_1")
    all_entries = [
        prompt("Fix the runner"),
        tool_call("t1", REMOTE_TITLE_TOOL),
        tool_result("t1"),
        meta_prompt("Base directory for this skill: /skills/pr-lifecycle"),
    ]
    assert run_gate(monkeypatch, capsys, tmp_path, all_entries) == (0, "")


def test_should_block_a_desktop_session_once_its_title_tool_is_listed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [deferred_tools("TaskCreate", DESKTOP_TITLE_TOOL), prompt("Fix the runner")]
    _, stdout_text = run_gate(monkeypatch, capsys, tmp_path, all_entries)
    assert DESKTOP_TITLE_TOOL in json.loads(stdout_text)["reason"]


def test_should_stay_silent_in_a_session_with_no_title_tool(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [
        deferred_tools("TaskCreate"),
        prompt("Fix the runner"),
        tool_call("t1", "Bash"),
        tool_result("t1"),
    ]
    assert run_gate(monkeypatch, capsys, tmp_path, all_entries) == (0, "")


def test_should_stay_silent_in_a_remote_session_whose_tool_list_lacks_the_title_tool(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv(REMOTE_SESSION_VARIABLE, "cse_1")
    all_entries = [
        deferred_tools("TaskCreate", "mcp__claude-code-remote__get_session"),
        prompt("Fix the runner"),
        tool_call("t1", "Bash"),
        tool_result("t1"),
    ]
    assert run_gate(monkeypatch, capsys, tmp_path, all_entries) == (0, "")


def test_should_block_a_remote_session_whose_tool_list_names_the_title_tool(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv(REMOTE_SESSION_VARIABLE, "cse_1")
    all_entries = [
        deferred_tools("TaskCreate", REMOTE_TITLE_TOOL),
        prompt("Fix the runner"),
        tool_call("t1", "Bash"),
        tool_result("t1"),
    ]
    _, stdout_text = run_gate(monkeypatch, capsys, tmp_path, all_entries)
    assert json.loads(stdout_text)["decision"] == "block"


def test_should_stay_silent_on_the_retry_after_a_block(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv(REMOTE_SESSION_VARIABLE, "cse_1")
    assert run_gate(
        monkeypatch, capsys, tmp_path, [prompt("Fix the runner")], stop_hook_active=True
    ) == (0, "")


def test_should_stay_silent_when_the_transcript_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv(REMOTE_SESSION_VARIABLE, "cse_1")
    hook_input = {"hook_event_name": "Stop", "transcript_path": str(tmp_path / "absent.jsonl")}
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    assert session_title_stop_gate.main() == 0
    assert capsys.readouterr().out == ""


def test_stop_block_reason_returns_none_after_a_successful_title_call() -> None:
    all_entries = [prompt("Fix the runner"), tool_call("t1", REMOTE_TITLE_TOOL), tool_result("t1")]
    assert session_title_stop_gate.stop_block_reason(all_entries, is_remote_session=True) is None


def test_stop_block_reason_names_the_seen_tool_when_the_turn_has_no_title() -> None:
    all_entries = [
        prompt("Fix the runner"),
        tool_call("t1", DESKTOP_TITLE_TOOL),
        tool_result("t1"),
        prompt("Next"),
    ]
    block_reason = session_title_stop_gate.stop_block_reason(all_entries, is_remote_session=False)
    assert block_reason is not None and DESKTOP_TITLE_TOOL in block_reason
