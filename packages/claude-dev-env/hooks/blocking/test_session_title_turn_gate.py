import io
import json
from pathlib import Path

import pytest

import session_title_turn_gate
from open_tasks_transcript import TaskItem

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
SESSION_ID = "s-title"
RED_FLAG_TITLE = "\U0001f6a9 Merge approval"
HOURGLASS_TITLE = "\u23f3 Export"
QUESTION_PROMPT = {"type": "user", "message": {"role": "user", "content": "did the export fail?"}}
REPLY = {"type": "assistant", "message": {"content": [{"type": "text", "text": "Done."}]}}


def title_call(
    tool_use_id: str, tool_name: str = REMOTE_TITLE_TOOL, title: str = "✅ Gate"
) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": tool_name,
                    "input": {"title": title},
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
        "session_id": SESSION_ID,
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
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_TASK_LIST_ID", raising=False)


def write_task_store(home_directory: Path, all_statuses: list[str]) -> None:
    task_directory = home_directory / ".claude" / "tasks" / SESSION_ID
    task_directory.mkdir(parents=True)
    for each_number, each_status in enumerate(all_statuses, start=1):
        each_task = {"id": str(each_number), "subject": f"Step {each_number}", "status": each_status}
        (task_directory / f"{each_number}.json").write_text(json.dumps(each_task), encoding="utf-8")


def earlier_turn(title: str) -> list[dict[str, object]]:
    return [TOOL_LISTING, PROMPT, title_call("t0", title=title), title_result("t0"), REPLY]


def block_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_entries: list[dict[str, object]],
) -> str:
    stdout_text = run_gate(monkeypatch, capsys, tmp_path, all_entries)[1]
    return json.loads(stdout_text)["reason"] if stdout_text else ""


def test_should_hold_a_work_turn_in_a_session_with_no_title(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exit_code, stdout_text = run_gate(
        monkeypatch, capsys, tmp_path, [TOOL_LISTING, PROMPT, WORK_CALL, WORK_RESULT, REPLY]
    )
    block_output = json.loads(stdout_text)
    assert exit_code == 0
    assert block_output["decision"] == "block"
    assert "no title yet" in block_output["reason"]
    assert REMOTE_TITLE_TOOL in block_output["reason"]
    assert all(
        each_emoji in block_output["reason"]
        for each_emoji in ("\U0001f6a9", "\U0001f6a7", "✅", "⏳")
    )


def test_should_pass_a_turn_that_set_a_title(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, ["completed"])
    all_entries = [
        TOOL_LISTING,
        PROMPT,
        WORK_CALL,
        WORK_RESULT,
        title_call("t1", title=HOURGLASS_TITLE),
        title_result("t1"),
        REPLY,
    ]
    assert run_gate(monkeypatch, capsys, tmp_path, all_entries) == (0, "")


@pytest.mark.parametrize(
    ("earlier_title", "all_statuses"),
    [
        (HOURGLASS_TITLE, ["completed", "in_progress"]),
        ("✅ Gate", []),
        ("✅ Gate", ["completed"]),
        ("\U0001f6a7 Org secret", ["pending"]),
    ],
)
def test_should_pass_a_work_turn_whose_carried_title_still_fits(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    earlier_title: str,
    all_statuses: list[str],
) -> None:
    if all_statuses:
        write_task_store(tmp_path, all_statuses)
    all_entries = [*earlier_turn(earlier_title), PROMPT, WORK_CALL, WORK_RESULT, REPLY]
    assert run_gate(monkeypatch, capsys, tmp_path, all_entries) == (0, "")


def test_should_hold_a_carried_red_flag_after_a_prompt_that_gives_work(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [*earlier_turn(RED_FLAG_TITLE), PROMPT, WORK_CALL, WORK_RESULT, REPLY]
    reason_text = block_reason(monkeypatch, capsys, tmp_path, all_entries)
    assert RED_FLAG_TITLE in reason_text
    assert "red flag" in reason_text


def test_should_pass_a_carried_red_flag_after_a_question(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [*earlier_turn(RED_FLAG_TITLE), QUESTION_PROMPT, WORK_CALL, WORK_RESULT, REPLY]
    assert run_gate(monkeypatch, capsys, tmp_path, all_entries) == (0, "")


def test_should_hold_a_carried_check_mark_while_items_are_open(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, ["completed", "pending"])
    all_entries = [*earlier_turn("✅ Gate"), QUESTION_PROMPT, WORK_CALL, WORK_RESULT, REPLY]
    assert "open items" in block_reason(monkeypatch, capsys, tmp_path, all_entries)


def test_should_hold_a_carried_hourglass_once_every_item_is_completed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, ["completed", "completed"])
    all_entries = [*earlier_turn(HOURGLASS_TITLE), PROMPT, WORK_CALL, WORK_RESULT, REPLY]
    assert "every task list item is completed" in block_reason(
        monkeypatch, capsys, tmp_path, all_entries
    )


def test_should_pass_a_held_turn_even_with_no_title(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [TOOL_LISTING, PROMPT, WORK_CALL, WORK_RESULT, REPLY]
    assert run_gate(monkeypatch, capsys, tmp_path, all_entries, is_stop_hook_active=True) == (0, "")


def test_should_pass_a_tool_free_turn_with_no_title(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert run_gate(monkeypatch, capsys, tmp_path, [TOOL_LISTING, PROMPT, REPLY]) == (0, "")


def test_should_keep_showing_the_earlier_title_when_this_turns_title_call_was_denied(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [
        *earlier_turn(RED_FLAG_TITLE),
        PROMPT,
        WORK_CALL,
        WORK_RESULT,
        title_call("t1", title="⏳ bad title."),
        title_result("t1", is_error=True),
        REPLY,
    ]
    assert RED_FLAG_TITLE in block_reason(monkeypatch, capsys, tmp_path, all_entries)


def test_should_ignore_a_title_set_on_a_sidechain(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    sidechain_call = {**title_call("s1"), "isSidechain": True}
    sidechain_result = {**title_result("s1"), "isSidechain": True}
    all_entries = [
        TOOL_LISTING,
        PROMPT,
        sidechain_call,
        sidechain_result,
        WORK_CALL,
        WORK_RESULT,
        REPLY,
    ]
    assert "no title yet" in block_reason(monkeypatch, capsys, tmp_path, all_entries)


def test_should_start_a_turn_at_an_image_only_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, ["pending"])
    image_prompt = {
        "type": "user",
        "message": {"content": [{"type": "image", "source": {"type": "base64", "data": ""}}]},
    }
    all_entries = [*earlier_turn("✅ Gate"), image_prompt, WORK_CALL, WORK_RESULT, REPLY]
    assert "open items" in block_reason(monkeypatch, capsys, tmp_path, all_entries)


def test_should_keep_the_turn_across_a_stop_block_and_a_meta_entry(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, ["pending"])
    stop_block = {
        "type": "attachment",
        "attachment": {"type": "hook_blocking_error", "hookEvent": "Stop"},
    }
    meta_entry = {"type": "user", "isMeta": True, "message": {"content": "Stop hook feedback"}}
    all_entries = [
        TOOL_LISTING,
        PROMPT,
        WORK_CALL,
        WORK_RESULT,
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
    all_entries = [DEFERRED_LISTING, PROMPT, WORK_CALL, WORK_RESULT, REPLY]
    assert DESKTOP_TITLE_TOOL in block_reason(monkeypatch, capsys, tmp_path, all_entries)


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
            WORK_CALL,
            WORK_RESULT,
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


def test_should_return_the_last_title_that_came_back_without_an_error() -> None:
    all_entries = [
        title_call("t1", title=HOURGLASS_TITLE),
        title_result("t1"),
        title_call("t2", title=RED_FLAG_TITLE),
        title_result("t2", is_error=True),
    ]
    assert session_title_turn_gate.shown_title(all_entries) == HOURGLASS_TITLE
    assert session_title_turn_gate.shown_title([PROMPT]) is None


@pytest.mark.parametrize(
    ("title", "expected_status"),
    [(RED_FLAG_TITLE, "\U0001f6a9"), ("⏳️ Export", "⏳"), ("Export", None)],
)
def test_should_read_the_status_emoji_without_its_variation_selector(
    title: str, expected_status: str | None
) -> None:
    assert session_title_turn_gate.title_status(title) == expected_status


@pytest.mark.parametrize(
    ("title", "is_ask_turn", "all_statuses", "is_expected_stale"),
    [
        (RED_FLAG_TITLE, True, [], True),
        (RED_FLAG_TITLE, False, [], False),
        ("✅ Gate", False, ["pending"], True),
        ("✅ Gate", True, ["completed"], False),
        ("✅ Gate", True, ["completed", "deleted"], False),
        (HOURGLASS_TITLE, True, ["completed", "deleted"], True),
        (HOURGLASS_TITLE, True, ["completed"], True),
        (HOURGLASS_TITLE, True, ["in_progress"], False),
        (HOURGLASS_TITLE, True, [], False),
    ],
)
def test_should_call_a_status_stale_only_when_the_session_state_contradicts_it(
    title: str, is_ask_turn: bool, all_statuses: list[str], is_expected_stale: bool
) -> None:
    all_items = [
        TaskItem(str(each_number), "Step", each_status)
        for each_number, each_status in enumerate(all_statuses)
    ]
    stale_reason = session_title_turn_gate.stale_status_reason(title, is_ask_turn, all_items)
    assert (stale_reason is not None) is is_expected_stale
    if stale_reason is not None:
        assert title in stale_reason


def test_should_build_the_block_reason_from_the_stale_status() -> None:
    all_entries = [*earlier_turn(RED_FLAG_TITLE), PROMPT, WORK_CALL, WORK_RESULT, REPLY]
    reason_text = session_title_turn_gate.turn_block_reason(all_entries, False, True, [])
    assert reason_text is not None
    assert reason_text.startswith("The title '" + RED_FLAG_TITLE)
    assert session_title_turn_gate.turn_block_reason(all_entries, False, False, []) is None
