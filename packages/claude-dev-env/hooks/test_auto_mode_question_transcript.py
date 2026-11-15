"""Behavior tests for the AskUserQuestion transcript reader."""

from __future__ import annotations

import json
from pathlib import Path

from auto_mode_question_transcript import AskedQuestions, read_asked_questions


def _ask_records(tool_use_id: str, tool_use_result: object) -> list[dict[str, object]]:
    return [
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "id": tool_use_id, "name": "AskUserQuestion"}]
            },
        },
        {
            "type": "user",
            "toolUseResult": tool_use_result,
            "message": {"content": [{"type": "tool_result", "tool_use_id": tool_use_id}]},
        },
    ]


def test_should_read_each_answered_ask_with_the_offset_of_its_call(tmp_path: Path) -> None:
    transcript_path = tmp_path / "transcript.jsonl"
    all_records = _ask_records(
        "toolu_error", "Error: The question could not be shown."
    ) + _ask_records("toolu_ok", {"answers": {"Q?": "Allow it"}})
    all_lines = ["not json"] + [json.dumps(each_record) for each_record in all_records]
    transcript_path.write_text("\n".join(all_lines) + "\n", encoding="utf-8")
    third_record_offset = sum(len(each_line) + 1 for each_line in all_lines[:3])
    assert read_asked_questions(transcript_path) == [
        AskedQuestions(call_offset=third_record_offset, answer_by_question={"Q?": "Allow it"})
    ]


def test_should_read_nothing_from_a_missing_transcript(tmp_path: Path) -> None:
    assert read_asked_questions(tmp_path / "missing.jsonl") == []
    assert read_asked_questions(None) == []
