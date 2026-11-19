import io
import json
import tempfile
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import closing_question_round_gate
from closing_question_round_tasks import SessionTasks
from open_tasks_transcript import TaskItem
from hooks_constants.closing_question_round_gate_constants import (
    CLOSING_ROUND_REASON_LEAD,
    FOOTER_GAP_REASON_LEAD,
    FOOTER_MISSING_REASON_LEAD,
    IN_PROGRESS_TASKS_REASON_LEAD,
    MAXIMUM_QUOTED_LINE_COUNT,
    MAXIMUM_QUOTED_LINE_LENGTH,
)

GATE_PATH = Path(closing_question_round_gate.__file__)
SESSION_ID = "s-123"
DEFERRAL_LINE = "I deferred the backoff setting to a later change."
FEEDBACK_TEXT = f'Stop hook feedback:\n{CLOSING_ROUND_REASON_LEAD}\nThe lines:\n"{DEFERRAL_LINE}"'


@pytest.fixture(autouse=True)
def interactive_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "1")


def typed_prompt_record(
    prompt_text: str = "Add the retry flag to the export job.",
) -> dict[str, object]:
    return {
        "type": "user",
        "turnOrigin": "human",
        "promptSource": "typed",
        "message": {"role": "user", "content": prompt_text},
    }


def machine_prompt_record(
    turn_origin: str, prompt_text: str = "Add the retry flag."
) -> dict[str, object]:
    return {
        "type": "user",
        "turnOrigin": turn_origin,
        "promptSource": "system",
        "message": {"role": "user", "content": prompt_text},
    }


def reply_record(reply_text: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": reply_text}]},
    }


def tool_call_record(
    tool_name: object,
    all_input_fields: dict[str, object] | None = None,
    tool_use_id: str | None = None,
) -> dict[str, object]:
    tool_use = {
        "type": "tool_use",
        "id": tool_use_id or f"id-{tool_name}",
        "name": tool_name,
        "input": all_input_fields or {},
    }
    return {"type": "assistant", "message": {"role": "assistant", "content": [tool_use]}}


def tool_result_record(
    tool_name: str, result_text: str, is_error: bool = False, tool_use_id: str | None = None
) -> dict[str, object]:
    tool_result = {
        "type": "tool_result",
        "tool_use_id": tool_use_id or f"id-{tool_name}",
        "content": result_text,
        "is_error": is_error,
    }
    return {"type": "user", "message": {"role": "user", "content": [tool_result]}}


def stop_feedback_record(feedback_text: str = FEEDBACK_TEXT) -> dict[str, object]:
    return {"type": "user", "isMeta": True, "message": {"role": "user", "content": feedback_text}}


def write_records(transcript_path: Path, all_records: list[dict[str, object]]) -> Path:
    transcript_path.write_text(
        "\n".join(json.dumps(each_record) for each_record in all_records), encoding="utf-8"
    )
    return transcript_path


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    transcript_path: Path | None,
    all_extra_fields: dict[str, object] | None = None,
) -> dict[str, str]:
    hook_input: dict[str, object] = {
        "hook_event_name": "Stop",
        "session_id": SESSION_ID,
        "stop_hook_active": False,
        **(all_extra_fields or {}),
    }
    if transcript_path is not None:
        hook_input["transcript_path"] = str(transcript_path)
        monkeypatch.setattr(tempfile, "tempdir", str(transcript_path.parent))
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = closing_question_round_gate.main()
    captured = capsys.readouterr()
    block_output = json.loads(captured.out) if captured.out else {}
    assert exit_code == (2 if block_output else 0)
    assert captured.err == block_output.get("reason", "")
    return block_output


def held_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_records: list[dict[str, object]],
    all_extra_fields: dict[str, object] | None = None,
) -> str | None:
    block_output = run_gate(
        monkeypatch, capsys, write_records(tmp_path / "s.jsonl", all_records), all_extra_fields
    )
    return block_output.get("reason")


def test_should_hold_a_typed_session_that_wrote_a_deferral_and_sent_no_card(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl",
        [typed_prompt_record(), reply_record(f"The flag is in place.\n\n{DEFERRAL_LINE}")],
    )
    block_output = run_gate(monkeypatch, capsys, transcript_path)
    assert block_output["decision"] == "block"
    assert block_output["reason"].startswith(CLOSING_ROUND_REASON_LEAD)
    assert f'"{DEFERRAL_LINE}"' in block_output["reason"]
    assert "The flag is in place." not in block_output["reason"]
    assert "AskUserQuestion" in block_output["reason"]


def test_should_log_a_hold_and_no_allow(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    log_path = tmp_path / ".claude" / "logs" / "hook-blocks.log"
    assert (
        held_reason(
            monkeypatch, capsys, tmp_path, [typed_prompt_record(), reply_record("Both tests pass.")]
        )
        is None
    )
    assert not log_path.exists()
    assert held_reason(
        monkeypatch, capsys, tmp_path, [typed_prompt_record(), reply_record(DEFERRAL_LINE)]
    )
    assert (
        json.loads(log_path.read_text(encoding="utf-8"))["hook"] == "closing_question_round_gate.py"
    )


def test_should_allow_once_a_question_card_follows_the_open_item_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(DEFERRAL_LINE),
        tool_call_record("AskUserQuestion"),
        tool_result_record("AskUserQuestion", "The user chose Leave it."),
        reply_record("The backoff setting stays as it is."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_hold_for_an_open_item_line_written_after_the_cards(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(DEFERRAL_LINE),
        tool_call_record("AskUserQuestion"),
        tool_result_record("AskUserQuestion", "The user chose Add it now."),
        reply_record("The jitter option is out of scope for this change."),
    ]
    reason = held_reason(monkeypatch, capsys, tmp_path, all_records)
    assert reason is not None
    assert "jitter option" in reason
    assert DEFERRAL_LINE not in reason


@pytest.mark.parametrize(
    "all_question_records",
    [
        [
            tool_call_record("AskUserQuestion", tool_use_id="id-refused"),
            tool_result_record(
                "AskUserQuestion",
                "Question refused: the chat text runs 600 words.",
                is_error=True,
                tool_use_id="id-refused",
            ),
        ],
        [
            tool_call_record("AskUserQuestion", tool_use_id="id-errored"),
            tool_result_record(
                "AskUserQuestion",
                "InputValidationError: questions is required.",
                is_error=True,
                tool_use_id="id-errored",
            ),
        ],
        [tool_call_record("AskUserQuestion", tool_use_id="id-unanswered")],
        [
            tool_call_record("AskUserQuestion", tool_use_id="id-asked"),
            tool_result_record("Bash", "ok", tool_use_id="id-other"),
        ],
    ],
)
def test_should_hold_when_the_question_call_did_not_reach_the_user(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_question_records: list[dict[str, object]],
) -> None:
    all_records = [typed_prompt_record(), reply_record(DEFERRAL_LINE), *all_question_records]
    assert f'"{DEFERRAL_LINE}"' in str(held_reason(monkeypatch, capsys, tmp_path, all_records))


def test_should_start_the_stretch_after_the_last_call_that_reached_the_user(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(DEFERRAL_LINE),
        tool_call_record("AskUserQuestion", tool_use_id="id-first"),
        tool_result_record("AskUserQuestion", "The user chose Leave it.", tool_use_id="id-first"),
        reply_record("The jitter option is parked."),
        tool_call_record("AskUserQuestion", tool_use_id="id-second"),
        tool_result_record(
            "AskUserQuestion", "Question refused.", is_error=True, tool_use_id="id-second"
        ),
    ]
    reason = held_reason(monkeypatch, capsys, tmp_path, all_records)
    assert '"The jitter option is parked."' in str(reason)
    assert DEFERRAL_LINE not in str(reason)


@pytest.mark.parametrize(
    "open_line",
    [
        "This defers the cleanup.",
        "I will send the cleanup as a follow-up.",
        "The cleanup goes in a follow up PR.",
        "The cleanup is parked.",
        "The cleanup is not covered here.",
        "The cleanup is left for later.",
        "The cleanup goes in a later pull request.",
        "One known gap is the cleanup.",
        "That is a known limitation.",
        "One open question is the cache size.",
        "The cache size is unresolved.",
        "The cache size is uncertain.",
        "I am not sure the cache is warm.",
        "I am unsure about the cache.",
        "It is unclear which cache wins.",
        "I assumed the cache holds 64 entries.",
        "I worked on, assuming the cache holds 64 entries.",
        "The cache size is an assumption.",
        "The cache size is unverified.",
        "I could not verify the cache size.",
        "I couldn't verify the cache size.",
        "I couldn\u2019t verify the cache size.",
        "I did not verify the cache size.",
        "The cache path is untested.",
        "The cache path is not tested.",
        "The cache size was a judgment call.",
        "The cache size is your call.",
        "The cache size is up to you.",
        "The cache size needs your decision.",
        "THE CACHE SIZE IS DEFERRED.",
        "No follow-up is needed except the retry fix.",
        "Nothing deferred except the backoff setting.",
        "No follow-ups except the retry fix.",
        "Nothing is deferred but the cache size.",
        "Nothing deferred other than the cache size.",
        "Nothing deferred apart from the cache size.",
        "Nothing deferred besides the cache size.",
        "Nothing deferred aside from the cache size.",
        "The cache warm-up is pending.",
        "TODO: warm the cache.",
        "The cache size is TBD.",
        "I skipped the cache warm-up.",
        "I am skipping the cache warm-up.",
        "The cache warm-up is not done.",
        "The cache warm-up is blocked.",
        "The cache suite did not run.",
        "The cache suite didn't run.",
        "The cache suite was not run.",
        "I could not reproduce the cache miss.",
        "I couldn't reproduce the cache miss.",
        "One deferral is the cache size.",
        "Two deferrals remain.",
        "One uncertainty is the cache size.",
        "The cache size needs your input.",
        "The cache size and the TTL need your input.",
        "I need you to pick the cache size.",
        "We assumed the cache holds 64 entries.",
        "I assume the cache holds 64 entries.",
        "We assume the cache holds 64 entries.",
        "I left it for you.",
        "I left these for you.",
        "The cache size is for you to decide.",
        "The cache size is waiting on you.",
        "The cache size waits on you.",
        "Should the cache hold 64 entries?",
        "- Should the cache hold 64 entries?**",
        "You may want to decide on the timeout.",
        "I didn't test the retry path.",
        "I did not test the retry path.",
        "I'll do the docs in a separate PR.",
        "The docs go in a separate pull request.",
        "I could not confirm the cache size.",
        "I couldn't confirm the cache size.",
        "I was unable to confirm the cache size.",
        "The cache warm-up is not yet implemented.",
        "The cache size rests on your judgment.",
        "Nothing deferred, except the backoff setting.",
        "Nothing is deferred.",
        "No follow-up is needed.",
        "No open questions remain.",
        "The cleanup is not deferred.",
        "Nothing is out of scope.",
    ],
)
def test_should_hold_for_each_marker_of_an_open_item(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    open_line: str,
) -> None:
    reason = held_reason(
        monkeypatch, capsys, tmp_path, [typed_prompt_record(), reply_record(open_line)]
    )
    assert reason is not None
    assert f'"{open_line}"' in reason


@pytest.mark.parametrize(
    "closed_line",
    [
        "Both tests pass, and the job is renamed.",
        "The flag is `--fast?`",
        "I will follow up with the build once it lands.",
        "The undeferred jobs ran first.",
        "Open items: none.",
    ],
)
def test_should_allow_a_line_with_no_marker_and_no_work(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    closed_line: str,
) -> None:
    assert (
        held_reason(
            monkeypatch, capsys, tmp_path, [typed_prompt_record(), reply_record(closed_line)]
        )
        is None
    )


def test_should_hold_for_a_marker_that_sits_beside_a_negated_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    open_line = "Nothing is deferred, but the retry path is untested."
    reason = held_reason(
        monkeypatch, capsys, tmp_path, [typed_prompt_record(), reply_record(open_line)]
    )
    assert reason is not None
    assert f'"{open_line}"' in reason


@pytest.mark.parametrize(
    "masked_reply",
    [
        'The job holds three status values.\n\n```python\nSTATUS_NAMES = ("queued", "deferred")\n```\n\nThat is all.',
        "The changelog has one entry.\n\n> The backoff setting is deferred.\n\nThat entry is a month old.",
        "A paused job holds the status `deferred` until the queue drains.",
        "The page has one block.\n\n<div>\nThe backoff setting is deferred.\n</div>\n\nThat is all.",
        "The flag is not `--fast` sure enough.",
        "Run this to see the queue:\n\n    queue list --status deferred\n\nThat is all.",
        "    queue list --status deferred\n\nThat is all.",
    ],
)
def test_should_leave_out_fences_quotes_code_spans_html_and_indented_code_blocks(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    masked_reply: str,
) -> None:
    assert (
        held_reason(
            monkeypatch, capsys, tmp_path, [typed_prompt_record(), reply_record(masked_reply)]
        )
        is None
    )


def test_should_read_assistant_text_blocks_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    thinking_record = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "I am not sure which file it is."}],
        },
    }
    sidechain_record = {**reply_record("The second caller is unverified."), "isSidechain": True}
    all_records = [
        typed_prompt_record("Note that the backoff setting is deferred."),
        thinking_record,
        sidechain_record,
        tool_call_record(
            "Write", {"file_path": "notes.md", "content": "The backoff setting is deferred."}
        ),
        tool_result_record("Write", "The backoff setting is deferred and untested."),
        reply_record("The note is written.\n\nOpen items: none."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_hold_for_a_deferral_from_an_earlier_turn_after_a_notification_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(DEFERRAL_LINE),
        machine_prompt_record("task_notification", "<task-notification>done</task-notification>"),
        reply_record("The test run finished, and all tests pass."),
    ]
    reason = held_reason(monkeypatch, capsys, tmp_path, all_records)
    assert reason is not None
    assert f'"{DEFERRAL_LINE}"' in reason


@pytest.mark.parametrize(
    "all_extra_fields",
    [
        {"agent_id": "agent-1"},
        {"conversation_id": "conversation-1"},
        {"background_tasks": [{"id": "task-1"}]},
    ],
)
def test_should_allow_a_subagent_a_cursor_stop_and_a_stop_with_background_work(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_extra_fields: dict[str, object],
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl", [typed_prompt_record(), reply_record(DEFERRAL_LINE)]
    )
    assert run_gate(monkeypatch, capsys, transcript_path, all_extra_fields) == {}


@pytest.mark.parametrize(
    "all_extra_fields", [{"agent_id": ""}, {"background_tasks": []}, {"stop_hook_active": True}]
)
def test_should_hold_when_a_field_that_exempts_a_stop_is_empty_or_marks_a_held_stop(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_extra_fields: dict[str, object],
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl", [typed_prompt_record(), reply_record(DEFERRAL_LINE)]
    )
    assert run_gate(monkeypatch, capsys, transcript_path, all_extra_fields)["decision"] == "block"


def test_should_allow_a_headless_run_and_hold_when_the_variable_is_unset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl", [typed_prompt_record(), reply_record(DEFERRAL_LINE)]
    )
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "0")
    assert run_gate(monkeypatch, capsys, transcript_path) == {}
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ATTENDED")
    assert run_gate(monkeypatch, capsys, transcript_path)["decision"] == "block"


@pytest.mark.parametrize("turn_origin", ["sdk", "task_notification"])
def test_should_allow_a_session_no_person_typed_into(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    turn_origin: str,
) -> None:
    all_records = [machine_prompt_record(turn_origin), reply_record(DEFERRAL_LINE)]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_hold_an_agent_seeded_session_a_person_later_typed_into(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        machine_prompt_record("task_notification"),
        reply_record("The retry flag is in place."),
        typed_prompt_record("Add the backoff setting too."),
        reply_record("The jitter option is parked."),
    ]
    assert '"The jitter option is parked."' in str(
        held_reason(monkeypatch, capsys, tmp_path, all_records)
    )


def test_should_hold_a_second_time_and_allow_the_third_stop(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_held_once_records = [
        typed_prompt_record(),
        reply_record(DEFERRAL_LINE),
        stop_feedback_record(),
        reply_record("The backoff setting waits for the next change."),
    ]
    assert f'"{DEFERRAL_LINE}"' in str(
        held_reason(monkeypatch, capsys, tmp_path, all_held_once_records)
    )
    all_held_twice_records = [
        *all_held_once_records,
        stop_feedback_record(),
        reply_record("No question tool here."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_held_twice_records) is None


def test_should_start_a_new_hold_count_after_a_question_card(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(DEFERRAL_LINE),
        stop_feedback_record(),
        stop_feedback_record(),
        tool_call_record("AskUserQuestion"),
        tool_result_record("AskUserQuestion", "The user chose Add it now."),
        reply_record("The jitter option is parked."),
    ]
    assert '"The jitter option is parked."' in str(
        held_reason(monkeypatch, capsys, tmp_path, all_records)
    )


def test_should_not_count_feedback_from_another_gate_or_an_assistant_quote_as_a_hold(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(f"What does this mean? {CLOSING_ROUND_REASON_LEAD}"),
        reply_record(DEFERRAL_LINE),
        stop_feedback_record(
            "Stop hook feedback:\nThe task list shows completed work beside open items."
        ),
        reply_record(f"The gate said: {CLOSING_ROUND_REASON_LEAD}"),
        stop_feedback_record("Stop hook feedback:\nThis turn worked on the user's ask."),
        reply_record(f"The gate said again: {CLOSING_ROUND_REASON_LEAD}"),
    ]
    assert f'"{DEFERRAL_LINE}"' in str(held_reason(monkeypatch, capsys, tmp_path, all_records))


def test_should_quote_at_most_eight_trimmed_lines_and_count_the_rest(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    long_line = "The cache path is untested " + "and slow " * 40
    all_open_item_lines = [f"Step {each_number} is deferred." for each_number in range(1, 11)]
    reason = held_reason(
        monkeypatch,
        capsys,
        tmp_path,
        [
            typed_prompt_record(),
            reply_record("\n".join(all_open_item_lines)),
            reply_record(long_line),
        ],
    )
    assert reason is not None
    all_quoted_lines = [each_line for each_line in reason.split("\n") if each_line.startswith('"')]
    assert len(all_quoted_lines) == MAXIMUM_QUOTED_LINE_COUNT
    assert all_quoted_lines[0] == '"Step 4 is deferred."'
    assert len(all_quoted_lines[-1]) == MAXIMUM_QUOTED_LINE_LENGTH + len('""')
    assert "Step 3 is deferred." not in reason
    assert "Earlier lines left out here: 3." in reason


def test_should_quote_a_repeated_line_once(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    reason = held_reason(
        monkeypatch,
        capsys,
        tmp_path,
        [typed_prompt_record(), reply_record(DEFERRAL_LINE), reply_record(DEFERRAL_LINE)],
    )
    assert reason is not None
    assert reason.count(DEFERRAL_LINE) == 1


def test_should_allow_malformed_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"not json")))
    assert closing_question_round_gate.main() == 0
    assert capsys.readouterr().out == ""


def test_should_allow_a_session_with_no_readable_transcript(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert run_gate(monkeypatch, capsys, None) == {}
    assert run_gate(monkeypatch, capsys, tmp_path / "missing.jsonl") == {}


def test_should_hold_through_a_subprocess_with_the_documented_contract(tmp_path: Path) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl", [typed_prompt_record(), reply_record(DEFERRAL_LINE)]
    )
    hook_input = {
        "hook_event_name": "Stop",
        "session_id": SESSION_ID,
        "transcript_path": str(transcript_path),
    }
    completed_process = subprocess.run(
        [sys.executable, str(GATE_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env={
            "HOME": str(tmp_path),
            "USERPROFILE": str(tmp_path),
            "CLAUDE_CODE_SESSION_ATTENDED": "1",
        },
        check=False,
    )
    assert completed_process.returncode == 2
    assert json.loads(completed_process.stdout)["decision"] == "block"
    assert completed_process.stderr.startswith(CLOSING_ROUND_REASON_LEAD)


def test_is_exempt_stop_reads_the_payload_and_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert closing_question_round_gate.is_exempt_stop({"agent_id": "agent-1"})
    assert closing_question_round_gate.is_exempt_stop({"conversation_id": "conversation-1"})
    assert not closing_question_round_gate.is_exempt_stop({"background_tasks": [{"id": "task-1"}]})
    assert not closing_question_round_gate.is_exempt_stop({"agent_id": "", "background_tasks": []})
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "0")
    assert closing_question_round_gate.is_exempt_stop({})


def test_has_background_work_reads_a_non_empty_list_object_or_string() -> None:
    assert closing_question_round_gate.has_background_work({"background_tasks": [{"id": "task-1"}]})
    assert closing_question_round_gate.has_background_work({"background_tasks": {"task-1": {}}})
    assert closing_question_round_gate.has_background_work({"background_tasks": "task-1"})
    assert not closing_question_round_gate.has_background_work({"background_tasks": {}})
    assert not closing_question_round_gate.has_background_work({"background_tasks": []})
    assert not closing_question_round_gate.has_background_work({"background_tasks": 3})
    assert not closing_question_round_gate.has_background_work({})


def test_prior_hold_count_counts_feedback_records_that_carry_the_lead() -> None:
    all_stretch_records = [
        stop_feedback_record(),
        stop_feedback_record("Stop hook feedback:\nThe task list shows completed work."),
        reply_record(CLOSING_ROUND_REASON_LEAD),
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": f"Stop hook feedback:\n{CLOSING_ROUND_REASON_LEAD}",
            },
        },
        typed_prompt_record(CLOSING_ROUND_REASON_LEAD),
        stop_feedback_record(f"Stop hook feedback:\n{IN_PROGRESS_TASKS_REASON_LEAD}"),
    ]
    assert closing_question_round_gate.prior_hold_count(all_stretch_records) == 3


def test_closing_round_reason_leads_with_the_fixed_sentence_and_ends_with_the_instruction() -> None:
    reason = closing_question_round_gate.closing_round_reason(
        ["The cleanup is parked.", "The cache is unverified."]
    )
    all_reason_lines = reason.split("\n")
    assert all_reason_lines[0] == CLOSING_ROUND_REASON_LEAD
    assert all_reason_lines[2:4] == ['"The cleanup is parked."', '"The cache is unverified."']
    assert "lines left out here" not in reason
    assert "at most four questions in one call" in all_reason_lines[-1]
    assert "refuses a question past 450 words or 15 items" in all_reason_lines[-1]
    assert "a refused question starts a new count" in all_reason_lines[-1]
    assert "write a link in a card as a bare URL" in all_reason_lines[-1]
    assert "end the reply with the In progress footer" in all_reason_lines[-1]
    assert "Open items: none." not in all_reason_lines[-1]
    assert all_reason_lines[-1].endswith(
        "send one question that says so and lets the user add an item."
    )


def write_session_tasks(tmp_path: Path, all_task_entries: list[dict[str, str]]) -> None:
    task_directory = tmp_path / ".claude" / "tasks" / SESSION_ID
    task_directory.mkdir(parents=True, exist_ok=True)
    for each_entry in all_task_entries:
        (task_directory / f"{each_entry['id']}.json").write_text(
            json.dumps(each_entry), encoding="utf-8"
        )


@pytest.mark.parametrize(
    ("closing_reply", "did_work", "expected_lead"),
    [
        ("Done.", True, FOOTER_MISSING_REASON_LEAD),
        ("Done.", False, ""),
        ("Done.\n\nOpen items: none.", False, IN_PROGRESS_TASKS_REASON_LEAD),
        ("Done.\n\nIn progress:\n- I am fixing the list reader.", True, FOOTER_GAP_REASON_LEAD),
        (
            "Done.\n\nIn progress:\n- I am fixing the list reader.\n- I am watching the discounts.",
            True,
            "",
        ),
    ],
)
def test_footer_hold_reason_picks_the_lead_from_the_reply_and_the_tasks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    closing_reply: str,
    did_work: bool,
    expected_lead: str,
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.delenv("CLAUDE_CODE_TASK_LIST_ID", raising=False)
    write_session_tasks(
        tmp_path,
        [
            {"id": "28", "subject": "Fix list reader lint finding", "status": "in_progress"},
            {"id": "29", "subject": "Watch discount ledger", "status": "in_progress"},
        ],
    )
    reason = closing_question_round_gate.footer_hold_reason(
        {"session_id": SESSION_ID}, closing_reply, did_work, time.monotonic() + 60
    )
    assert (reason or "").split("\n")[0] == expected_lead


def test_footer_hold_reason_owes_no_closing_line_when_nothing_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.delenv("CLAUDE_CODE_TASK_LIST_ID", raising=False)
    write_session_tasks(tmp_path, [{"id": "1", "subject": "Ship the export", "status": "completed"}])
    all_payload_fields: dict[str, object] = {"session_id": SESSION_ID}
    assert closing_question_round_gate.footer_hold_reason(
        all_payload_fields, "Done.", True, time.monotonic() + 60
    ) is None
    all_payload_fields["background_tasks"] = [{"id": "task-1"}]
    assert str(
        closing_question_round_gate.footer_hold_reason(
            all_payload_fields, "Done.", True, time.monotonic() + 60
        )
    ).startswith(FOOTER_MISSING_REASON_LEAD)


def test_should_read_the_closing_reply_from_the_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(DEFERRAL_LINE),
        tool_call_record("AskUserQuestion"),
        tool_result_record("AskUserQuestion", "The user chose Leave it."),
    ]
    closing_reply = "The backoff setting stays.\n\nThe jitter option is parked."
    reason = held_reason(
        monkeypatch, capsys, tmp_path, all_records, {"last_assistant_message": closing_reply}
    )
    assert '"The jitter option is parked."' in str(reason)
    assert DEFERRAL_LINE not in str(reason)
    assert (
        held_reason(monkeypatch, capsys, tmp_path, all_records, {"last_assistant_message": 7})
        is None
    )


def test_should_not_count_a_closing_reply_the_transcript_already_holds_twice(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    closing_reply = "\n".join(f"Step {each_number} is deferred." for each_number in range(1, 9))
    reason = held_reason(
        monkeypatch,
        capsys,
        tmp_path,
        [typed_prompt_record(), reply_record("Step 0 is deferred."), reply_record(closing_reply)],
        {"last_assistant_message": closing_reply},
    )
    assert "Earlier lines left out here: 1." in str(reason)
    assert '"Step 1 is deferred."' in str(reason)


def test_should_scan_a_payload_that_writes_as_prose_what_the_transcript_holds_as_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [typed_prompt_record(), reply_record("    TODO: add the flag.")]
    prose_fields = {"last_assistant_message": "TODO: add the flag."}
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records, prose_fields)).startswith(
        CLOSING_ROUND_REASON_LEAD
    )


def test_should_not_reread_a_closing_reply_written_before_the_cards(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(DEFERRAL_LINE),
        tool_call_record("AskUserQuestion"),
        tool_result_record("AskUserQuestion", "The user chose Leave it."),
    ]
    assert (
        held_reason(
            monkeypatch, capsys, tmp_path, all_records, {"last_assistant_message": DEFERRAL_LINE}
        )
        is None
    )


@pytest.mark.parametrize(
    ("wrapped_reply", "quoted_text"),
    [
        (
            "The cleanup is out of\nscope for this change.",
            "The cleanup is out of scope for this change.",
        ),
        ("The retry path is not\ntested yet.", "The retry path is not tested yet."),
    ],
)
def test_should_find_a_marker_split_across_a_soft_line_break(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    wrapped_reply: str,
    quoted_text: str,
) -> None:
    reason = held_reason(
        monkeypatch, capsys, tmp_path, [typed_prompt_record(), reply_record(wrapped_reply)]
    )
    assert f'"{quoted_text}"' in str(reason)


def test_should_hold_on_a_host_whose_prompt_records_carry_no_turn_origin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    untagged_prompt = {"type": "user", "message": {"role": "user", "content": "Add the flag."}}
    all_records = [untagged_prompt, reply_record(DEFERRAL_LINE)]
    assert f'"{DEFERRAL_LINE}"' in str(held_reason(monkeypatch, capsys, tmp_path, all_records))
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ATTENDED")
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_hold_a_session_a_custom_slash_command_started(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    command_record = {
        "type": "user",
        "turnOrigin": "human",
        "message": {
            "role": "user",
            "content": "<command-message>hello</command-message>\n"
            "<command-name>/hello</command-name>",
        },
    }
    command_text_record = {
        "type": "user",
        "isMeta": True,
        "message": {"role": "user", "content": "Say hello and list what is left."},
    }
    all_records = [command_record, command_text_record, reply_record(DEFERRAL_LINE)]
    assert f'"{DEFERRAL_LINE}"' in str(held_reason(monkeypatch, capsys, tmp_path, all_records))


@pytest.mark.parametrize("malformed_name", [["AskUserQuestion"], {"name": "AskUserQuestion"}])
def test_should_read_past_a_tool_call_whose_name_is_no_string(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    malformed_name: object,
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(DEFERRAL_LINE),
        tool_call_record(malformed_name, tool_use_id="id-malformed"),
        tool_result_record("AskUserQuestion", "ok", tool_use_id="id-malformed"),
    ]
    assert f'"{DEFERRAL_LINE}"' in str(held_reason(monkeypatch, capsys, tmp_path, all_records))


def test_should_allow_with_no_output_when_an_internal_step_raises(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def raise_type_error(*_: object) -> list[str]:
        raise TypeError("unhashable type: 'list'")

    transcript_path = write_records(
        tmp_path / "s.jsonl", [typed_prompt_record(), reply_record(DEFERRAL_LINE)]
    )
    assert run_gate(monkeypatch, capsys, transcript_path)["decision"] == "block"
    monkeypatch.setattr(closing_question_round_gate, "marked_open_lines", raise_type_error)
    assert run_gate(monkeypatch, capsys, transcript_path) == {}


def test_should_allow_with_no_output_once_the_deadline_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl", [typed_prompt_record(), reply_record(DEFERRAL_LINE)]
    )
    assert run_gate(monkeypatch, capsys, transcript_path)["decision"] == "block"
    monkeypatch.setattr(closing_question_round_gate, "STOP_DEADLINE_SECONDS", 0.0)
    assert run_gate(monkeypatch, capsys, transcript_path) == {}


@pytest.mark.parametrize("closed_stream_name", ["stdin", "stdout", "stderr"])
def test_supervised_main_should_allow_with_no_output_when_a_standard_stream_is_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], closed_stream_name: str
) -> None:
    def held_run(*all_arguments: object, **all_options: object) -> object:
        return subprocess.CompletedProcess(args=[], returncode=2, stdout=b'{"x": 1}', stderr=b"why")

    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"{}")))
    monkeypatch.setattr(closing_question_round_gate.subprocess, "run", held_run)
    monkeypatch.setattr(f"sys.{closed_stream_name}", None)
    assert closing_question_round_gate.supervised_main() == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_should_hold_work_whose_record_spells_its_type_with_a_json_escape(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.delenv("CLAUDE_CODE_TASK_LIST_ID", raising=False)
    write_session_tasks(tmp_path, [{"id": "1", "subject": "Ship the export", "status": "in_progress"}])
    escaped_work_line = json.dumps(tool_call_record("Edit")).replace(
        '"assistant"', '"\\u0061ssistant"'
    )
    transcript_path = tmp_path / "s.jsonl"
    transcript_path.write_text(
        "\n".join(
            [
                json.dumps(typed_prompt_record()),
                escaped_work_line,
                json.dumps(tool_result_record("Edit", "The file was updated.")),
            ]
        ),
        encoding="utf-8",
    )
    block_output = run_gate(
        monkeypatch, capsys, transcript_path, {"last_assistant_message": "Done."}
    )
    assert block_output["reason"].startswith(FOOTER_MISSING_REASON_LEAD)


def _held_gate_run(
    tmp_path: Path, all_stream_targets: dict[str, int]
) -> tuple[subprocess.CompletedProcess[bytes], float]:
    transcript_path = write_records(
        tmp_path / "s.jsonl", [typed_prompt_record(), reply_record(DEFERRAL_LINE)]
    )
    hook_input = json.dumps({"hook_event_name": "Stop", "transcript_path": str(transcript_path)})
    buffered_environment = {
        **{
            each_name: each_value
            for each_name, each_value in os.environ.items()
            if each_name != "PYTHONUNBUFFERED"
        },
        "HOME": str(tmp_path),
        "CLAUDE_CODE_SESSION_ATTENDED": "1",
    }
    started_at = time.monotonic()
    completed_gate = subprocess.run(
        [sys.executable, str(GATE_PATH)],
        input=hook_input.encode("utf-8"),
        env=buffered_environment,
        timeout=20,
        check=False,
        **{"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, **all_stream_targets},
    )
    return completed_gate, time.monotonic() - started_at


@pytest.mark.parametrize("stream_name", ["stdout", "stderr"])
def test_should_allow_the_stop_soon_after_the_write_starts_when_the_output_pipe_is_full(
    tmp_path: Path, stream_name: str
) -> None:
    read_end, write_end = os.pipe()
    os.set_blocking(write_end, False)
    try:
        while True:
            os.write(write_end, b"x" * 4096)
    except BlockingIOError:
        os.set_blocking(write_end, True)
    try:
        completed_gate, elapsed_seconds = _held_gate_run(tmp_path, {stream_name: write_end})
    finally:
        os.close(write_end)
        os.close(read_end)
    assert completed_gate.returncode == 0
    assert elapsed_seconds < 5


@pytest.mark.parametrize("stream_name", ["stdout", "stderr"])
def test_should_allow_the_stop_when_the_output_pipe_has_no_reader(
    tmp_path: Path, stream_name: str
) -> None:
    read_end, write_end = os.pipe()
    os.close(read_end)
    try:
        completed_gate, _ = _held_gate_run(tmp_path, {stream_name: write_end})
    finally:
        os.close(write_end)
    assert completed_gate.returncode == 0


@pytest.mark.parametrize("unwritable_stderr", ["closed_reader", "full_device"])
def test_should_leave_no_hold_on_stdout_when_stderr_cannot_be_written(
    tmp_path: Path, unwritable_stderr: str
) -> None:
    if unwritable_stderr == "full_device":
        if not Path("/dev/full").exists():
            pytest.skip("this host has no /dev/full")
        stderr_target = os.open("/dev/full", os.O_WRONLY)
    else:
        read_end, stderr_target = os.pipe()
        os.close(read_end)
    try:
        completed_gate, _ = _held_gate_run(
            tmp_path, {"stderr": stderr_target, "stdout": subprocess.PIPE}
        )
    finally:
        os.close(stderr_target)
    assert completed_gate.returncode == 0
    assert b'"block"' not in completed_gate.stdout


def test_should_hold_a_declaration_beside_an_in_progress_task_in_the_store(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.delenv("CLAUDE_CODE_TASK_LIST_ID", raising=False)
    task_directory = tmp_path / ".claude" / "tasks" / SESSION_ID
    task_directory.mkdir(parents=True)
    (task_directory / "1.json").write_text(
        json.dumps({"id": "1", "subject": "Ship the export", "status": "in_progress"}),
        encoding="utf-8",
    )
    all_records = [typed_prompt_record(), reply_record("Done.\n\nOpen items: none.")]
    reason = str(held_reason(monkeypatch, capsys, tmp_path, all_records))
    assert reason.startswith(IN_PROGRESS_TASKS_REASON_LEAD)
    assert "- Ship the export [ship export]" in reason


NO_TASKS = SessionTasks((), ())


LEDGER_SEEN = closing_question_round_gate.FooterSeen(("I am watching the ledger.",), 4, 1)


def shown(all_fields: dict[str, object], footer: object, all_tasks: SessionTasks) -> bool:
    kept_snapshot = closing_question_round_gate.kept_footer_snapshot(all_fields, footer)
    return closing_question_round_gate.were_jobs_shown(kept_snapshot, all_fields, footer, all_tasks)


def recorded(all_fields: dict[str, object], footer: object) -> bool:
    kept_snapshot = closing_question_round_gate.kept_footer_snapshot(all_fields, footer)
    return closing_question_round_gate.is_footer_recorded(kept_snapshot, footer)


def test_should_name_the_footer_tasks_and_background_jobs_the_same_in_any_order() -> None:
    two_tasks = SessionTasks(
        (TaskItem("28", "Fix the list reader", "in_progress"), TaskItem("29", "Watch the ledger", "in_progress")), ()
    )

    def snapshot(all_jobs: object, footer: object = LEDGER_SEEN, all_tasks: SessionTasks = NO_TASKS) -> object:
        return closing_question_round_gate.footer_snapshot({"background_tasks": all_jobs}, footer, all_tasks)

    first_snapshot = snapshot([{"id": "b"}, {"id": "a", "status": "running"}])
    assert first_snapshot == snapshot([{"id": "a"}, {"id": "b"}])
    assert first_snapshot.job_count == 2
    assert first_snapshot.state_key != snapshot([{"id": "a"}, {"id": "c"}]).state_key
    assert first_snapshot.state_key != snapshot([{"id": "a"}, {"id": "b"}], all_tasks=two_tasks).state_key
    assert snapshot(["ab", "c"]).state_key != snapshot(["a", "bc"]).state_key
    assert snapshot("ledger") == snapshot({"ledger": {}})


def test_should_name_two_replies_that_share_a_footer_apart() -> None:
    done_key = closing_question_round_gate.reply_key("Done.\n\nIn progress:\n- I am shipping 8590.")
    assert done_key == closing_question_round_gate.reply_key("\n  Done.\n\nIn progress:\n- I am shipping 8590.\n")
    assert done_key != closing_question_round_gate.reply_key("    Done.\n\nIn progress:\n- I am shipping 8590.")
    assert done_key != closing_question_round_gate.reply_key("Merged.\n\nIn progress:\n- I am shipping 8590.")
    assert done_key == closing_question_round_gate.reply_key("Done.\n\n\nIn progress:\n\n- I am shipping 8590.")
    assert done_key == closing_question_round_gate.reply_key("Done.\nIn progress:\n- I am shipping 8590.")
    assert done_key != closing_question_round_gate.reply_key("Done.\n\nIn progress:\n  - I am shipping 8590.")


def test_should_name_each_footer_occurrence_apart() -> None:
    first_key = closing_question_round_gate.footer_key(LEDGER_SEEN)
    assert first_key == closing_question_round_gate.footer_key(LEDGER_SEEN._replace())
    assert first_key != closing_question_round_gate.footer_key(LEDGER_SEEN._replace(occurrence=2))
    assert first_key != closing_question_round_gate.footer_key(LEDGER_SEEN._replace(count_start=9))
    assert first_key != closing_question_round_gate.footer_key(LEDGER_SEEN._replace(lines=("I am running the tests.",)))


def test_should_know_only_the_newest_footer_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    ledger_fields = {"session_id": SESSION_ID, "background_tasks": [{"id": "ledger"}]}
    both_fields = {**ledger_fields, "background_tasks": [{"id": "ledger"}, {"id": "tests"}]}
    assert closing_question_round_gate.kept_footer_snapshot(ledger_fields, LEDGER_SEEN) is None
    assert not shown(ledger_fields, LEDGER_SEEN, NO_TASKS)
    closing_question_round_gate.record_footer_jobs(ledger_fields, LEDGER_SEEN, NO_TASKS)
    assert shown(ledger_fields, LEDGER_SEEN, NO_TASKS)
    closing_question_round_gate.record_footer_jobs(both_fields, LEDGER_SEEN, NO_TASKS)
    assert closing_question_round_gate.kept_footer_snapshot(ledger_fields, LEDGER_SEEN) == (
        closing_question_round_gate.footer_snapshot(both_fields, LEDGER_SEEN, NO_TASKS)
    )
    assert shown(both_fields, LEDGER_SEEN, NO_TASKS)
    assert not shown(ledger_fields, LEDGER_SEEN, NO_TASKS)
    assert not shown(ledger_fields, None, NO_TASKS)


def test_should_keep_the_snapshots_of_the_newest_three_footers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    ledger_fields = {"session_id": SESSION_ID, "background_tasks": [{"id": "ledger"}]}
    tests_fields = {**ledger_fields, "background_tasks": [{"id": "tests"}]}
    all_footers = [LEDGER_SEEN._replace(occurrence=each_occurrence) for each_occurrence in range(1, 5)]
    closing_question_round_gate.record_footer_jobs(ledger_fields, all_footers[0], NO_TASKS)
    closing_question_round_gate.record_footer_jobs(tests_fields, all_footers[1], NO_TASKS, is_pending=True)
    assert shown(ledger_fields, all_footers[0], NO_TASKS)
    assert shown(tests_fields, all_footers[1], NO_TASKS)
    assert closing_question_round_gate.kept_footer_snapshot(tests_fields, all_footers[1]).is_pending
    assert not closing_question_round_gate.kept_footer_snapshot(ledger_fields, all_footers[0]).is_pending
    closing_question_round_gate.record_footer_jobs(ledger_fields, all_footers[2], NO_TASKS)
    closing_question_round_gate.record_footer_jobs(ledger_fields, all_footers[3], NO_TASKS)
    assert [each.footer_key for each in closing_question_round_gate.kept_footer_snapshots(ledger_fields)] == [
        closing_question_round_gate.footer_key(each_footer) for each_footer in reversed(all_footers[1:])
    ]
    assert not recorded(ledger_fields, all_footers[0])


def test_should_read_snapshots_whose_lines_end_in_a_carriage_return(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    ledger_fields = {"session_id": SESSION_ID, "background_tasks": [{"id": "ledger"}]}
    second_footer = LEDGER_SEEN._replace(occurrence=2)
    closing_question_round_gate.record_footer_jobs(ledger_fields, LEDGER_SEEN, NO_TASKS)
    closing_question_round_gate.record_footer_jobs(ledger_fields, second_footer, NO_TASKS)
    snapshot_path = closing_question_round_gate._snapshot_path(ledger_fields)
    assert snapshot_path is not None
    assert b"\r" not in snapshot_path.read_bytes()
    snapshot_path.write_bytes(snapshot_path.read_bytes().replace(b"\n", b"\r\n"))
    assert shown(ledger_fields, LEDGER_SEEN, NO_TASKS)
    assert shown(ledger_fields, second_footer, NO_TASKS)


def test_should_know_the_kept_snapshot_names_a_footer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    session_fields = {"session_id": SESSION_ID}
    assert not recorded(session_fields, LEDGER_SEEN)
    closing_question_round_gate.record_footer_jobs(session_fields, LEDGER_SEEN, NO_TASKS)
    assert recorded({"session_id": SESSION_ID, "background_tasks": [{"id": "ledger"}]}, LEDGER_SEEN)
    assert not recorded(session_fields, LEDGER_SEEN._replace(occurrence=2))
    assert not recorded(session_fields, None)


def test_should_leave_a_symlink_target_untouched_when_it_keeps_the_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    job_fields = {"session_id": SESSION_ID, "background_tasks": [{"id": "ledger"}]}
    target_path = tmp_path / "users-own-file.txt"
    target_path.write_text("keep me")
    snapshot_path = closing_question_round_gate._snapshot_path(job_fields)
    assert snapshot_path is not None
    try:
        snapshot_path.symlink_to(target_path)
    except OSError:
        pytest.skip("this runner cannot make a symlink")
    closing_question_round_gate.record_footer_jobs(job_fields, LEDGER_SEEN, NO_TASKS)
    assert target_path.read_text() == "keep me"
    assert not snapshot_path.is_symlink()
    if os.name != "nt":
        assert oct(snapshot_path.stat().st_mode & 0o777) == oct(0o600)
    assert shown(job_fields, LEDGER_SEEN, NO_TASKS)
    assert sorted(each_path.name for each_path in tmp_path.iterdir()) == sorted(
        [target_path.name, snapshot_path.name]
    )


@pytest.mark.parametrize("no_follow_flag", [0, getattr(os, "O_NOFOLLOW", 0)])
def test_should_refuse_a_snapshot_name_that_links_to_another_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, no_follow_flag: int
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(closing_question_round_gate, "NO_FOLLOW_FLAG", no_follow_flag)
    job_fields = {"session_id": SESSION_ID, "background_tasks": [{"id": "ledger"}]}
    closing_question_round_gate.record_footer_jobs(job_fields, LEDGER_SEEN, NO_TASKS)
    snapshot_path = closing_question_round_gate._snapshot_path(job_fields)
    assert snapshot_path is not None
    planted_path = tmp_path / "planted.txt"
    snapshot_path.rename(planted_path)
    try:
        snapshot_path.symlink_to(planted_path)
    except OSError:
        pytest.skip("this runner cannot make a symlink")
    assert closing_question_round_gate.kept_footer_snapshot(job_fields, LEDGER_SEEN) is None
    assert closing_question_round_gate.kept_footer_snapshots(job_fields) == ()


def test_should_record_and_read_back_a_long_background_job_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    all_long_jobs = [{"id": f"background-job-{each_index:07d}"} for each_index in range(10)]
    job_fields = {"session_id": SESSION_ID, "background_tasks": all_long_jobs}
    closing_question_round_gate.record_footer_jobs(job_fields, LEDGER_SEEN, NO_TASKS)
    assert shown(job_fields, LEDGER_SEEN, NO_TASKS)
    assert not shown(
        {**job_fields, "background_tasks": all_long_jobs[:9]}, LEDGER_SEEN, NO_TASKS
    )
