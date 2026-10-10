"""Tests for the shared PostToolUse context emitter."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from hooks_constants.post_tool_use_context import write_post_tool_use_context_to_stdout
from hooks_constants.test_stdout_flush_support import FlushRecordingStream


def test_should_write_the_post_tool_use_payload_carrying_the_context_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_post_tool_use_context_to_stdout("=== PR DONE CHECKLIST ===")

    assert json.loads(capsys.readouterr().out) == {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "=== PR DONE CHECKLIST ===",
        }
    }


def test_should_flush_the_whole_payload_so_the_dispatcher_reads_it_before_exit() -> None:
    recording_stream = FlushRecordingStream()
    with patch("sys.stdout", recording_stream):
        write_post_tool_use_context_to_stdout('line one\nline "two"')

    assert recording_stream.flushed_text
    assert json.loads(recording_stream.flushed_text[-1])["hookSpecificOutput"]["additionalContext"] == (
        'line one\nline "two"'
    )
