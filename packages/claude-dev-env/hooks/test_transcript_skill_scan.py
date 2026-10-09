"""Tests for skill invocation state across transcript compactions."""

import json
import sys
from pathlib import Path

HOOKS_DIRECTORY = Path(__file__).resolve().parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from transcript_skill_scan import (
    invokes_skill_with_argument,
    is_skill_loaded_after_last_compaction,
    skill_invocation_status,
)


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


def test_plugin_prefixed_claude_api_with_build_eval_should_count() -> None:
    assert _invokes_build_eval([_skill_entry_with_arguments("plugin:claude-api", "build-eval")])


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
