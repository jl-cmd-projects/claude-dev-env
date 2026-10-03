"""Tests for skill invocation state across transcript compactions."""

import json
import sys
from pathlib import Path

HOOKS_DIRECTORY = Path(__file__).resolve().parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from transcript_skill_scan import is_skill_loaded_after_last_compaction


def _skill_entry(name: str) -> str:
    return json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": name}}]}}
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
