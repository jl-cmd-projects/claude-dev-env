"""Tests for the hookSpecificOutput key names."""

from __future__ import annotations

from hooks_constants import hook_specific_output_keys


def test_keys_match_the_harness_hook_specific_output_field_names() -> None:
    assert {
        each_name: getattr(hook_specific_output_keys, each_name)
        for each_name in hook_specific_output_keys.__all__
    } == {
        "HOOK_SPECIFIC_OUTPUT_KEY": "hookSpecificOutput",
        "HOOK_EVENT_NAME_KEY": "hookEventName",
        "PERMISSION_DECISION_KEY": "permissionDecision",
        "UPDATED_INPUT_KEY": "updatedInput",
    }
