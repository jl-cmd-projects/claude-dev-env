"""Tests for the PreToolUse hookSpecificOutput key names."""

from __future__ import annotations

from hooks_constants import pre_tool_use_output_keys


def test_keys_match_the_harness_pre_tool_use_output_field_names() -> None:
    assert {
        each_name: getattr(pre_tool_use_output_keys, each_name)
        for each_name in pre_tool_use_output_keys.__all__
    } == {
        "HOOK_SPECIFIC_OUTPUT_KEY": "hookSpecificOutput",
        "HOOK_EVENT_NAME_KEY": "hookEventName",
        "PERMISSION_DECISION_KEY": "permissionDecision",
        "UPDATED_INPUT_KEY": "updatedInput",
    }
