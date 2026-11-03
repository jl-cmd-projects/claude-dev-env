"""Tests for the pr-lifecycle SessionStart hook that puts a skill summary into the session context."""

import json
import sys
from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path
from unittest.mock import patch

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import pr_lifecycle_skill_session_start as injector
from hooks_constants.pr_lifecycle_skill_gate_constants import (
    SKILL_LOADED_CLOSING_TAG,
    SKILL_LOADED_MARKER,
    SKILL_CONTEXT_SUMMARY,
)

CONTEXT_CHARACTER_LIMIT = 1500


def _run_main(hook_payload: object) -> str:
    stdin_text = hook_payload if isinstance(hook_payload, str) else json.dumps(hook_payload)
    captured_stdout = StringIO()
    fake_stdin = TextIOWrapper(BytesIO(stdin_text.encode("utf-8")), encoding="utf-8")
    with patch("sys.stdin", fake_stdin), patch("sys.stdout", captured_stdout):
        injector.main()
    return captured_stdout.getvalue()


def _skill_file(tmp_path: Path) -> Path:
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("---\nname: pr-lifecycle\n---\n# Pull request lifecycle\n", encoding="utf-8")
    return skill_file


def test_skill_context_should_wrap_the_summary_in_the_loaded_tag(tmp_path: Path) -> None:
    assert injector.skill_context(_skill_file(tmp_path)) == (
        f"{SKILL_LOADED_MARKER}\n{SKILL_CONTEXT_SUMMARY}{SKILL_LOADED_CLOSING_TAG}"
    )


def test_skill_context_should_be_none_for_a_missing_file(tmp_path: Path) -> None:
    assert injector.skill_context(tmp_path / "missing.md") is None


def test_session_start_payload_should_inject_for_startup_and_compact(tmp_path: Path) -> None:
    skill_file = _skill_file(tmp_path)
    for each_source in ("startup", "compact"):
        payload = injector.session_start_payload(
            {"hook_event_name": "SessionStart", "source": each_source}, skill_file
        )
        assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert payload["hookSpecificOutput"]["additionalContext"] == injector.skill_context(skill_file)


def test_session_start_payload_should_be_empty_without_a_source(tmp_path: Path) -> None:
    payload = injector.session_start_payload({"hook_event_name": "UserPromptSubmit"}, _skill_file(tmp_path))
    assert payload == {}


def test_session_start_payload_should_be_empty_when_the_skill_file_is_missing(tmp_path: Path) -> None:
    payload = injector.session_start_payload(
        {"hook_event_name": "SessionStart", "source": "startup"}, tmp_path / "missing.md"
    )
    assert payload == {}


def test_packaged_context_should_fit_its_character_budget() -> None:
    payload = injector.session_start_payload({"hook_event_name": "SessionStart", "source": "startup"})
    context_text = payload["hookSpecificOutput"]["additionalContext"]
    assert context_text.startswith(SKILL_LOADED_MARKER)
    assert context_text.endswith(SKILL_LOADED_CLOSING_TAG)
    assert len(context_text) <= CONTEXT_CHARACTER_LIMIT


def test_summary_should_name_the_skill_tool_fallback_and_the_proof_sections() -> None:
    assert "Skill tool with pr-lifecycle" in SKILL_CONTEXT_SUMMARY
    assert "Proof in practice" in SKILL_CONTEXT_SUMMARY
    assert "Existing work" in SKILL_CONTEXT_SUMMARY


def test_main_should_print_the_context_payload_as_json() -> None:
    printed = json.loads(_run_main({"hook_event_name": "SessionStart", "source": "startup"}))
    assert printed["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert printed["hookSpecificOutput"]["additionalContext"].startswith(SKILL_LOADED_MARKER)


def test_main_should_stay_silent_for_a_payload_without_a_source() -> None:
    assert _run_main({"hook_event_name": "UserPromptSubmit"}) == ""


def test_hooks_json_should_register_the_injector_for_startup_and_compact() -> None:
    registration = json.loads((_HOOKS_ROOT / "hooks.json").read_text(encoding="utf-8"))
    command = "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/session/pr_lifecycle_skill_session_start.py"
    session_start_groups = registration["hooks"]["SessionStart"]
    for each_matcher in ("", "compact"):
        matching_commands = [
            each_hook["command"]
            for each_group in session_start_groups
            if each_group["matcher"] == each_matcher
            for each_hook in each_group["hooks"]
        ]
        assert command in matching_commands
