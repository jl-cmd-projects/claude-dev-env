import importlib.util
import json
from pathlib import Path

import pytest

from routing_eval_support.grading import ChildRun
from session_eval_support.session import SessionRun

flow_directory = Path(__file__).resolve().parent
run_specification = importlib.util.spec_from_file_location("routing_run", flow_directory / "run.py")
routing_run = importlib.util.module_from_spec(run_specification)
run_specification.loader.exec_module(routing_run)

OPUS_ID = "claude-opus-5-5"


def test_hook_settings_bytes_register_the_hook_only_when_the_variant_has_one() -> None:
    assert routing_run.hook_settings_bytes([]) == {}
    settings_bytes = routing_run.hook_settings_bytes([["Agent|Task", "packages/claude-dev-env/hooks/routing/subagent_effort_route_hook.py"]])
    registered = json.loads(settings_bytes[".claude/settings.json"])["hooks"]["PreToolUse"][0]
    assert registered["matcher"] == "Agent|Task"
    assert registered["hooks"][0]["command"].endswith("subagent_effort_route_hook.py")


def test_extra_words_allow_spawns_and_show_hook_events() -> None:
    assert routing_run.unbrokered_words(Path("r"), ["claude", "-p"]) == ["claude", "-p", "--allowedTools", "Agent,Task,Read,Grep,Glob", "--include-hook-events"]


def test_scored_row_grades_from_the_children_and_the_hook_events() -> None:
    changed = json.dumps({"hookSpecificOutput": {"updatedInput": {"model": "opus", "effort": "medium"}}})
    all_events = [
        {"type": "system", "subtype": "init", "session_id": "s1"},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Agent", "input": {"model": "opus", "effort": "xhigh"}}]}},
        {"type": "system", "subtype": "hook_response", "output": changed},
        {"type": "result", "subtype": "success", "modelUsage": {OPUS_ID: {}}},
    ]
    session = SessionRun(all_events, 4.04, 0, {})
    settings = routing_run.SessionSettings(OPUS_ID, "high", 8, 600)

    row = routing_run._scored_row({"id": "o01", "prompt": "p", "group": "asks-out-of-rule"}, 0, session, [ChildRun("t", None, ((OPUS_ID, "medium"),))], "dig", settings)

    assert row["grade"] == {"in_rule": 1, "spawned": 1, "named_in_rule": 0, "routed": 1}
    assert row["meta"]["spawns"] == [{"model": "opus", "effort": "xhigh", "named_in_rule": False}]
    assert row["meta"]["run_digest"] == "dig"


def test_summary_rates_count_only_spawning_rows_after_the_spawn_rate() -> None:
    all_rows = [
        {"tags": ["g"], "grade": {"in_rule": 1, "spawned": 0, "named_in_rule": 0, "routed": 0}},
        {"tags": ["g"], "grade": {"in_rule": 0, "spawned": 1, "named_in_rule": 0, "routed": 0}},
    ]

    all_lines = routing_run.summary_lines(all_rows, 1)

    assert all_lines[0].startswith("all: spawned 1/2")
    assert "in_rule 0/1" in all_lines[0]
    assert all_lines[-1] == "errors 1"


def test_session_children_reads_the_child_transcripts_of_the_stream_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    subagents = tmp_path / "-tmp-ws" / "s9" / "subagents"
    subagents.mkdir(parents=True)
    (subagents / "agent-a.jsonl").write_text(json.dumps({"type": "assistant", "effort": "medium", "message": {"model": OPUS_ID}}), encoding="utf-8")
    monkeypatch.setattr(routing_run, "CLAUDE_PROJECTS_DIRECTORY", tmp_path)

    assert routing_run.session_children(SessionRun([{"session_id": "s9"}], 1.0, 0, {})) == [ChildRun(None, None, ((OPUS_ID, "medium"),))]
    assert routing_run.session_children(SessionRun([], 1.0, 0, {})) == []
