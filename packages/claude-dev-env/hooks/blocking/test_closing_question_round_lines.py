import json
from pathlib import Path

import pytest

from closing_question_round_lines import before_deadline, is_within_scan_cap, transcript_lines
from hooks_constants.closing_question_round_gate_constants import (
    MAXIMUM_SCANNED_BYTES,
    MAXIMUM_SCANNED_TEXT_BYTES,
)

NO_DEADLINE = float("inf")



def test_should_pass_each_text_through_before_the_deadline_and_raise_after_it() -> None:
    assert list(before_deadline(["one", "two"], NO_DEADLINE)) == ["one", "two"]
    with pytest.raises(TimeoutError):
        list(before_deadline(["one"], 0.0))


def test_should_split_a_readable_transcript_into_lines_and_return_an_empty_list_otherwise(
    tmp_path: Path,
) -> None:
    transcript_path = tmp_path / "s.jsonl"
    transcript_path.write_text('{"a": 1}\n{"b": 2}', encoding="utf-8")
    assert transcript_lines(str(transcript_path), NO_DEADLINE) == ['{"a": 1}', '{"b": 2}']
    assert transcript_lines(str(tmp_path / "missing.jsonl"), NO_DEADLINE) == []
    assert transcript_lines(None, NO_DEADLINE) == []
    with pytest.raises(TimeoutError):
        transcript_lines(str(transcript_path), 0.0)


def test_transcript_lines_reads_a_line_over_sixteen_mebibytes_as_an_empty_line(
    tmp_path: Path,
) -> None:
    transcript_path = tmp_path / "s.jsonl"
    oversized_line = "x" * (MAXIMUM_SCANNED_BYTES + 1)
    transcript_path.write_text(f'{{"a": 1}}\n{oversized_line}\n{{"b": 2}}', encoding="utf-8")
    assert transcript_lines(str(transcript_path), NO_DEADLINE) == ['{"a": 1}', "", '{"b": 2}']


def test_is_within_scan_cap_counts_utf8_bytes() -> None:
    assert is_within_scan_cap("x" * MAXIMUM_SCANNED_TEXT_BYTES)
    assert not is_within_scan_cap("x" * (MAXIMUM_SCANNED_TEXT_BYTES + 1))
    assert not is_within_scan_cap("é" * (MAXIMUM_SCANNED_TEXT_BYTES // 2 + 1))


def test_transcript_lines_should_spell_out_json_escapes_and_drop_a_byte_order_mark(
    tmp_path: Path,
) -> None:
    transcript_path = tmp_path / "s.jsonl"
    transcript_path.write_bytes(
        b'\xef\xbb\xbf{"type": "user"}\n{"\\u0074urnOrigin": "sdk", "text": "caf\\u00e9"}\n{"a": "\\u0062"'
    )
    all_lines = transcript_lines(str(transcript_path), NO_DEADLINE)
    assert all_lines[0] == '{"type": "user"}'
    assert json.loads(all_lines[1]) == {"turnOrigin": "sdk", "text": "caf\u00e9"}
    assert '"turnOrigin"' in all_lines[1]
    assert all_lines[2] == '{"a": "\\u0062"'


def test_transcript_lines_should_keep_a_line_whose_only_escapes_are_control_characters(
    tmp_path: Path,
) -> None:
    transcript_path = tmp_path / "s.jsonl"
    transcript_path.write_bytes(b'{"content":"\\u001b[31mred\\u001b[0m"}')
    assert transcript_lines(str(transcript_path), NO_DEADLINE) == [
        '{"content":"\\u001b[31mred\\u001b[0m"}'
    ]
