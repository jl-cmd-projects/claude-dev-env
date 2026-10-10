"""Tests for the shared PreToolUse allow-with-rewrite stdout emitter."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

from hooks_constants.pre_tool_use_allow_output import write_pre_tool_use_allow_to_stdout


def _emitted_payload(updated_tool_input: dict[str, object]) -> dict[str, object]:
    """Return the parsed payload the emitter wrote for one updated tool input."""
    captured_stdout = StringIO()
    with patch("sys.stdout", captured_stdout):
        write_pre_tool_use_allow_to_stdout(updated_tool_input)
    return json.loads(captured_stdout.getvalue())


def test_emitter_writes_an_allow_decision_carrying_the_updated_input() -> None:
    assert _emitted_payload({"command": "git status", "description": "check"}) == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": {"command": "git status", "description": "check"},
        }
    }


class _FlushRecordingStream(StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flushed_text: list[str] = []

    def flush(self) -> None:
        self.flushed_text.append(self.getvalue())
        super().flush()


def test_emitter_flushes_the_whole_payload_with_nested_input_intact() -> None:
    nested_input = {"command": "echo hi", "options": {"timeout": 5, "flags": ["-n"]}}
    recording_stream = _FlushRecordingStream()
    with patch("sys.stdout", recording_stream):
        write_pre_tool_use_allow_to_stdout(nested_input)

    assert recording_stream.flushed_text
    assert json.loads(recording_stream.flushed_text[-1])["hookSpecificOutput"]["updatedInput"] == nested_input
