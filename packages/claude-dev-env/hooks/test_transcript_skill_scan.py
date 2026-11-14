"""Tests for skill invocation state across transcript compactions."""

import errno
import io
import json
import random
import sys
from pathlib import Path
from typing import BinaryIO

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from transcript_skill_scan import (
    ScanCaps,
    TranscriptToolCall,
    invokes_skill_with_argument,
    is_skill_loaded_after_last_compaction,
    is_skill_loaded_after_last_compaction_newest_first,
    is_skill_loaded_since_last_prompt,
    skill_invocation_status,
    tool_calls_since_last_prompt,
    transcript_lines_newest_first,
)


def _skill_entry(name: str, tool_use_id: str = "toolu_skill") -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "id": tool_use_id, "name": "Skill", "input": {"skill": name}}]
            },
        }
    )


def test_matching_skill_after_compaction_loads() -> None:
    lines = [
        _skill_entry("pr-lifecycle"),
        json.dumps({"type": "system", "subtype": "compact_boundary"}),
        _skill_entry("plugin:pr-lifecycle"),
    ]
    assert is_skill_loaded_after_last_compaction(
        lines, ("pr-lifecycle",), ("<command-name>/pr-lifecycle</command-name>",)
    )


def test_compaction_drops_a_loaded_skill() -> None:
    lines = [_skill_entry("pr-lifecycle"), json.dumps({"subtype": "compact_boundary"})]
    assert not is_skill_loaded_after_last_compaction(lines, ("pr-lifecycle",), ())


def test_user_command_loads_and_quoted_tool_result_does_not() -> None:
    marker = "<command-name>/pr-lifecycle</command-name>"
    user_entry = json.dumps({"type": "user", "message": {"content": marker}})
    quoted_result = json.dumps(
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": marker}]}}
    )
    assert is_skill_loaded_after_last_compaction([user_entry], ("pr-lifecycle",), (marker,))
    assert not is_skill_loaded_after_last_compaction([quoted_result], ("pr-lifecycle",), (marker,))


def test_malformed_entries_do_not_load() -> None:
    assert not is_skill_loaded_after_last_compaction(
        ["pr-lifecycle {", json.dumps({"type": "assistant", "message": {"content": "pr-lifecycle"}})],
        ("pr-lifecycle",),
        (),
    )


def test_invocation_status_separates_ever_invoked_from_loaded_now() -> None:
    compaction = json.dumps({"subtype": "compact_boundary"})
    assert skill_invocation_status([_skill_entry("pr-lifecycle")], ("pr-lifecycle",), ()) == (True, True)
    assert skill_invocation_status([_skill_entry("pr-lifecycle"), compaction], ("pr-lifecycle",), ()) == (True, False)
    assert skill_invocation_status([compaction, _skill_entry("other")], ("pr-lifecycle",), ()) == (False, False)


BUILD_EVAL_MARKER = "<command-name>/claude-api</command-name>"


def _skill_entry_with_arguments(name: str, arguments: object) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Skill", "input": {"skill": name, "args": arguments}}]
            },
        }
    )


def _invokes_build_eval(lines: list[str]) -> bool:
    return invokes_skill_with_argument(lines, ("claude-api",), "build-eval", BUILD_EVAL_MARKER)


def test_claude_api_skill_with_build_eval_argument_should_count() -> None:
    assert _invokes_build_eval([_skill_entry_with_arguments("claude-api", "build-eval")])


def test_build_eval_argument_followed_by_more_words_should_count() -> None:
    assert _invokes_build_eval([_skill_entry_with_arguments("claude-api", "build-eval   extra words")])


def test_plugin_prefixed_claude_api_with_build_eval_should_not_count() -> None:
    assert not _invokes_build_eval([_skill_entry_with_arguments("plugin:claude-api", "build-eval")])


def test_build_eval_argument_in_another_case_should_count() -> None:
    assert _invokes_build_eval([_skill_entry_with_arguments("claude-api", "Build-Eval")])


def test_claude_api_with_another_argument_should_not_count() -> None:
    assert not _invokes_build_eval([_skill_entry_with_arguments("claude-api", "migrate")])
    assert not _invokes_build_eval([_skill_entry_with_arguments("claude-api", "migrate build-eval")])
    assert not _invokes_build_eval([_skill_entry_with_arguments("claude-api", None)])
    assert not _invokes_build_eval([_skill_entry("claude-api")])


def test_build_eval_skill_alone_should_not_count() -> None:
    assert not _invokes_build_eval([_skill_entry("build-eval")])
    assert not _invokes_build_eval([_skill_entry_with_arguments("build-eval", "build-eval")])


def test_user_claude_api_build_eval_command_should_count() -> None:
    command_text = BUILD_EVAL_MARKER + "<command-args>build-eval for the gate</command-args>"
    assert _invokes_build_eval([json.dumps({"type": "user", "message": {"content": command_text}})])


def test_user_claude_api_command_with_another_argument_should_not_count() -> None:
    command_text = BUILD_EVAL_MARKER + "<command-args>migrate</command-args>"
    assert not _invokes_build_eval([json.dumps({"type": "user", "message": {"content": command_text}})])
    assert not _invokes_build_eval([json.dumps({"type": "user", "message": {"content": BUILD_EVAL_MARKER}})])


def test_quoted_build_eval_command_in_a_tool_result_should_not_count() -> None:
    command_text = BUILD_EVAL_MARKER + "<command-args>build-eval</command-args>"
    quoted_result = json.dumps(
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": command_text}]}}
    )
    assert not _invokes_build_eval([quoted_result])


def test_build_eval_invocation_before_a_compact_boundary_should_still_count() -> None:
    lines = [
        _skill_entry_with_arguments("claude-api", "build-eval"),
        json.dumps({"type": "system", "subtype": "compact_boundary"}),
        _skill_entry("other"),
    ]
    assert _invokes_build_eval(lines)


def _prompt_entry(content: object) -> str:
    return json.dumps({"type": "user", "message": {"content": content}})


def test_skill_since_last_prompt_survives_tool_results_and_skill_bodies() -> None:
    tool_result = _prompt_entry(
        [{"type": "tool_result", "tool_use_id": "toolu_skill", "content": "Launching skill: verify"}]
    )
    skill_body = json.dumps({"type": "user", "isMeta": True, "message": {"content": "Base directory for this skill"}})
    lines = [_prompt_entry("Commit it."), _skill_entry("verify"), tool_result, skill_body]
    assert is_skill_loaded_since_last_prompt(lines, ("verify",), ())


def test_refused_skill_load_leaves_the_skill_unloaded() -> None:
    refused_result = _prompt_entry(
        [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_skill",
                "content": "<tool_use_error>Skill verify cannot be used with Skill tool</tool_use_error>",
                "is_error": True,
            }
        ]
    )
    lines = [_prompt_entry("Commit it."), _skill_entry("verify"), refused_result]
    assert not is_skill_loaded_since_last_prompt(lines, ("verify",), ())


def test_skill_call_with_no_result_yet_leaves_the_skill_unloaded() -> None:
    lines = [_prompt_entry("Commit it."), _skill_entry("verify")]
    assert not is_skill_loaded_since_last_prompt(lines, ("verify",), ())


def test_result_for_another_call_leaves_the_skill_unloaded() -> None:
    other_result = _prompt_entry([{"type": "tool_result", "tool_use_id": "toolu_other", "content": "done"}])
    lines = [_prompt_entry("Commit it."), _skill_entry("verify"), other_result]
    assert not is_skill_loaded_since_last_prompt(lines, ("verify",), ())


def test_next_prompt_drops_a_skill_loaded_in_the_last_turn() -> None:
    lines = [_prompt_entry("First."), _skill_entry("verify"), _prompt_entry([{"type": "text", "text": "Second."}])]
    assert not is_skill_loaded_since_last_prompt(lines, ("verify",), ())


def test_slash_command_prompt_loads_the_skill_for_its_own_turn() -> None:
    marker = "<command-name>/verify</command-name>"
    assert is_skill_loaded_since_last_prompt([_prompt_entry("First."), _prompt_entry(marker)], ("verify",), (marker,))
    compaction = json.dumps({"subtype": "compact_boundary"})
    assert not is_skill_loaded_since_last_prompt([_prompt_entry(marker), compaction], ("verify",), (marker,))


def should_list_each_tool_call_since_the_last_prompt_with_its_outcome() -> None:
    def _call(tool_use_id: str, name: str) -> str:
        return json.dumps(
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tool_use_id, "name": name, "input": {}}]}}
        )

    def _result(tool_use_id: str, is_error: bool) -> str:
        tool_result = {"type": "tool_result", "tool_use_id": tool_use_id, "is_error": is_error, "content": "x"}
        return json.dumps({"type": "user", "message": {"content": [tool_result]}})

    lines = [
        json.dumps({"type": "user", "message": {"content": "First."}}),
        _call("old", "Read"),
        _result("old", False),
        json.dumps({"type": "user", "message": {"content": "Second."}}),
        _call("ok", "Bash"),
        _result("ok", False),
        _call("denied", "Edit"),
        _result("denied", True),
        _call("pending", "Write"),
    ]
    assert tool_calls_since_last_prompt(lines) == [
        TranscriptToolCall("Bash", {}, True),
        TranscriptToolCall("Edit", {}, False),
        TranscriptToolCall("Write", {}, False),
    ]


NEWEST_FIRST_SKILL_NAMES = ("pr-lifecycle",)
NEWEST_FIRST_MARKERS = ("<command-name>/pr-lifecycle</command-name>",)
ALL_GENERATED_LINE_KINDS = (
    _skill_entry("pr-lifecycle"),
    _skill_entry("plugin:pr-lifecycle"),
    json.dumps({"type": "system", "subtype": "compact_boundary"}),
    json.dumps(
        {
            "type": "assistant",
            "subtype": "compact_boundary",
            "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "pr-lifecycle"}}]},
        }
    ),
    json.dumps({"type": "user", "message": {"content": "<command-name>/pr-lifecycle</command-name>"}}),
    json.dumps({"type": "user", "message": {"content": "Please run pr-lifecycle later."}}),
    json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "content": "pr-lifecycle"}]}}),
    _skill_entry("other"),
    json.dumps({"type": "user", "message": {"content": "Unrelated."}}),
    "pr-lifecycle {",
)
EXHAUSTIVE_SEQUENCE_LENGTH = 4
GENERATED_SEQUENCE_COUNT = 3000
LONGEST_GENERATED_SEQUENCE = 30
GENERATED_SEQUENCE_SEED = 2338
ALL_TINY_BLOCK_SIZES = (1, 2, 3, 7, 64, 1 << 20)
ALL_READER_CONTENTS = (
    b"",
    b"\n",
    b"one",
    b"one\n",
    b"one\ntwo",
    b"one\ntwo\n",
    b"\n\nmiddle\n\n",
    b"short\n" + b"x" * 200 + b"\nend",
    "café ☃ \U0001f600\nnext é\n".encode("utf-8"),
    b"bad \xff\xfe byte\n\xc3\nhalf\xe2\x98\n",
    b"carriage\r\nreturn\rinside\n",
    b"lone\rcarriage\rreturns\r",
    b"\r",
    b"\r\r\n\n\r",
    b"ab\r\ncd\r\nef\r\n",
    b"x\ry\r\nz",
    b"abcdef\r\nghijk\rlmnopq\n",
)
ALL_LINE_ENDINGS = ("\n", "\r\n", "\r")
ALL_SEQUENCE_BLOCK_SIZES = (1, 2, 3, 7, 64)
MIXED_ENDING_SEQUENCE_COUNT = 400
STOP_AFTER_BLOCK_COUNT = 2


def _newest_first_load(all_lines: list[str]) -> bool:
    return is_skill_loaded_after_last_compaction_newest_first(
        list(reversed(all_lines)), NEWEST_FIRST_SKILL_NAMES, NEWEST_FIRST_MARKERS
    )


def _oldest_first_load(all_lines: list[str]) -> bool:
    return is_skill_loaded_after_last_compaction(all_lines, NEWEST_FIRST_SKILL_NAMES, NEWEST_FIRST_MARKERS)


def test_newest_first_load_should_take_the_newest_load_or_compaction() -> None:
    load, plugin_load, compaction, compaction_that_also_loads, slash_command = ALL_GENERATED_LINE_KINDS[:5]
    unrelated = ALL_GENERATED_LINE_KINDS[-2]
    assert _newest_first_load([compaction, load, unrelated])
    assert _newest_first_load([load, compaction, slash_command])
    assert not _newest_first_load([load, compaction])
    assert not _newest_first_load([plugin_load, compaction_that_also_loads])
    assert not _newest_first_load([unrelated])
    assert not _newest_first_load([])


def test_newest_first_load_should_match_the_oldest_first_answer_on_every_short_sequence() -> None:
    all_sequences: list[list[str]] = [[]]
    for _ in range(EXHAUSTIVE_SEQUENCE_LENGTH):
        all_sequences = [
            each_sequence + [each_kind] for each_sequence in all_sequences for each_kind in ALL_GENERATED_LINE_KINDS
        ]
        for each_sequence in all_sequences:
            assert _newest_first_load(each_sequence) == _oldest_first_load(each_sequence), each_sequence


def test_newest_first_load_should_match_the_oldest_first_answer_on_generated_long_sequences() -> None:
    generator = random.Random(GENERATED_SEQUENCE_SEED)
    all_answers: set[bool] = set()
    for _ in range(GENERATED_SEQUENCE_COUNT):
        all_lines = [
            generator.choice(ALL_GENERATED_LINE_KINDS) for _ in range(generator.randint(0, LONGEST_GENERATED_SEQUENCE))
        ]
        oldest_first_answer = _oldest_first_load(all_lines)
        assert _newest_first_load(all_lines) == oldest_first_answer, all_lines
        all_answers.add(oldest_first_answer)
    assert all_answers == {True, False}


def _lines_read_oldest_first(path: Path) -> list[str]:
    with open(path, encoding="utf-8", errors="replace") as transcript:
        return [each_line.removesuffix("\n") for each_line in transcript]


def _lines_read_newest_first(path: Path, block_size: int) -> list[str]:
    with open(path, "rb") as transcript:
        return list(transcript_lines_newest_first(transcript, "utf-8", "replace", block_size))


def test_lines_newest_first_should_return_each_line_of_the_file_newest_first(tmp_path: Path) -> None:
    transcript_path = tmp_path / "session.jsonl"
    for each_content in ALL_READER_CONTENTS:
        transcript_path.write_bytes(each_content)
        expected_lines = list(reversed(_lines_read_oldest_first(transcript_path)))
        all_answers = {
            each_block_size: _lines_read_newest_first(transcript_path, each_block_size)
            for each_block_size in ALL_TINY_BLOCK_SIZES
        }
        assert all_answers == dict.fromkeys(ALL_TINY_BLOCK_SIZES, expected_lines), each_content


def test_lines_newest_first_should_split_a_carriage_return_pair_across_a_block_edge(tmp_path: Path) -> None:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_bytes(b"ab\r\ncd\n")
    assert _lines_read_newest_first(transcript_path, 4) == ["cd", "ab"]
    transcript_path.write_bytes(b"ab\rcd\n")
    assert _lines_read_newest_first(transcript_path, 3) == ["cd", "ab"]
    transcript_path.write_bytes(b"ab\r\rcd")
    assert _lines_read_newest_first(transcript_path, 2) == ["cd", "", "ab"]


def _old_gate_answer(path: Path) -> bool:
    return _oldest_first_load(_lines_read_oldest_first(path))


def _new_gate_answer(path: Path, block_size: int) -> bool:
    with open(path, "rb") as transcript:
        all_lines = transcript_lines_newest_first(transcript, "utf-8", "replace", block_size)
        return is_skill_loaded_after_last_compaction_newest_first(all_lines, NEWEST_FIRST_SKILL_NAMES, NEWEST_FIRST_MARKERS)


def test_newest_first_scan_should_answer_as_the_old_gate_on_a_lone_carriage_return(tmp_path: Path) -> None:
    load, _, compaction = ALL_GENERATED_LINE_KINDS[:3]
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_bytes(f'{load}\n{compaction}\r{{"x":1}}\n'.encode())
    assert not _old_gate_answer(transcript_path)
    assert [_new_gate_answer(transcript_path, each_size) for each_size in ALL_SEQUENCE_BLOCK_SIZES] == [False] * 5


def _mixed_ending_transcript(generator: random.Random) -> bytes:
    all_lines = [generator.choice(ALL_GENERATED_LINE_KINDS) for _ in range(generator.randint(0, 12))]
    return "".join(each_line + generator.choice(ALL_LINE_ENDINGS) for each_line in all_lines).encode("utf-8")


def test_newest_first_scan_should_answer_as_the_old_gate_with_every_line_ending(tmp_path: Path) -> None:
    generator = random.Random(GENERATED_SEQUENCE_SEED)
    transcript_path = tmp_path / "session.jsonl"
    all_answers: set[bool] = set()
    for _ in range(MIXED_ENDING_SEQUENCE_COUNT):
        transcript_path.write_bytes(_mixed_ending_transcript(generator))
        old_answer = _old_gate_answer(transcript_path)
        all_new_answers = {_new_gate_answer(transcript_path, each_size) for each_size in ALL_SEQUENCE_BLOCK_SIZES}
        assert all_new_answers == {old_answer}, transcript_path.read_bytes()
        all_answers.add(old_answer)
    assert all_answers == {True, False}


def test_lines_newest_first_should_stop_between_blocks_once_told_to_stop(tmp_path: Path) -> None:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_bytes(b"a\nb\nc\n" + b"x" * 40)
    all_asks: list[int] = []

    def keeps_reading() -> bool:
        all_asks.append(len(all_asks))
        return len(all_asks) <= STOP_AFTER_BLOCK_COUNT

    with open(transcript_path, "rb") as transcript:
        assert list(transcript_lines_newest_first(transcript, "utf-8", "replace", 4, keeps_reading)) == []
        assert transcript.tell() == transcript_path.stat().st_size - 4
    transcript_path.write_bytes(b"a\nb\nc\n")
    all_asks.clear()
    with open(transcript_path, "rb") as transcript:
        assert list(transcript_lines_newest_first(transcript, "utf-8", "replace", 2, keeps_reading)) == ["c"]
    assert len(all_asks) == STOP_AFTER_BLOCK_COUNT + 1


def test_lines_newest_first_should_give_a_recent_load_before_reading_the_whole_file(tmp_path: Path) -> None:
    transcript_path = tmp_path / "session.jsonl"
    all_old_lines = [json.dumps({"type": "user", "message": {"content": f"line {each_index}"}}) for each_index in range(2000)]
    transcript_path.write_text("\n".join([*all_old_lines, _skill_entry("pr-lifecycle")]) + "\n", encoding="utf-8")
    with open(transcript_path, "rb") as transcript:
        all_lines = transcript_lines_newest_first(transcript, "utf-8", "replace", 256)
        assert is_skill_loaded_after_last_compaction_newest_first(all_lines, NEWEST_FIRST_SKILL_NAMES, NEWEST_FIRST_MARKERS)
        assert transcript.tell() > transcript_path.stat().st_size - 1024


SMALL_LINE_BYTE_CAP = 256
SMALL_COPY_BYTE_CAP = 4096
ALL_CAP_BLOCK_SIZES = (1, 5, 16, 1000)
ALL_COPY_BLOCK_SIZES = (1, 7, 64, 4096, 5000)


class UnseekableTranscript(io.BytesIO):
    def seekable(self) -> bool:
        return False

    def seek(self, *all_arguments: int) -> int:
        raise io.UnsupportedOperation("seek")


class EndSeekRefusedTranscript(io.BytesIO):
    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_END:
            raise OSError(errno.EINVAL, "Invalid argument")
        return super().seek(offset, whence)


def _capped_lines(
    transcript: BinaryIO, block_size: int, all_cuts: list[int], copy_byte_cap: int = SMALL_COPY_BYTE_CAP
) -> list[str]:
    caps = ScanCaps(SMALL_LINE_BYTE_CAP, copy_byte_cap, lambda: all_cuts.append(1))
    return list(transcript_lines_newest_first(transcript, "utf-8", "replace", block_size, caps=caps))


def _capped_load(content: bytes, block_size: int, all_cuts: list[int], is_seekable: bool = True) -> bool:
    transcript = io.BytesIO(content) if is_seekable else UnseekableTranscript(content)
    all_lines = _capped_lines(transcript, block_size, all_cuts)
    return is_skill_loaded_after_last_compaction_newest_first(all_lines, NEWEST_FIRST_SKILL_NAMES, NEWEST_FIRST_MARKERS)


def _load_line() -> bytes:
    return _skill_entry("pr-lifecycle").encode()


def test_load_older_than_a_line_over_the_cap_should_not_be_found_and_should_count_a_cut() -> None:
    content = _load_line() + b"\n" + b"y" * (SMALL_LINE_BYTE_CAP + 1) + b"\n"
    for each_block_size in ALL_CAP_BLOCK_SIZES:
        all_cuts: list[int] = []
        assert not _capped_load(content, each_block_size, all_cuts)
        assert all_cuts == [1]


def test_load_newer_than_a_line_over_the_cap_should_be_found() -> None:
    content = b"x\n" + b"y" * (SMALL_LINE_BYTE_CAP * 3) + b"\n" + _load_line() + b"\n"
    for each_block_size in ALL_CAP_BLOCK_SIZES:
        assert _capped_load(content, each_block_size, [])


def test_line_at_exactly_the_cap_should_be_read() -> None:
    content = _load_line() + b"\n" + b"y" * SMALL_LINE_BYTE_CAP + b"\r\n" + b"z" * SMALL_LINE_BYTE_CAP
    for each_block_size in ALL_CAP_BLOCK_SIZES:
        all_cuts: list[int] = []
        assert _capped_load(content, each_block_size, all_cuts)
        assert all_cuts == []


def test_unseekable_transcript_should_be_read_newest_first_after_a_forward_copy() -> None:
    content = b"a\nb\r\nc\rd"
    all_lines = transcript_lines_newest_first(UnseekableTranscript(content), "utf-8", "replace", 3)
    assert list(all_lines) == ["d", "c", "b", "a"]
    assert _capped_load(b"x\n" + _load_line() + b"\n", 7, [], is_seekable=False)


def test_unseekable_transcript_should_give_no_lines_once_the_forward_copy_is_stopped() -> None:
    all_asks: list[int] = []

    def keeps_reading() -> bool:
        all_asks.append(len(all_asks))
        return len(all_asks) <= STOP_AFTER_BLOCK_COUNT

    transcript = UnseekableTranscript(_load_line() + b"\n" + b"x" * 40)
    assert list(transcript_lines_newest_first(transcript, "utf-8", "replace", 4, keeps_reading)) == []


def test_unseekable_transcript_should_stop_the_copy_at_a_line_over_the_cap() -> None:
    all_cuts: list[int] = []
    content = b"y" * (SMALL_LINE_BYTE_CAP * 4) + b"\n" + _load_line() + b"\n"
    assert not _capped_load(content, 16, all_cuts, is_seekable=False)
    assert all_cuts == [1]


def _copy_sized_stream(total_bytes: int) -> bytes:
    load_part = _load_line() + b"\n"
    filler_line = b"f" * 99 + b"\n"
    filler = filler_line * ((total_bytes - len(load_part)) // len(filler_line) + 1)
    return (load_part + filler)[:total_bytes]


def test_transcript_whose_end_seek_fails_should_be_read_newest_first_after_a_forward_copy() -> None:
    content = b"x\n" + _load_line() + b"\nnewest"
    all_lines = _capped_lines(EndSeekRefusedTranscript(content), 7, [])
    assert all_lines[0] == "newest"
    assert is_skill_loaded_after_last_compaction_newest_first(all_lines, NEWEST_FIRST_SKILL_NAMES, NEWEST_FIRST_MARKERS)


def test_procfs_transcript_should_be_read_after_a_forward_copy() -> None:
    if sys.platform != "linux":
        pytest.skip("procfs is a Linux file system")
    with open("/proc/version", "rb") as transcript:
        all_lines = list(transcript_lines_newest_first(transcript, "utf-8", "replace"))
    assert all_lines[0].startswith("Linux version")


def test_stream_one_byte_over_the_copy_cap_should_give_no_lines_and_count_a_cut() -> None:
    content = _copy_sized_stream(SMALL_COPY_BYTE_CAP + 1)
    for each_block_size in ALL_COPY_BLOCK_SIZES:
        all_cuts: list[int] = []
        assert _capped_lines(UnseekableTranscript(content), each_block_size, all_cuts) == []
        assert all_cuts == [1]


def test_stream_at_exactly_the_copy_cap_should_be_read() -> None:
    content = _copy_sized_stream(SMALL_COPY_BYTE_CAP)
    for each_block_size in ALL_COPY_BLOCK_SIZES:
        all_cuts: list[int] = []
        all_lines = _capped_lines(EndSeekRefusedTranscript(content), each_block_size, all_cuts)
        assert all_cuts == []
        assert is_skill_loaded_after_last_compaction_newest_first(all_lines, NEWEST_FIRST_SKILL_NAMES, NEWEST_FIRST_MARKERS)
