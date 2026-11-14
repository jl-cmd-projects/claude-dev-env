import json
from pathlib import Path

from routing_eval_support.grading import (
    ChildRun,
    child_runs,
    grade_case,
    is_allowed_pair,
    named_in_rule,
    routed_count,
    session_id,
)
from session_eval_support.grading import ToolCall

OPUS_ID = "claude-opus-5-5"


def _write_child(session_directory: Path, agent_id: str, all_pairs: list[tuple[str, str]]) -> None:
    subagents = session_directory / "subagents"
    subagents.mkdir(parents=True, exist_ok=True)
    all_lines = [
        json.dumps({"type": "assistant", "perTurnEffort": each_effort, "message": {"model": each_model}})
        for each_model, each_effort in all_pairs
    ]
    (subagents / f"agent-{agent_id}.jsonl").write_text("\n".join(['{"type": "user"}', *all_lines]), encoding="utf-8")
    (subagents / f"agent-{agent_id}.meta.json").write_text(json.dumps({"toolUseId": "toolu_" + agent_id, "agentType": "general-purpose"}), encoding="utf-8")


def test_allowed_pairs_follow_the_rule_table() -> None:
    assert is_allowed_pair(OPUS_ID, "medium")
    assert is_allowed_pair(OPUS_ID, "high")
    assert not is_allowed_pair(OPUS_ID, "xhigh")
    assert is_allowed_pair("claude-sonnet-5-5", "high")
    assert not is_allowed_pair("sonnet", "medium")
    assert is_allowed_pair("claude-fable-5-2", "low")
    assert not is_allowed_pair("fable", "xhigh")
    assert is_allowed_pair("claude-haiku-5-5", "max")
    assert not is_allowed_pair("gpt-5", "low")
    assert not is_allowed_pair(OPUS_ID, None)


def test_child_runs_read_every_turn_pair_and_the_meta(tmp_path: Path) -> None:
    _write_child(tmp_path / "-tmp-ws" / "s1", "a1", [(OPUS_ID, "medium"), (OPUS_ID, "medium")])
    _write_child(tmp_path / "-tmp-ws" / "s2", "b1", [(OPUS_ID, "xhigh")])

    all_children = child_runs(tmp_path, "s1")

    assert all_children == [ChildRun("toolu_a1", "general-purpose", ((OPUS_ID, "medium"), (OPUS_ID, "medium")))]


def test_grade_marks_a_session_with_no_spawn_as_vacuously_in_rule() -> None:
    assert grade_case([], [], 0) == {"in_rule": 1, "spawned": 0, "named_in_rule": 0, "routed": 0}


def test_grade_fails_in_rule_when_any_child_turn_is_outside_the_table() -> None:
    spawn = ToolCall("Agent", {"prompt": "x"})
    all_children = [ChildRun("t1", None, ((OPUS_ID, "medium"),)), ChildRun("t2", None, ((OPUS_ID, "medium"), (OPUS_ID, "max")))]

    assert grade_case([spawn, spawn], all_children, 0) == {"in_rule": 0, "spawned": 1, "named_in_rule": 0, "routed": 0}


def test_grade_counts_a_named_allowed_pair_and_a_routed_spawn() -> None:
    spawn = ToolCall("Task", {"model": "haiku", "effort": "max"})

    assert named_in_rule(spawn)
    assert grade_case([spawn], [ChildRun("t1", None, (("claude-haiku-5-5", "max"),))], 1) == {"in_rule": 1, "spawned": 1, "named_in_rule": 1, "routed": 1}


def test_a_child_with_no_assistant_turn_is_not_in_rule() -> None:
    assert grade_case([ToolCall("Agent", {})], [ChildRun("t1", None, ())], 0)["in_rule"] == 0


def test_routed_count_reads_only_hook_responses_that_change_the_input() -> None:
    changed = json.dumps({"hookSpecificOutput": {"updatedInput": {"effort": "medium"}}})
    all_events = [
        {"type": "system", "subtype": "hook_response", "output": changed},
        {"type": "system", "subtype": "hook_response", "output": ""},
        {"type": "system", "subtype": "hook_response", "output": "not json"},
        {"type": "system", "subtype": "hook_started", "output": changed},
    ]

    assert routed_count(all_events) == 1


def test_session_id_comes_from_the_first_event_that_has_one() -> None:
    assert session_id([{"type": "x"}, {"session_id": "abc"}, {"session_id": "zzz"}]) == "abc"
    assert session_id([{"type": "x"}]) is None
