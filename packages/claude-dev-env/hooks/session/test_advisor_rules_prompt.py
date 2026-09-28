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
    ADVISOR_RULES_PROMPT,
    ALL_ADVISOR_RULE_SENTENCES,
    CLAUDE_CONFIG_DIR_ENV_VAR,
)


def _run_main() -> str:
    captured_stdout = StringIO()
    with patch("sys.stdout", captured_stdout):
        starter.main()
    return captured_stdout.getvalue()


@pytest.fixture
def config_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(CLAUDE_CONFIG_DIR_ENV_VAR, str(tmp_path))
    monkeypatch.delenv(ADVISOR_DISABLE_ENV_VAR, raising=False)
    return tmp_path


def _write_settings(config_directory: Path, settings: object) -> None:
    (config_directory / "settings.json").write_text(json.dumps(settings), encoding="utf-8")


class TestAdvisorRulesPrompt:
    def test_should_emit_rules_when_advisor_model_is_set(self, config_directory: Path) -> None:
        _write_settings(config_directory, {"advisorModel": "fable"})
        hook_output = json.loads(_run_main())["hookSpecificOutput"]
        assert hook_output["hookEventName"] == "SessionStart"
        assert hook_output["additionalContext"] == ADVISOR_RULES_PROMPT

    def test_should_emit_nothing_when_advisor_model_is_missing(
        self, config_directory: Path
    ) -> None:
        _write_settings(config_directory, {"permissions": {}})
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
