import io
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import question_brief_gate
from hooks_constants.question_brief_gate_constants import (
    MAXIMUM_BRIEF_LIST_ITEM_COUNT,
    MAXIMUM_BRIEF_WORD_COUNT,
)

GATE_SCRIPT = Path(__file__).resolve().parent / "question_brief_gate.py"
PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent
QUESTION_ID = "toolu_question_now"
EARLIER_QUESTION_ID = "toolu_question_earlier"
SHORT_POLL_LIMIT_SECONDS = 0.3
LATE_WRITE_DELAY_SECONDS = 0.1
FIFO_RUN_TIMEOUT_SECONDS = 5
BASH_CALL_ID = "toolu_bash"
REVIEW_ITEM_COUNT = MAXIMUM_BRIEF_LIST_ITEM_COUNT + 15
EARLIER_TURN_ITEM_COUNT = MAXIMUM_BRIEF_LIST_ITEM_COUNT + 5
CURRENT_TURN_ITEM_COUNT = MAXIMUM_BRIEF_LIST_ITEM_COUNT + 1


def prompt_entry(prompt_text: str) -> dict[str, object]:
    return {"type": "user", "message": {"role": "user", "content": prompt_text}}


def meta_entry(prompt_text: str) -> dict[str, object]:
    return {"type": "user", "isMeta": True, "message": {"role": "user", "content": prompt_text}}


def queued_entry(prompt_text: str) -> dict[str, object]:
    return {"type": "attachment", "attachment": {"type": "queued_command", "prompt": prompt_text}}


def text_entry(text: str, stop_reason: str = "tool_use") -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "id": "msg_a",
            "role": "assistant",
            "stop_reason": stop_reason,
            "content": [{"type": "text", "text": text}],
        },
    }


def stop_summary_entry() -> dict[str, object]:
    return {"type": "system", "subtype": "stop_hook_summary"}


def question_entry(tool_use_id: str) -> dict[str, object]:
    question_input = {"questions": [{"question": "Which one?", "header": "Pick", "options": []}]}
    return {
        "type": "assistant",
        "message": {
            "id": "msg_a",
            "role": "assistant",
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": "AskUserQuestion",
                    "input": question_input,
                }
            ],
        },
    }


def result_entry(tool_use_id: object, is_error: bool) -> dict[str, object]:
    result_block = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": "answer",
        "is_error": is_error,
    }
    return {"type": "user", "message": {"role": "user", "content": [result_block]}}


def tool_call_entry(tool_use_id: str, tool_name: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "id": "msg_b",
            "role": "assistant",
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": tool_name,
                    "input": {"command": "git status"},
                }
            ],
        },
    }


def held_stop_feedback_entry() -> dict[str, object]:
    return meta_entry("Stop hook feedback:\nThe reply ends with a question in plain text.")


def stop_hook_error_entry() -> dict[str, object]:
    return {
        "type": "attachment",
        "attachment": {
            "type": "hook_blocking_error",
            "hookEvent": "Stop",
            "hookName": "Stop",
            "toolUseID": "toolu_stop",
            "blockingError": {"blockingError": "The reply ends with a question in plain text."},
        },
    }


def task_notification_entry() -> dict[str, object]:
    return prompt_entry("<task-notification>\n<task-id>a1</task-id>\n</task-notification>")


def words(count: int) -> str:
    return " ".join(["word"] * count) + "."


def bullets(count: int) -> str:
    return "\n".join(f"- Item {each_index} needs a call." for each_index in range(count))


def table(row_count: int) -> str:
    all_rows = [f"| {each_index} | Row {each_index} |" for each_index in range(row_count)]
    return "\n".join(["| # | What |", "|---|---|", *all_rows])


def verdict(all_entries: list[dict[str, object]]) -> str | None:
    brief = question_brief_gate.brief_before_question(all_entries, QUESTION_ID)
    assert brief is not None
    return question_brief_gate.refusal_reason(brief)


def write_transcript(tmp_path: Path, all_entries: list[object]) -> Path:
    transcript_path = tmp_path / "transcript.jsonl"
    transcript_path.write_text(
        "\n".join(json.dumps(each_entry) for each_entry in all_entries) + "\n", encoding="utf-8"
    )
    return transcript_path


def question_payload(transcript_path: object, **extra_payload: object) -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "AskUserQuestion",
        "tool_use_id": QUESTION_ID,
        "transcript_path": transcript_path,
        "tool_input": {"questions": []},
        **extra_payload,
    }


def run_main(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], stdin_bytes: bytes
) -> tuple[int, str]:
    monkeypatch.setattr(
        question_brief_gate, "TRANSCRIPT_POLL_LIMIT_SECONDS", SHORT_POLL_LIMIT_SECONDS
    )
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin_bytes), encoding="utf-8"))
    exit_code = question_brief_gate.main()
    return exit_code, capsys.readouterr().err


def run_gate_on(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    all_entries: list[dict[str, object]],
) -> tuple[int, str]:
    transcript_path = write_transcript(tmp_path, all_entries)
    payload_bytes = json.dumps(question_payload(str(transcript_path))).encode()
    return run_main(monkeypatch, capsys, payload_bytes)


def item_count_refusal(item_count: int) -> str:
    return f"runs {item_count} list or table items"


def refuse_to_wait(seconds: float) -> None:
    raise AssertionError(f"the gate waited {seconds} seconds on a transcript it cannot use")


def long_brief_entries() -> list[dict[str, object]]:
    return [
        prompt_entry("Fix it."),
        text_entry(table(MAXIMUM_BRIEF_LIST_ITEM_COUNT + 15)),
        question_entry(QUESTION_ID),
    ]


@pytest.mark.parametrize(
    "brief_text",
    [
        words(40),
        words(MAXIMUM_BRIEF_WORD_COUNT),
        bullets(MAXIMUM_BRIEF_LIST_ITEM_COUNT),
        table(MAXIMUM_BRIEF_LIST_ITEM_COUNT),
        "Two choices.\n\n- **Keep:** the gate stays.\n- **Drop:** the gate goes.",
        "```\n" + bullets(MAXIMUM_BRIEF_LIST_ITEM_COUNT + 10) + "\n```",
        "~~~\n" + table(MAXIMUM_BRIEF_LIST_ITEM_COUNT + 10) + "\n~~~",
    ],
)
def test_should_pass_a_short_brief(brief_text: str) -> None:
    assert (
        verdict([prompt_entry("Fix it."), text_entry(brief_text), question_entry(QUESTION_ID)])
        is None
    )


@pytest.mark.parametrize(
    ("brief_text", "expected_fragment"),
    [
        (
            words(MAXIMUM_BRIEF_WORD_COUNT + 1),
            f"{MAXIMUM_BRIEF_WORD_COUNT + 1} words, over the {MAXIMUM_BRIEF_WORD_COUNT}-word limit",
        ),
        (
            bullets(MAXIMUM_BRIEF_LIST_ITEM_COUNT + 1),
            f"{MAXIMUM_BRIEF_LIST_ITEM_COUNT + 1} list or table items, over the {MAXIMUM_BRIEF_LIST_ITEM_COUNT}-item limit",
        ),
        (
            table(MAXIMUM_BRIEF_LIST_ITEM_COUNT + 1),
            f"{MAXIMUM_BRIEF_LIST_ITEM_COUNT + 1} list or table items, over the {MAXIMUM_BRIEF_LIST_ITEM_COUNT}-item limit",
        ),
        (
            "\n".join(
                f"{each_index}. Step {each_index}."
                for each_index in range(MAXIMUM_BRIEF_LIST_ITEM_COUNT + 1)
            ),
            f"{MAXIMUM_BRIEF_LIST_ITEM_COUNT + 1} list or table items",
        ),
        (
            "```\nfenced line\n```\n" + bullets(MAXIMUM_BRIEF_LIST_ITEM_COUNT + 1),
            f"{MAXIMUM_BRIEF_LIST_ITEM_COUNT + 1} list or table items",
        ),
    ],
)
def test_should_refuse_a_long_brief_naming_the_limit_it_passed(
    brief_text: str, expected_fragment: str
) -> None:
    refusal = verdict(
        [prompt_entry("Fix it."), text_entry(brief_text), question_entry(QUESTION_ID)]
    )
    assert refusal is not None
    assert expected_fragment in refusal
    assert "Shorten the brief" in refusal
    assert "split the question" in refusal


def test_should_name_only_the_word_limit_when_only_the_words_run_over() -> None:
    refusal = verdict(
        [
            prompt_entry("Fix it."),
            text_entry(words(MAXIMUM_BRIEF_WORD_COUNT + 1)),
            question_entry(QUESTION_ID),
        ]
    )
    assert refusal is not None
    assert "-item limit" not in refusal


def test_should_add_up_text_blocks_across_tool_calls_in_one_turn() -> None:
    half_limit = MAXIMUM_BRIEF_WORD_COUNT // 2
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(words(half_limit)),
        result_entry("toolu_bash", False),
        text_entry(words(half_limit + 10)),
        question_entry(QUESTION_ID),
    ]
    assert f"{2 * half_limit + 10} words" in (verdict(all_entries) or "")


@pytest.mark.parametrize(
    "turn_start_entries",
    [
        [
            stop_summary_entry(),
            meta_entry(
                'Another Claude session sent a message: <agent-message from="a1">Done.</agent-message>'
            ),
        ],
        [prompt_entry("<task-notification>\n<task-id>a1</task-id>\n</task-notification>")],
        [
            stop_summary_entry(),
            prompt_entry("<task-notification>\n<task-id>a1</task-id>\n</task-notification>"),
        ],
        [
            stop_summary_entry(),
            queued_entry("<task-notification>\n<task-id>a1</task-id>\n</task-notification>"),
        ],
    ],
)
def test_should_never_count_text_from_an_earlier_turn(
    turn_start_entries: list[dict[str, object]],
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(words(MAXIMUM_BRIEF_WORD_COUNT * 2), stop_reason="end_turn"),
        *turn_start_entries,
        text_entry(words(10)),
        question_entry(QUESTION_ID),
    ]
    assert verdict(all_entries) is None


@pytest.mark.parametrize(
    "held_stop_entries",
    [
        [stop_summary_entry()],
        [
            stop_summary_entry(),
            prompt_entry("Stop hook feedback:\nThe reply ends with a question in plain text."),
        ],
        [],
    ],
)
def test_should_keep_counting_through_a_held_stop(
    held_stop_entries: list[dict[str, object]],
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(
            bullets(MAXIMUM_BRIEF_LIST_ITEM_COUNT + 1) + "\n\nWhich one first?",
            stop_reason="end_turn",
        ),
        *held_stop_entries,
        text_entry(words(10)),
        question_entry(QUESTION_ID),
    ]
    assert f"{MAXIMUM_BRIEF_LIST_ITEM_COUNT + 1} list or table items" in (
        verdict(all_entries) or ""
    )


def test_should_pass_a_retry_after_a_refusal() -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(words(MAXIMUM_BRIEF_WORD_COUNT * 2)),
        question_entry(EARLIER_QUESTION_ID),
        result_entry(EARLIER_QUESTION_ID, True),
        text_entry(words(30)),
        question_entry(QUESTION_ID),
    ]
    assert verdict(all_entries) is None


def test_should_not_charge_a_second_question_for_the_first_brief() -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(words(MAXIMUM_BRIEF_WORD_COUNT - 10)),
        question_entry(EARLIER_QUESTION_ID),
        result_entry(EARLIER_QUESTION_ID, False),
        text_entry(words(MAXIMUM_BRIEF_WORD_COUNT - 10)),
        question_entry(QUESTION_ID),
    ]
    assert verdict(all_entries) is None


@pytest.mark.parametrize(
    "mid_turn_entry",
    [
        queued_entry('<agent-message from="a1">\nDone.\n</agent-message>'),
        queued_entry("<task-notification>\n<task-id>a1</task-id>\n</task-notification>"),
        {
            "type": "user",
            "isCompactSummary": True,
            "message": {"role": "user", "content": "This session is being continued."},
        },
    ],
)
def test_should_keep_counting_through_a_message_queued_mid_turn_that_the_user_did_not_type(
    mid_turn_entry: dict[str, object],
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(words(MAXIMUM_BRIEF_WORD_COUNT)),
        mid_turn_entry,
        text_entry(words(10)),
        question_entry(QUESTION_ID),
    ]
    assert f"{MAXIMUM_BRIEF_WORD_COUNT + 10} words" in (verdict(all_entries) or "")


def test_should_reset_on_a_message_the_user_queued_mid_turn() -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(words(MAXIMUM_BRIEF_WORD_COUNT * 2)),
        queued_entry("Okay, go on."),
        text_entry(words(20)),
        question_entry(QUESTION_ID),
    ]
    assert verdict(all_entries) is None


def test_should_report_no_brief_while_the_question_is_not_written_yet() -> None:
    assert (
        question_brief_gate.brief_before_question(
            [prompt_entry("Fix it."), text_entry(words(400))], QUESTION_ID
        )
        is None
    )


def test_should_refuse_a_long_brief_through_the_entry_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    transcript_path = write_transcript(tmp_path, long_brief_entries())
    exit_code, error_text = run_main(
        monkeypatch, capsys, json.dumps(question_payload(str(transcript_path))).encode()
    )
    assert exit_code == 2
    assert f"{MAXIMUM_BRIEF_LIST_ITEM_COUNT + 15} list or table items" in error_text


def test_should_refuse_a_question_written_after_the_hook_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_entries = long_brief_entries()
    transcript_path = write_transcript(tmp_path, all_entries[:-1])
    late_line = json.dumps(all_entries[-1]) + "\n"

    def append_the_call() -> None:
        with transcript_path.open("a", encoding="utf-8") as transcript_file:
            transcript_file.write(late_line)

    late_writer = threading.Timer(LATE_WRITE_DELAY_SECONDS, append_the_call)
    late_writer.start()
    exit_code, error_text = run_main(
        monkeypatch, capsys, json.dumps(question_payload(str(transcript_path))).encode()
    )
    late_writer.join()
    assert exit_code == 2
    assert "list or table items" in error_text


def test_should_pass_when_the_call_never_appears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    transcript_path = write_transcript(tmp_path, long_brief_entries()[:-1])
    exit_code, error_text = run_main(
        monkeypatch, capsys, json.dumps(question_payload(str(transcript_path))).encode()
    )
    assert (exit_code, error_text) == (0, "")


def test_should_keep_counting_through_a_user_entry_with_no_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(table(REVIEW_ITEM_COUNT)),
        prompt_entry("   "),
        question_entry(QUESTION_ID),
    ]
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, all_entries)
    assert exit_code == 2
    assert item_count_refusal(REVIEW_ITEM_COUNT) in error_text


def test_should_keep_counting_through_an_attachment_that_is_not_a_queued_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(table(REVIEW_ITEM_COUNT)),
        {"type": "attachment", "attachment": {"type": "hook_context", "prompt": "Fix"}},
        question_entry(QUESTION_ID),
    ]
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, all_entries)
    assert exit_code == 2
    assert item_count_refusal(REVIEW_ITEM_COUNT) in error_text


def test_should_end_a_turn_at_a_stop_hook_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(table(EARLIER_TURN_ITEM_COUNT)),
        stop_summary_entry(),
        task_notification_entry(),
        text_entry(table(CURRENT_TURN_ITEM_COUNT)),
        question_entry(QUESTION_ID),
    ]
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, all_entries)
    assert exit_code == 2
    assert item_count_refusal(CURRENT_TURN_ITEM_COUNT) in error_text


def test_should_end_a_turn_only_at_an_assistant_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(table(REVIEW_ITEM_COUNT)),
        {"type": "progress", "message": {"stop_reason": "end_turn"}},
        task_notification_entry(),
        question_entry(QUESTION_ID),
    ]
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, all_entries)
    assert exit_code == 2
    assert item_count_refusal(REVIEW_ITEM_COUNT) in error_text


def test_should_keep_counting_through_the_hook_attachment_of_a_held_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(table(REVIEW_ITEM_COUNT), stop_reason="end_turn"),
        held_stop_feedback_entry(),
        stop_hook_error_entry(),
        stop_summary_entry(),
        text_entry(words(10)),
        question_entry(QUESTION_ID),
    ]
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, all_entries)
    assert exit_code == 2
    assert item_count_refusal(REVIEW_ITEM_COUNT) in error_text


def test_should_keep_counting_across_a_tool_call_in_a_turn_a_task_notification_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(words(10), stop_reason="end_turn"),
        stop_summary_entry(),
        task_notification_entry(),
        text_entry(table(REVIEW_ITEM_COUNT)),
        tool_call_entry(BASH_CALL_ID, "Bash"),
        result_entry(BASH_CALL_ID, False),
        question_entry(QUESTION_ID),
    ]
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, all_entries)
    assert exit_code == 2
    assert item_count_refusal(REVIEW_ITEM_COUNT) in error_text


def test_should_keep_counting_across_a_tool_call_after_a_held_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(table(REVIEW_ITEM_COUNT), stop_reason="end_turn"),
        held_stop_feedback_entry(),
        stop_summary_entry(),
        tool_call_entry(BASH_CALL_ID, "Bash"),
        result_entry(BASH_CALL_ID, False),
        question_entry(QUESTION_ID),
    ]
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, all_entries)
    assert exit_code == 2
    assert item_count_refusal(REVIEW_ITEM_COUNT) in error_text


def test_should_count_only_a_tool_use_block_as_a_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(table(REVIEW_ITEM_COUNT)),
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "server_tool_use", "id": "srvtoolu_1", "name": "AskUserQuestion"}
                ]
            },
        },
        result_entry("srvtoolu_1", False),
        question_entry(QUESTION_ID),
    ]
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, all_entries)
    assert exit_code == 2
    assert item_count_refusal(REVIEW_ITEM_COUNT) in error_text


def test_should_keep_counting_across_a_tool_call_that_is_not_a_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(table(REVIEW_ITEM_COUNT)),
        tool_call_entry(BASH_CALL_ID, "Bash"),
        result_entry(BASH_CALL_ID, False),
        question_entry(QUESTION_ID),
    ]
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, all_entries)
    assert exit_code == 2
    assert item_count_refusal(REVIEW_ITEM_COUNT) in error_text


def test_should_count_only_text_blocks_in_the_brief(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        {
            "type": "assistant",
            "message": {"content": [{"type": "thinking", "text": table(EARLIER_TURN_ITEM_COUNT)}]},
        },
        text_entry(table(CURRENT_TURN_ITEM_COUNT)),
        question_entry(QUESTION_ID),
    ]
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, all_entries)
    assert exit_code == 2
    assert item_count_refusal(CURRENT_TURN_ITEM_COUNT) in error_text


def test_should_start_a_new_count_at_a_prompt_the_user_types_after_an_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(table(EARLIER_TURN_ITEM_COUNT)),
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "[Request interrupted by user]"}],
            },
        },
        prompt_entry("Use the other file."),
        text_entry(table(CURRENT_TURN_ITEM_COUNT)),
        question_entry(QUESTION_ID),
    ]
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, all_entries)
    assert exit_code == 2
    assert item_count_refusal(CURRENT_TURN_ITEM_COUNT) in error_text


def test_should_start_a_new_count_at_a_question_result_that_shares_an_entry_with_another_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    parallel_calls = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "stop_reason": "tool_use",
            "content": [
                {"type": "tool_use", "id": EARLIER_QUESTION_ID, "name": "AskUserQuestion"},
                {"type": "tool_use", "id": BASH_CALL_ID, "name": "Bash"},
            ],
        },
    }
    parallel_results = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": EARLIER_QUESTION_ID, "content": "answer"},
                {"type": "tool_result", "tool_use_id": BASH_CALL_ID, "content": "ok"},
            ],
        },
    }
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(table(EARLIER_TURN_ITEM_COUNT)),
        parallel_calls,
        parallel_results,
        text_entry(table(CURRENT_TURN_ITEM_COUNT)),
        question_entry(QUESTION_ID),
    ]
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, all_entries)
    assert exit_code == 2
    assert item_count_refusal(CURRENT_TURN_ITEM_COUNT) in error_text


def test_should_keep_counting_through_a_compaction_mid_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(table(REVIEW_ITEM_COUNT)),
        {"type": "system", "subtype": "compact_boundary", "content": "Conversation compacted"},
        {
            "type": "user",
            "isCompactSummary": True,
            "message": {"role": "user", "content": "This session is being continued."},
        },
        text_entry(words(10)),
        question_entry(QUESTION_ID),
    ]
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, all_entries)
    assert exit_code == 2
    assert item_count_refusal(REVIEW_ITEM_COUNT) in error_text


def test_should_keep_a_turn_ended_through_the_queue_entries_written_after_a_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        text_entry(table(EARLIER_TURN_ITEM_COUNT), stop_reason="end_turn"),
        stop_summary_entry(),
        {"type": "queue-operation", "operation": "enqueue", "content": "Done."},
        meta_entry(
            'Another Claude session sent a message: <agent-message from="a1">Done.</agent-message>'
        ),
        text_entry(table(CURRENT_TURN_ITEM_COUNT)),
        question_entry(QUESTION_ID),
    ]
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, all_entries)
    assert exit_code == 2
    assert item_count_refusal(CURRENT_TURN_ITEM_COUNT) in error_text


def test_should_not_wait_when_the_question_is_already_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_requested_waits: list[float] = []
    monkeypatch.setattr(question_brief_gate.time, "sleep", all_requested_waits.append)
    exit_code, error_text = run_gate_on(tmp_path, monkeypatch, capsys, long_brief_entries())
    assert exit_code == 2
    assert item_count_refusal(REVIEW_ITEM_COUNT) in error_text
    assert all_requested_waits == []


@pytest.mark.parametrize(
    "stdin_bytes",
    [
        b"",
        b"{not json",
        b"[1, 2]",
        b"\xff\xfe\x00 not utf-8",
        b"[" * 100_000,
        b'{"tool_name": "AskUserQuestion", "tool_use_id": ' + b"[" * 100_000,
        b'{"tool_name": "AskUserQuestion", "tool_use_id": ' + b"7" * 6000 + b"}",
    ],
)
def test_should_pass_on_unreadable_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], stdin_bytes: bytes
) -> None:
    assert run_main(monkeypatch, capsys, stdin_bytes) == (0, "")


@pytest.mark.parametrize(
    "transcript_path",
    [
        7,
        ["a", "b"],
        "has\x00nul.jsonl",
        "n" * 5000,
        "",
        None,
    ],
)
def test_should_pass_a_transcript_path_that_is_not_a_usable_path(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], transcript_path: object
) -> None:
    payload_bytes = json.dumps(question_payload(transcript_path)).encode()
    assert run_main(monkeypatch, capsys, payload_bytes) == (0, "")


@pytest.mark.parametrize(
    "tool_use_id",
    [7, ["a"], None, ""],
)
def test_should_pass_a_tool_use_id_that_is_not_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool_use_id: object,
) -> None:
    transcript_path = write_transcript(tmp_path, long_brief_entries())
    monkeypatch.setattr(question_brief_gate.time, "sleep", refuse_to_wait)
    payload_bytes = json.dumps(
        question_payload(str(transcript_path), tool_use_id=tool_use_id)
    ).encode()
    assert run_main(monkeypatch, capsys, payload_bytes) == (0, "")


@pytest.mark.parametrize(
    "odd_entry",
    [
        {"type": "assistant", "message": "a string"},
        {"type": "assistant", "message": ["a", "list"]},
        {"type": "user", "message": "a string"},
        {"type": "user", "message": 7},
        result_entry(["a", "list"], False),
        result_entry({"an": "object"}, False),
        {"type": "assistant", "message": {"content": [{"type": "text", "text": 7}]}},
        {"type": "system", "subtype": ["stop_hook_summary"]},
        {"type": "system", "subtype": {"a": 1}},
        {"type": "attachment", "attachment": "queued_command"},
        {"type": "attachment", "attachment": {"type": "queued_command", "prompt": ["Fix it."]}},
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "id": ["a", "list"], "name": "AskUserQuestion"}]
            },
        },
    ],
)
def test_should_never_crash_on_an_odd_transcript_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    odd_entry: dict[str, object],
) -> None:
    all_entries = [
        prompt_entry("Fix it."),
        odd_entry,
        text_entry(words(10)),
        question_entry(QUESTION_ID),
    ]
    transcript_path = write_transcript(tmp_path, all_entries)
    payload_bytes = json.dumps(question_payload(str(transcript_path))).encode()
    assert run_main(monkeypatch, capsys, payload_bytes) == (0, "")


def test_should_never_crash_on_a_deeply_nested_transcript_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    transcript_path = write_transcript(tmp_path, long_brief_entries())
    with transcript_path.open("a", encoding="utf-8") as transcript_file:
        transcript_file.write("[" * 100_000 + "\n")
    payload_bytes = json.dumps(question_payload(str(transcript_path))).encode()
    assert run_main(monkeypatch, capsys, payload_bytes) == (0, "")


@pytest.mark.parametrize("missing_kind", ["absent", "directory"])
def test_should_return_at_once_for_a_transcript_it_cannot_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    missing_kind: str,
) -> None:
    unreadable_path = tmp_path / "transcript.jsonl"
    if missing_kind == "directory":
        unreadable_path.mkdir()
    monkeypatch.setattr(question_brief_gate.time, "sleep", refuse_to_wait)
    payload_bytes = json.dumps(question_payload(str(unreadable_path))).encode()
    assert run_main(monkeypatch, capsys, payload_bytes) == (0, "")


def test_should_return_at_once_for_a_transcript_it_may_not_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    transcript_path = write_transcript(tmp_path, long_brief_entries())

    def refuse_to_open(*_arguments: object, **_keywords: object) -> None:
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "open", refuse_to_open)
    monkeypatch.setattr(question_brief_gate.time, "sleep", refuse_to_wait)
    payload_bytes = json.dumps(question_payload(str(transcript_path))).encode()
    assert run_main(monkeypatch, capsys, payload_bytes) == (0, "")


def test_should_pass_at_once_when_the_transcript_path_is_a_named_pipe(tmp_path: Path) -> None:
    pipe_path = tmp_path / "transcript.jsonl"
    os.mkfifo(pipe_path)
    completed = subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        input=json.dumps(question_payload(str(pipe_path))),
        capture_output=True,
        text=True,
        check=False,
        timeout=FIFO_RUN_TIMEOUT_SECONDS,
    )
    assert (completed.returncode, completed.stderr) == (0, "")


def test_should_exit_two_from_the_script_for_a_long_brief(tmp_path: Path) -> None:
    transcript_path = write_transcript(tmp_path, long_brief_entries())
    completed = subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        input=json.dumps(question_payload(str(transcript_path))),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "over the" in completed.stderr


def test_should_exit_zero_for_a_subagent_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    transcript_path = write_transcript(tmp_path, long_brief_entries())
    payload_bytes = json.dumps(question_payload(str(transcript_path), agent_id="a1")).encode()
    assert run_main(monkeypatch, capsys, payload_bytes) == (0, "")


def test_should_exit_zero_for_another_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    transcript_path = write_transcript(tmp_path, long_brief_entries())
    payload_bytes = json.dumps(question_payload(str(transcript_path), tool_name="Bash")).encode()
    assert run_main(monkeypatch, capsys, payload_bytes) == (0, "")


@pytest.mark.parametrize(
    "rule_path",
    ["rules/question-presentation.md", "docs/rule-guides/question-presentation.md"],
)
def test_should_state_the_limits_the_gate_enforces_in_each_rule_file(rule_path: str) -> None:
    rule_text = (PACKAGE_ROOT / rule_path).read_text(encoding="utf-8")
    assert f"{MAXIMUM_BRIEF_WORD_COUNT} words" in rule_text
    assert f"{MAXIMUM_BRIEF_LIST_ITEM_COUNT} list" in rule_text
