"""Behavior tests for the auto mode denial approval advisor."""

from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

import pytest

advisory_directory = str(Path(__file__).resolve().parent)
if advisory_directory not in sys.path:
    sys.path.insert(0, advisory_directory)
import auto_mode_denial_quick_fix

PHRASE_PATTERN = re.compile(
    r"^I approve this one action: (?P<action>.+?)\. I accept the risk that (?P<risk>.+?)\.$"
)
FENCED_PHRASE_PATTERN = re.compile(r"```\n(I approve this one action: [^\n]+)\n```")


@pytest.fixture(autouse=True)
def isolated_state_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    state_directory = tmp_path / "state"
    monkeypatch.setattr(
        auto_mode_denial_quick_fix, "state_directory", lambda: state_directory
    )
    return state_directory


def _denial_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "session_id": "session-1",
        "hook_event_name": "PermissionDenied",
        "tool_name": "Bash",
        "tool_input": {
            "command": "git push --force-with-lease origin skill/role-templates",
            "description": "Force push",
        },
        "tool_use_id": "toolu_1",
        "reason": "[Git Destructive] force push rewrites remote history",
    }
    payload.update(overrides)
    return payload


def _stop_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "session_id": "session-1",
        "hook_event_name": "Stop",
        "stop_hook_active": False,
    }
    payload.update(overrides)
    return payload


def _run_main(
    payload_text: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> str:
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload_text))
    assert auto_mode_denial_quick_fix.main() == 0
    return capsys.readouterr().out


def _context_of(stdout_text: str) -> str:
    return json.loads(stdout_text)["hookSpecificOutput"]["additionalContext"]


def _phrase_of(context_text: str) -> str:
    all_phrases = FENCED_PHRASE_PATTERN.findall(context_text)
    assert len(all_phrases) == 1
    return all_phrases[0]


def test_should_read_the_rule_from_the_reason_field() -> None:
    context_text = auto_mode_denial_quick_fix.denial_context(_denial_payload())
    assert "[Git Destructive]" in context_text
    risk_clause = PHRASE_PATTERN.match(_phrase_of(context_text)).group("risk")
    assert "overwritten" in risk_clause


def test_should_ignore_the_old_denial_reason_field() -> None:
    payload = _denial_payload(reason="Blocked by classifier")
    payload["denial_reason"] = "[Irreversible Local Destruction] stale field"
    context_text = auto_mode_denial_quick_fix.denial_context(payload)
    assert "Irreversible Local Destruction" not in context_text


def test_should_write_one_phrase_naming_program_target_and_risk() -> None:
    phrase = _phrase_of(auto_mode_denial_quick_fix.denial_context(_denial_payload()))
    shape_match = PHRASE_PATTERN.match(phrase)
    assert shape_match is not None
    assert "git, the program that tracks code versions" in shape_match.group("action")
    assert "skill/role-templates" in shape_match.group("action")
    assert phrase.count("I approve this one action:") == 1


def test_should_keep_the_start_and_the_target_of_a_long_command() -> None:
    long_command = "cd /tmp/work && " + "git status && " * 20 + "git push --force origin feat/target-branch"
    summary = auto_mode_denial_quick_fix.action_summary_from({"command": long_command})
    assert len(summary) == 160
    assert summary.startswith("cd /tmp/work")
    assert summary.endswith("origin feat/target-branch")
    assert "..." in summary


def test_should_fall_back_to_the_program_risk_when_the_reason_names_no_rule() -> None:
    payload = _denial_payload(
        tool_input={"command": 'cat "Run Theme Submissions.bat" | head -60'},
        reason=(
            "The server-side auto mode classifier judged this action dangerous "
            "(it gave no explanation)"
        ),
    )
    risk_clause = PHRASE_PATTERN.match(
        _phrase_of(auto_mode_denial_quick_fix.denial_context(payload))
    ).group("risk")
    assert "passwords" in risk_clause


def test_should_name_a_helper_agent_and_tell_it_to_return_the_phrase() -> None:
    context_text = auto_mode_denial_quick_fix.denial_context(
        _denial_payload(agent_id="agent-7", agent_type="general-purpose")
    )
    assert "a helper agent working for Claude" in _phrase_of(context_text)
    assert "return the code block to your parent agent unchanged" in context_text


def test_should_ask_for_a_task_card_with_the_fixed_rule_target() -> None:
    context_text = auto_mode_denial_quick_fix.denial_context(_denial_payload())
    assert "TaskCreate" in context_text
    assert "autoMode.allow" in context_text
    assert "packages/claude-dev-env/settings.json" in context_text


def test_should_keep_banned_style_out_of_every_output() -> None:
    context_text = auto_mode_denial_quick_fix.denial_context(
        _denial_payload(reason="[Data Exfiltration] sends data out")
    )
    assert chr(0x2014) not in context_text
    assert not re.search(r"\breal(ly)?\b", context_text)


def test_should_skip_the_phrase_when_the_classifier_gave_no_verdict() -> None:
    context_text = auto_mode_denial_quick_fix.denial_context(
        _denial_payload(reason="Classifier unavailable")
    )
    assert "I approve this one action" not in context_text
    assert "TaskCreate" not in context_text


def test_should_replay_the_denial_once_at_the_end_of_the_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _run_main(json.dumps(_denial_payload()), monkeypatch, capsys)
    stop_output = json.loads(_run_main(json.dumps(_stop_payload()), monkeypatch, capsys))
    assert stop_output["hookSpecificOutput"]["hookEventName"] == "Stop"
    _phrase_of(stop_output["hookSpecificOutput"]["additionalContext"])
    assert _run_main(json.dumps(_stop_payload()), monkeypatch, capsys) == ""


def test_should_replay_a_subagent_denial_only_at_that_subagent_stop(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _run_main(json.dumps(_denial_payload(agent_id="agent-7")), monkeypatch, capsys)
    assert _run_main(json.dumps(_stop_payload()), monkeypatch, capsys) == ""
    subagent_stop_output = _run_main(
        json.dumps(_stop_payload(hook_event_name="SubagentStop", agent_id="agent-7")),
        monkeypatch,
        capsys,
    )
    assert (
        json.loads(subagent_stop_output)["hookSpecificOutput"]["hookEventName"]
        == "SubagentStop"
    )


def test_should_replay_every_denial_of_the_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _run_main(json.dumps(_denial_payload()), monkeypatch, capsys)
    _run_main(
        json.dumps(_denial_payload(tool_input={"command": "gh pr ready 5510"})),
        monkeypatch,
        capsys,
    )
    context_text = _context_of(_run_main(json.dumps(_stop_payload()), monkeypatch, capsys))
    assert len(FENCED_PHRASE_PATTERN.findall(context_text)) == 2


def test_should_print_the_denial_context_on_the_denial_event(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stdout_text = _run_main(json.dumps(_denial_payload()), monkeypatch, capsys)
    _phrase_of(_context_of(stdout_text))
    assert "```" not in json.loads(stdout_text)["systemMessage"]


@pytest.mark.parametrize(
    "payload_text",
    [
        "",
        "not json",
        "{}",
        "[]",
        json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Bash"}),
        json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash"}),
    ],
)
def test_should_stay_quiet_on_anything_but_a_denial_or_a_stop(
    payload_text: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run_main(payload_text, monkeypatch, capsys) == ""
