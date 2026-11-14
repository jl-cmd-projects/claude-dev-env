"""Tests for advisor_rules_prompt: SessionStart hook that injects advisor consult rules."""

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
_ADVISOR_TOOL_DOC = _HOOKS_ROOT.parent / "docs" / "references" / "advisor-tool.md"
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import advisor_rules_prompt as starter

from hooks_constants.advisor_rules_prompt_constants import (
    ADVISOR_DISABLE_ENV_VAR,
    ALL_ADVISOR_RULE_SENTENCES,
    CLAUDE_CONFIG_DIR_ENV_VAR,
)


def _run_main(session_start_payload: object = "") -> str:
    stdin_text = (
        session_start_payload
        if isinstance(session_start_payload, str)
        else json.dumps(session_start_payload)
    )
    captured_stdout = StringIO()
    with patch("sys.stdin", StringIO(stdin_text)), patch("sys.stdout", captured_stdout):
        starter.main()
    return captured_stdout.getvalue()


def _session_start_payload(session_model: str | None) -> dict[str, str]:
    payload = {"hook_event_name": "SessionStart", "source": "startup"}
    if session_model is not None:
        payload["model"] = session_model
    return payload


@pytest.fixture
def config_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(CLAUDE_CONFIG_DIR_ENV_VAR, str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.delenv(ADVISOR_DISABLE_ENV_VAR, raising=False)
    return tmp_path


def _write_settings(config_directory: Path, settings: object) -> None:
    (config_directory / "settings.json").write_text(json.dumps(settings), encoding="utf-8")


class TestAdvisorRulesPrompt:
    def test_should_emit_rules_when_advisor_model_is_set(self, config_directory: Path) -> None:
        _write_settings(config_directory, {"advisorModel": "fable"})
        hook_output = json.loads(_run_main())["hookSpecificOutput"]
        assert hook_output["hookEventName"] == "SessionStart"
        for each_rule_sentence in ALL_ADVISOR_RULE_SENTENCES:
            assert each_rule_sentence in hook_output["additionalContext"]

    def test_should_name_the_configured_advisor_model(self, config_directory: Path) -> None:
        _write_settings(config_directory, {"advisorModel": "fable"})
        hook_output = json.loads(_run_main())["hookSpecificOutput"]
        assert "The advisor runs on `fable`." in hook_output["additionalContext"]

    @pytest.mark.parametrize(
        ("advisor_model", "session_model"),
        [
            ("fable", "claude-fable-5-2"),
            ("claude-fable-5-2", "claude-fable-5-2"),
            ("opus", "claude-opus-5-5[1m]"),
            ("claude-opus-4-7", "claude-opus-5"),
            ("claude-mythos-1", "claude-mythos-1"),
            ("Custom-Advisor", "custom-advisor"),
        ],
    )
    def test_should_emit_nothing_when_session_runs_on_the_advisor_model(
        self, config_directory: Path, advisor_model: str, session_model: str
    ) -> None:
        _write_settings(config_directory, {"advisorModel": advisor_model})
        assert _run_main(_session_start_payload(session_model)) == ""

    @pytest.mark.parametrize(
        ("advisor_model", "session_model"),
        [
            ("fable", "claude-opus-5-5"),
            ("opus", "claude-sonnet-5-5"),
            ("fable", "claude-mythos-1"),
            ("custom-advisor", "claude-fable-5-2"),
            ("custom-advisor", "claude-mythos-1"),
        ],
    )
    def test_should_emit_rules_when_session_runs_on_another_model(
        self, config_directory: Path, advisor_model: str, session_model: str
    ) -> None:
        _write_settings(config_directory, {"advisorModel": advisor_model})
        hook_output = json.loads(_run_main(_session_start_payload(session_model)))
        assert hook_output["hookSpecificOutput"]["hookEventName"] == "SessionStart"

    @pytest.mark.parametrize("session_start_payload", [_session_start_payload(None), "", "{not json", "[]"])
    def test_should_emit_rules_when_payload_names_no_model(
        self, config_directory: Path, session_start_payload: object
    ) -> None:
        _write_settings(config_directory, {"advisorModel": "fable"})
        hook_output = json.loads(_run_main(session_start_payload))
        assert hook_output["hookSpecificOutput"]["hookEventName"] == "SessionStart"

    def test_should_emit_rules_when_payload_model_is_not_a_string(
        self, config_directory: Path
    ) -> None:
        _write_settings(config_directory, {"advisorModel": "fable"})
        hook_output = json.loads(_run_main({"hook_event_name": "SessionStart", "model": 5}))
        assert hook_output["hookSpecificOutput"]["hookEventName"] == "SessionStart"

    def test_should_emit_nothing_when_advisor_model_is_missing(
        self, config_directory: Path
    ) -> None:
        _write_settings(config_directory, {"permissions": {}})
        assert _run_main() == ""

    def test_should_emit_nothing_while_the_session_prompts_mod_is_on(
        self, config_directory: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(config_directory))
        _write_settings(
            config_directory,
            {"advisorModel": "fable", "enabledPlugins": {"session-prompts@mods-marketplace": True}},
        )
        assert _run_main() == ""

    def test_should_emit_nothing_when_advisor_model_is_blank(self, config_directory: Path) -> None:
        _write_settings(config_directory, {"advisorModel": "  "})
        assert _run_main() == ""

    def test_should_emit_nothing_when_settings_file_is_absent(self, config_directory: Path) -> None:
        assert _run_main() == ""

    def test_should_emit_nothing_when_settings_file_is_not_json(
        self, config_directory: Path
    ) -> None:
        (config_directory / "settings.json").write_text("{not json", encoding="utf-8")
        assert _run_main() == ""

    def test_should_emit_nothing_when_environment_disables_the_advisor(
        self, config_directory: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_settings(config_directory, {"advisorModel": "fable"})
        monkeypatch.setenv(ADVISOR_DISABLE_ENV_VAR, "1")
        assert _run_main() == ""


class TestAdvisorRulesMatchTheDoc:
    @pytest.mark.parametrize("each_rule_sentence", ALL_ADVISOR_RULE_SENTENCES)
    def test_should_quote_each_sentence_from_advisor_tool_doc(
        self, each_rule_sentence: str
    ) -> None:
        doc_text = " ".join(_ADVISOR_TOOL_DOC.read_text(encoding="utf-8").split())
        assert each_rule_sentence in doc_text
