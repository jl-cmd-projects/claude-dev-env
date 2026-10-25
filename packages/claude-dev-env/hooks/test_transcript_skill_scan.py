"""Tests for skill invocation state across transcript compactions."""

import json
import sys
from pathlib import Path

HOOKS_DIRECTORY = Path(__file__).resolve().parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from transcript_skill_scan import (
    TranscriptToolCall,
    invokes_skill_with_argument,
    is_skill_loaded_after_last_compaction,
    is_skill_loaded_since_last_prompt,
    skill_invocation_status,
    tool_calls_since_last_prompt,
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
        _tool_result_entry("toolu_skill", False),
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
    loaded = [_skill_entry("pr-lifecycle"), _tool_result_entry("toolu_skill", False)]
    assert skill_invocation_status(loaded, ("pr-lifecycle",), ()) == (True, True)
    assert skill_invocation_status([*loaded, compaction], ("pr-lifecycle",), ()) == (True, False)
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


def _tool_result_entry(tool_use_id: str, is_error: bool) -> str:
    return json.dumps(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": "Skill pr-lifecycle cannot be used" if is_error else "Launching skill",
                        "is_error": is_error,
                    }
                ]
            },
        }
    )


def test_should_not_count_a_refused_skill_load_after_the_last_compaction() -> None:
    lines = [_skill_entry("pr-lifecycle", "toolu_refused"), _tool_result_entry("toolu_refused", True)]
    assert not is_skill_loaded_after_last_compaction(lines, ("pr-lifecycle",), ())
    assert skill_invocation_status(lines, ("pr-lifecycle",), ()) == (False, False)


def test_should_count_a_successful_load_after_a_refused_one() -> None:
    lines = [
        _skill_entry("pr-lifecycle", "toolu_refused"),
        _tool_result_entry("toolu_refused", True),
        _skill_entry("pr-lifecycle", "toolu_loaded"),
        _tool_result_entry("toolu_loaded", False),
    ]
    assert is_skill_loaded_after_last_compaction(lines, ("pr-lifecycle",), ())


def test_should_not_count_a_load_whose_result_has_not_arrived() -> None:
    assert not is_skill_loaded_after_last_compaction(
        [_skill_entry("pr-lifecycle", "toolu_pending")], ("pr-lifecycle",), ()
    )
