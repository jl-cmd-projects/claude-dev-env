"""Behavior tests for first-task deepening."""

from __future__ import annotations

import json
import os
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import deepen_first_prompt as deepen

from hooks_constants.deepen_first_prompt_constants import (
    DEEPEN_AGENT_MARKER,
    DEEPEN_MARKER,
    DEEPEN_OUTPUT_JSON,
    DEEPEN_OUTPUT_REWRITE,
    DEEPEN_REWRITE_ENV_VAR,
    DEEPEN_TURN_MARKER_SUFFIX,
    SKIP_DEEPEN_ENV_VAR,
    USER_PROMPT_SUBMIT_EVENT_NAME,
)
from hooks_constants.skill_loaded_reminder_constants import CLAUDE_SUBAGENT_PROMPT_PREFIX


def _payload(prompt: str, transcript_path: str | None = None) -> dict[str, object]:
    fields: dict[str, object] = {
        "hook_event_name": USER_PROMPT_SUBMIT_EVENT_NAME,
        "prompt": prompt,
        "session_id": "session-one",
    }
    if transcript_path is not None:
        fields["transcript_path"] = transcript_path
    return fields


def _run_main(payload: dict[str, object]) -> str:
    captured_stdout = StringIO()
    with patch("sys.stdin", StringIO(json.dumps(payload))), patch("sys.stdout", captured_stdout):
        deepen.main()
    return captured_stdout.getvalue()


def _user_transcript_line() -> str:
    return json.dumps({"type": "user", "message": {"role": "user", "content": "earlier task"}})


class TestSkipReasonFor:
    def test_should_skip_a_thanks_prompt(self) -> None:
        assert deepen.skip_reason_for(_payload("thanks")) is deepen.SkipReason.TRIVIAL

    def test_should_skip_a_yes_prompt(self) -> None:
        assert deepen.skip_reason_for(_payload("Yes")) is deepen.SkipReason.TRIVIAL

    def test_should_skip_status(self) -> None:
        assert deepen.skip_reason_for(_payload("status")) is deepen.SkipReason.TRIVIAL

    def test_should_skip_a_slash_command_other_than_deepen(self) -> None:
        assert deepen.skip_reason_for(_payload("/sr-loop")) is deepen.SkipReason.SLASH_COMMAND

    def test_should_skip_bare_deepen_with_no_task(self) -> None:
        assert deepen.skip_reason_for(_payload("/deepen")) is deepen.SkipReason.SLASH_COMMAND

    def test_should_allow_deepen_with_a_task(self) -> None:
        assert deepen.skip_reason_for(_payload("/deepen fix the login page")) is None

    def test_should_skip_a_loop_iteration(self) -> None:
        assert (
            deepen.skip_reason_for(_payload("/loop until the tests pass"))
            is deepen.SkipReason.LOOP_OR_HELPER
        )

    def test_should_skip_a_helper_report(self) -> None:
        assert (
            deepen.skip_reason_for(_payload("<task-notification> helper finished"))
            is deepen.SkipReason.LOOP_OR_HELPER
        )

    def test_should_skip_a_spawn_rewrite_prefix(self) -> None:
        prompt = CLAUDE_SUBAGENT_PROMPT_PREFIX + "\n\nReply leaf."
        assert deepen.skip_reason_for(_payload(prompt)) is deepen.SkipReason.SPAWN_REWRITE

    def test_should_skip_when_the_prompt_already_carries_the_marker(self) -> None:
        assert (
            deepen.skip_reason_for(_payload(f"{DEEPEN_MARKER}\n\nDo the job."))
            is deepen.SkipReason.MARKER_PRESENT
        )

    def test_should_skip_the_deepen_agent_prompt(self) -> None:
        prompt = f"{DEEPEN_AGENT_MARKER}\nAnswer the four deepening questions."
        assert deepen.skip_reason_for(_payload(prompt)) is deepen.SkipReason.DEEPEN_AGENT

    def test_should_skip_when_the_skip_flag_is_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(SKIP_DEEPEN_ENV_VAR, "1")
        assert (
            deepen.skip_reason_for(_payload("Add dark mode to settings"))
            is deepen.SkipReason.SKIP_FLAG
        )

    def test_should_skip_a_print_mode_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_CODE_NONINTERACTIVE", "true")
        assert (
            deepen.skip_reason_for(_payload("Add dark mode to settings"))
            is deepen.SkipReason.NONINTERACTIVE
        )

    def test_should_skip_codex_exec(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CODEX_EXEC", "1")
        assert (
            deepen.skip_reason_for(_payload("Add dark mode to settings"))
            is deepen.SkipReason.NONINTERACTIVE
        )

    def test_should_skip_turn_two_when_the_transcript_has_a_user_line(
        self, tmp_path: Path
    ) -> None:
        transcript_path = tmp_path / "session.jsonl"
        transcript_path.write_text(_user_transcript_line() + "\n", encoding="utf-8")
        assert (
            deepen.skip_reason_for(_payload("Add dark mode", str(transcript_path)))
            is deepen.SkipReason.LATER_TURN
        )

    def test_should_deepen_a_first_task(self) -> None:
        assert deepen.skip_reason_for(_payload("Add dark mode to the settings page")) is None


class TestDecideFirstPrompt:
    def test_should_emit_additional_context_with_the_four_answers_for_a_first_task(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(
            DEEPEN_REWRITE_ENV_VAR,
            (
                "Omitted: ship contrast tokens with the theme.\n"
                "Source: src/settings/theme.ts\n"
                "Methods: existing token file and a visual check.\n"
                "Proof: screenshot of the settings page in dark mode."
            ),
        )
        transcript_path = tmp_path / "fresh.jsonl"
        decision = deepen.decide_first_prompt(
            _payload("Add dark mode to the settings page", str(transcript_path))
        )
        assert isinstance(decision, deepen.Deepen)
        assert DEEPEN_MARKER in decision.rewritten_prompt
        assert "Omitted: ship contrast tokens" in decision.rewritten_prompt
        assert "src/settings/theme.ts" in decision.rewritten_prompt
        assert "visual check" in decision.rewritten_prompt
        assert "screenshot of the settings page" in decision.additional_context
        assert decision.additional_context.startswith(DEEPEN_MARKER)

    def test_should_keep_a_skip_silent_on_the_command_hook(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CDE_DEEPEN_OUTPUT", raising=False)
        assert _run_main(_payload("thanks")) == ""

    def test_should_write_a_turn_marker_so_turn_two_stays_silent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(DEEPEN_REWRITE_ENV_VAR, "Deeper task body")
        transcript_path = tmp_path / "fresh.jsonl"
        first_stdout = _run_main(_payload("Add dark mode to the settings page", str(transcript_path)))
        assert DEEPEN_MARKER in first_stdout
        marker_path = Path(str(transcript_path) + DEEPEN_TURN_MARKER_SUFFIX)
        assert marker_path.is_file()
        second_stdout = _run_main(_payload("and also the billing page", str(transcript_path)))
        assert second_stdout == ""

    def test_should_print_rewrite_text_for_the_claude_mod(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(DEEPEN_REWRITE_ENV_VAR, "Deeper task body")
        monkeypatch.setenv("CDE_DEEPEN_OUTPUT", DEEPEN_OUTPUT_REWRITE)
        transcript_path = tmp_path / "fresh.jsonl"
        printed = _run_main(_payload("Add dark mode to the settings page", str(transcript_path)))
        assert printed.startswith(DEEPEN_MARKER)
        assert "Deeper task body" in printed
        assert "hookSpecificOutput" not in printed

    def test_should_print_json_decisions_for_the_playtest(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(DEEPEN_REWRITE_ENV_VAR, "Deeper task body")
        monkeypatch.setenv("CDE_DEEPEN_OUTPUT", DEEPEN_OUTPUT_JSON)
        transcript_path = tmp_path / "fresh.jsonl"
        deepen_payload = json.loads(
            _run_main(_payload("Add dark mode to the settings page", str(transcript_path)))
        )
        assert deepen_payload["decision"] == "deepen"
        skip_payload = json.loads(_run_main(_payload("thanks")))
        assert skip_payload == {"decision": "skip", "reason": "trivial"}

    def test_should_stay_silent_when_the_claude_mod_is_on(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_directory = tmp_path / "claude-config"
        config_directory.mkdir()
        (config_directory / "settings.json").write_text(
            json.dumps({"enabledPlugins": {"deepen-first-prompt@claude-dev-env": True}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_directory))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDECODE", "1")
        monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
        monkeypatch.setenv(DEEPEN_REWRITE_ENV_VAR, "Deeper task body")
        transcript_path = tmp_path / "fresh.jsonl"
        assert _run_main(_payload("Add dark mode to the settings page", str(transcript_path))) == ""

    def test_should_emit_context_for_codex_when_the_claude_mod_is_on(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_directory = tmp_path / "claude-config"
        config_directory.mkdir()
        (config_directory / "settings.json").write_text(
            json.dumps({"enabledPlugins": {"deepen-first-prompt@claude-dev-env": True}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_directory))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.delenv("CLAUDECODE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
        monkeypatch.setenv(DEEPEN_REWRITE_ENV_VAR, "Deeper task body")
        transcript_path = tmp_path / "codex-fresh.jsonl"
        printed = _run_main(_payload("Add dark mode to the settings page", str(transcript_path)))
        envelope = json.loads(printed)
        assert envelope["hookSpecificOutput"]["hookEventName"] == USER_PROMPT_SUBMIT_EVENT_NAME
        assert "Deeper task body" in envelope["hookSpecificOutput"]["additionalContext"]

    def test_should_still_emit_context_in_a_cloud_session_when_the_mod_is_on(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_directory = tmp_path / "claude-config"
        config_directory.mkdir()
        (config_directory / "settings.json").write_text(
            json.dumps({"enabledPlugins": {"deepen-first-prompt@claude-dev-env": True}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_directory))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
        monkeypatch.setenv(DEEPEN_REWRITE_ENV_VAR, "Deeper task body")
        transcript_path = tmp_path / "fresh.jsonl"
        printed = _run_main(_payload("Add dark mode to the settings page", str(transcript_path)))
        envelope = json.loads(printed)
        assert envelope["hookSpecificOutput"]["hookEventName"] == USER_PROMPT_SUBMIT_EVENT_NAME
        assert "Deeper task body" in envelope["hookSpecificOutput"]["additionalContext"]


def test_should_strip_the_deepen_slash_before_rewriting() -> None:
    assert deepen.task_text_for_deepen("/deepen fix the login page") == "fix the login page"


def test_should_name_the_four_omitted_answers_in_the_default_rewrite() -> None:
    rewritten = deepen.expand_first_task("Add dark mode to the settings page")
    assert rewritten.startswith(DEEPEN_MARKER)
    assert "Add dark mode to the settings page" in rewritten
    assert "What a top person in that field would do that this prompt omitted." in rewritten
    assert "The raw source to start from." in rewritten
    assert "The methods and tools they would use." in rewritten
    assert "What besides the agent or Jon would show the result is right." in rewritten
