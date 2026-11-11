import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import spawn_oversight_hook
from hooks_constants.spawn_oversight_hook_constants import (
    MISSING_BLOCKER_CLAUSE_REASON,
    MISSING_OUTCOME_REASON,
    SPAWN_OVERSIGHT_DIRECTIVE,
)

HOOK_SCRIPT = Path(__file__).resolve().parent / "spawn_oversight_hook.py"

ROUTE_ONLY_BRIEF = "Run X on the PC via RC and send me the output."
GOOD_BRIEF = (
    "Outcome: the user has X's output in this thread. Suggested route: RC on the PC. "
    "On a blocker: try the bridge, a cloud run, or another route that reaches the "
    "outcome; hand the user a step only when it needs their hands."
)
OUTCOME_ONLY_BRIEF = (
    "Outcome: the user has X's output in this thread. Suggested route: RC on the PC."
)
BLOCKER_ONLY_BRIEF = (
    "Run X on the PC via RC. On a blocker: try the bridge or a cloud run; hand the "
    "user a step only when it needs their hands."
)
MARKDOWN_BRIEF = (
    "Fix the parser.\n\n"
    "- **Outcome:** the parser test passes on main.\n"
    "- **On a blocker:** try another route; hand the user a step only when it needs "
    "their hands.\n"
)
EMPTY_MARKERS_BRIEF = "Do X.\nOutcome:\nOn a blocker:"

ALL_BRIEF_FIELDS_BY_TOOL_NAME = {
    "Agent": "prompt",
    "Task": "prompt",
    "Workflow": "script",
    "multi_agent_v1__spawn_agent": "message",
    "mcp__hearthbot__start_thread_session": "instructions",
    "mcp__hearthbot__start_rc_session": "instructions",
    "mcp__hearthbot__start_remote_control": "instructions",
}
WORKFLOW_DISPATCH_TOOL_NAME = "mcp__github__actions_run_trigger"


def _spawn_payload(tool_name: str, brief: str) -> dict[str, object]:
    if tool_name == WORKFLOW_DISPATCH_TOOL_NAME:
        return {
            "tool_name": tool_name,
            "tool_input": {"method": "run_workflow", "inputs": {"prompt": brief}},
        }
    return {
        "tool_name": tool_name,
        "tool_input": {ALL_BRIEF_FIELDS_BY_TOOL_NAME[tool_name]: brief},
    }


ALL_SPAWN_TOOL_NAMES = [*ALL_BRIEF_FIELDS_BY_TOOL_NAME, WORKFLOW_DISPATCH_TOOL_NAME]


def _directive_output() -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": SPAWN_OVERSIGHT_DIRECTIVE,
        }
    }


def _deny_reason(hook_output: dict[str, object] | None) -> str:
    assert hook_output is not None
    hook_specific_output = hook_output["hookSpecificOutput"]
    assert isinstance(hook_specific_output, dict)
    assert hook_specific_output["hookEventName"] == "PreToolUse"
    assert hook_specific_output["permissionDecision"] == "deny"
    reason = hook_specific_output["permissionDecisionReason"]
    assert isinstance(reason, str)
    return reason


@pytest.mark.parametrize("tool_name", ALL_SPAWN_TOOL_NAMES)
def test_a_route_only_brief_is_refused_on_every_spawn_tool(tool_name: str) -> None:
    reason = _deny_reason(
        spawn_oversight_hook.decide_hook_output(_spawn_payload(tool_name, ROUTE_ONLY_BRIEF))
    )
    assert MISSING_OUTCOME_REASON in reason
    assert MISSING_BLOCKER_CLAUSE_REASON in reason


@pytest.mark.parametrize("tool_name", ALL_SPAWN_TOOL_NAMES)
def test_a_brief_with_outcome_and_blocker_clause_passes_with_the_directive(
    tool_name: str,
) -> None:
    payload = _spawn_payload(tool_name, GOOD_BRIEF)
    assert spawn_oversight_hook.decide_hook_output(payload) == _directive_output()


@pytest.mark.parametrize("tool_name", ALL_SPAWN_TOOL_NAMES)
def test_an_outcome_without_a_blocker_clause_is_refused(tool_name: str) -> None:
    reason = _deny_reason(
        spawn_oversight_hook.decide_hook_output(_spawn_payload(tool_name, OUTCOME_ONLY_BRIEF))
    )
    assert MISSING_BLOCKER_CLAUSE_REASON in reason
    assert MISSING_OUTCOME_REASON not in reason


@pytest.mark.parametrize("tool_name", ALL_SPAWN_TOOL_NAMES)
def test_a_blocker_clause_without_an_outcome_is_refused(tool_name: str) -> None:
    reason = _deny_reason(
        spawn_oversight_hook.decide_hook_output(_spawn_payload(tool_name, BLOCKER_ONLY_BRIEF))
    )
    assert MISSING_OUTCOME_REASON in reason
    assert MISSING_BLOCKER_CLAUSE_REASON not in reason


def test_markers_with_no_text_after_them_are_refused() -> None:
    reason = _deny_reason(
        spawn_oversight_hook.decide_hook_output(_spawn_payload("Agent", EMPTY_MARKERS_BRIEF))
    )
    assert MISSING_OUTCOME_REASON in reason
    assert MISSING_BLOCKER_CLAUSE_REASON in reason


def test_markdown_bullet_markers_pass() -> None:
    payload = _spawn_payload("Agent", MARKDOWN_BRIEF)
    assert spawn_oversight_hook.decide_hook_output(payload) == _directive_output()


def test_a_missing_brief_field_is_refused() -> None:
    payload = {"tool_name": "Agent", "tool_input": {"description": "No prompt"}}
    assert MISSING_OUTCOME_REASON in _deny_reason(spawn_oversight_hook.decide_hook_output(payload))


def test_a_subagent_spawning_its_own_agent_is_checked() -> None:
    payload = {**_spawn_payload("Agent", ROUTE_ONLY_BRIEF), "agent_id": "agent_child"}
    assert MISSING_OUTCOME_REASON in _deny_reason(spawn_oversight_hook.decide_hook_output(payload))


def test_a_read_only_helper_spawn_is_checked() -> None:
    payload = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "Explore", "prompt": "Find X."},
    }
    assert MISSING_OUTCOME_REASON in _deny_reason(spawn_oversight_hook.decide_hook_output(payload))


def test_a_workflow_script_file_is_read_for_the_markers(tmp_path: Path) -> None:
    script_path = tmp_path / "workflow.js"
    script_path.write_text(f"agent({json.dumps(ROUTE_ONLY_BRIEF)})", encoding="utf-8")
    payload = {"tool_name": "Workflow", "tool_input": {"scriptPath": str(script_path)}}
    assert MISSING_OUTCOME_REASON in _deny_reason(spawn_oversight_hook.decide_hook_output(payload))


@pytest.mark.parametrize(
    "tool_input",
    [
        {"name": "saved-review"},
        {"resumeFromRunId": "wf_abc123"},
        {"scriptPath": "/nonexistent/workflow.js"},
    ],
)
def test_a_workflow_with_no_script_text_gets_the_directive(tool_input: dict[str, object]) -> None:
    payload = {"tool_name": "Workflow", "tool_input": tool_input}
    assert spawn_oversight_hook.decide_hook_output(payload) == _directive_output()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "tool_name": "mcp__github__actions_run_trigger",
            "tool_input": {"method": "cancel_workflow_run", "run_id": 1},
        },
        {
            "tool_name": "mcp__github__actions_run_trigger",
            "tool_input": {"method": "run_workflow", "inputs": {"head": "branch"}},
        },
        {"tool_name": "Bash", "tool_input": {"command": "ls"}},
        {"tool_name": "mcp__hearthbot__reply", "tool_input": {"text": "hi"}},
        {"tool_name": "Agent", "tool_input": "not an object"},
        {"tool_input": {"prompt": "Do X."}},
    ],
)
def test_other_calls_get_no_output(payload: dict[str, object]) -> None:
    assert spawn_oversight_hook.decide_hook_output(payload) is None


def _session_spawn(
    brief: str, transcript_path: Path, agent_id: str | None = None
) -> dict[str, object]:
    payload: dict[str, object] = {
        **_spawn_payload("Agent", brief),
        "session_id": "session_one",
        "transcript_path": str(transcript_path),
    }
    if agent_id is not None:
        payload["agent_id"] = agent_id
    return payload


@pytest.fixture
def session_transcript(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(json.dumps({"type": "user"}) + "\n", encoding="utf-8")
    return transcript_path


def _append_compaction(transcript_path: Path) -> None:
    with transcript_path.open("a", encoding="utf-8") as transcript:
        transcript.write(json.dumps({"type": "system", "subtype": "compact_boundary"}) + "\n")


def test_the_directive_shows_once_per_session_and_again_after_a_compaction(
    session_transcript: Path,
) -> None:
    decide = spawn_oversight_hook.decide_hook_output
    assert decide(_session_spawn(GOOD_BRIEF, session_transcript)) == _directive_output()
    assert decide(_session_spawn(GOOD_BRIEF, session_transcript)) is None
    _append_compaction(session_transcript)
    assert decide(_session_spawn(GOOD_BRIEF, session_transcript)) == _directive_output()
    assert decide(_session_spawn(GOOD_BRIEF, session_transcript)) is None


def test_a_brief_missing_a_clause_is_refused_on_every_spawn_of_a_session(
    session_transcript: Path,
) -> None:
    decide = spawn_oversight_hook.decide_hook_output
    assert MISSING_OUTCOME_REASON in _deny_reason(
        decide(_session_spawn(ROUTE_ONLY_BRIEF, session_transcript))
    )
    assert decide(_session_spawn(GOOD_BRIEF, session_transcript)) == _directive_output()
    assert MISSING_OUTCOME_REASON in _deny_reason(
        decide(_session_spawn(ROUTE_ONLY_BRIEF, session_transcript))
    )
    assert MISSING_BLOCKER_CLAUSE_REASON in _deny_reason(
        decide(_session_spawn(OUTCOME_ONLY_BRIEF, session_transcript))
    )


def test_a_subagent_gets_the_directive_on_its_own_first_spawn(
    session_transcript: Path,
) -> None:
    decide = spawn_oversight_hook.decide_hook_output
    assert decide(_session_spawn(GOOD_BRIEF, session_transcript)) == _directive_output()
    child_spawn = _session_spawn(GOOD_BRIEF, session_transcript, agent_id="agent_child")
    assert decide(child_spawn) == _directive_output()
    assert decide(child_spawn) is None


def test_replay_of_two_spawns_and_a_compaction_through_the_script(tmp_path: Path) -> None:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(json.dumps({"type": "user"}) + "\n", encoding="utf-8")
    environment = {**os.environ, "TMP": str(tmp_path), "TEMP": str(tmp_path), "TMPDIR": str(tmp_path)}

    def replay_spawn() -> str:
        return subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=json.dumps(_session_spawn(GOOD_BRIEF, transcript_path)),
            capture_output=True,
            text=True,
            env=environment,
            check=True,
        ).stdout

    first_stdout = replay_spawn()
    second_stdout = replay_spawn()
    _append_compaction(transcript_path)
    after_compaction_stdout = replay_spawn()
    assert json.loads(first_stdout) == _directive_output()
    assert second_stdout == ""
    assert json.loads(after_compaction_stdout) == _directive_output()


def _run_script(stdin_text: str) -> str:
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=stdin_text,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


@pytest.mark.parametrize("tool_name", ALL_SPAWN_TOOL_NAMES)
def test_script_refuses_the_route_only_brief(tool_name: str) -> None:
    stdout = _run_script(json.dumps(_spawn_payload(tool_name, ROUTE_ONLY_BRIEF)))
    assert MISSING_OUTCOME_REASON in _deny_reason(json.loads(stdout))


@pytest.mark.parametrize("tool_name", ALL_SPAWN_TOOL_NAMES)
def test_script_passes_the_good_brief(tool_name: str) -> None:
    stdout = _run_script(json.dumps(_spawn_payload(tool_name, GOOD_BRIEF)))
    assert json.loads(stdout) == _directive_output()


def test_script_prints_nothing_for_empty_stdin() -> None:
    assert _run_script("") == ""


def test_has_marked_clause_should_find_a_marker_mid_line_with_text_after_it() -> None:
    assert spawn_oversight_hook.has_marked_clause("Do X. Outcome: X is done.", ("outcome:",))
    assert not spawn_oversight_hook.has_marked_clause("Do X. Outcome: **", ("outcome:",))


def test_brief_gaps_should_name_each_missing_clause() -> None:
    assert spawn_oversight_hook.brief_gaps(GOOD_BRIEF) == []
    assert spawn_oversight_hook.brief_gaps(ROUTE_ONLY_BRIEF) == [
        MISSING_OUTCOME_REASON,
        MISSING_BLOCKER_CLAUSE_REASON,
    ]


def test_a_workflow_script_path_that_cannot_be_opened_gets_the_directive() -> None:
    payload = {"tool_name": "Workflow", "tool_input": {"scriptPath": "bad\u0000path.js"}}
    assert json.loads(_run_script(json.dumps(payload))) == _directive_output()


def _emitted_directive() -> str:
    stdout = _run_script(json.dumps(_spawn_payload("Agent", GOOD_BRIEF)))
    return json.loads(stdout)["hookSpecificOutput"]["additionalContext"]


def test_the_emitted_directive_runs_research_plan_and_fix_in_order() -> None:
    directive = _emitted_directive()
    research_position = directive.index("research, then a separate verifier checks the research")
    plan_position = directive.index("plan, then a separate verifier checks that the plan fixes the researched issue")
    fix_position = directive.index("implement, then a separate verifier reproduces the issue")
    assert research_position < plan_position < fix_position


def test_the_emitted_directive_reproduces_the_issue_before_it_confirms_the_fix() -> None:
    directive = _emitted_directive()
    assert directive.index("reproduces the issue on the old state") < directive.index(
        "confirms the fix on the new state"
    )


def test_the_emitted_directive_keeps_the_verifier_apart_from_the_worker() -> None:
    directive = _emitted_directive()
    assert "Spawn a fresh verifier agent for each check, never the agent that did the work" in directive
    assert "leave the worker's conclusion out" in directive


def test_the_emitted_directive_asks_before_new_scope_and_keeps_in_scope_work_moving() -> None:
    directive = _emitted_directive()
    assert "Ask the user once before you build new scope" in directive
    assert "keep in-scope work moving while the question waits" in directive


def test_the_emitted_directive_reports_only_verified_results() -> None:
    assert "Report as done only what a verifier passed, with its evidence" in _emitted_directive()


def test_the_emitted_directive_ends_the_chain_at_the_verifier() -> None:
    assert "A verifier's check ends the chain and gets no verifier of its own" in _emitted_directive()


def test_the_emitted_directive_commits_each_passed_piece_as_its_own_stack_level() -> None:
    directive = _emitted_directive()
    assert "When a piece's verifier passes and the brief allows commits, commit that piece alone as its own stack level" in directive
    assert "a piece that depends on it goes on top" in directive
    assert "an independent piece goes on its own branch from trunk" in directive
    assert "Otherwise hand the piece back uncommitted and say so." in directive
    assert directive.index("confirms the fix on the new state") < directive.index("commit that piece alone")


def test_the_emitted_directive_stays_context_only_and_inside_its_budget() -> None:
    directive = _emitted_directive()
    assert len(directive) < 1500
    assert "deny" not in directive.lower()
