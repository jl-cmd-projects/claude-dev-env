"""Behavior tests for the auto mode denial quick-fix advisor."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

advisory_directory = str(Path(__file__).resolve().parent)
if advisory_directory not in sys.path:
    sys.path.insert(0, advisory_directory)
import auto_mode_denial_quick_fix


def _denial_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "hook_event_name": "PermissionDenied",
        "tool_name": "mcp__github__resolve_review_thread",
        "tool_input": {"threadId": "PRRT_abc"},
        "denial_reason": "[Security Weaken] resolving review threads bypasses review",
        "classifier_verdict": "deny",
    }
    payload.update(overrides)
    return payload


def test_should_name_the_bracketed_rule() -> None:
    assert (
        auto_mode_denial_quick_fix.rule_label_from("[Git Destructive] force") == "Git Destructive"
    )


def test_should_fall_back_when_the_reason_has_no_label() -> None:
    assert auto_mode_denial_quick_fix.rule_label_from("Blocked by classifier") == "unnamed rule"


def test_should_summarize_a_bash_call_by_its_command() -> None:
    summary = auto_mode_denial_quick_fix.action_summary_from(
        {"command": "git push\n --force origin x"}
    )
    assert summary == "git push --force origin x"


def test_should_cut_a_long_summary_to_the_limit() -> None:
    summary = auto_mode_denial_quick_fix.action_summary_from({"command": "x" * 500})
    assert len(summary) == 160
    assert summary.endswith("...")


def test_should_escape_single_quotes_in_the_powershell_entry() -> None:
    block = auto_mode_denial_quick_fix.powershell_block_for("it's allowed")
    assert "$entry = 'it''s allowed'" in block
    assert "$allowList.Add('$defaults')" in block


def test_should_propose_rule_entry_and_block_for_a_classifier_denial() -> None:
    hook_output = auto_mode_denial_quick_fix.build_hook_output(_denial_payload())
    context_text = hook_output["hookSpecificOutput"]["additionalContext"]
    assert "rule [Security Weaken]" in context_text
    assert (
        "Security Weaken exception: mcp__github__resolve_review_thread calls like" in context_text
    )
    assert "```powershell" in context_text
    assert "retry" not in hook_output["hookSpecificOutput"]
    assert hook_output["systemMessage"].startswith(
        "Auto mode blocked mcp__github__resolve_review_thread"
    )


def test_should_omit_the_block_when_no_verdict_exists() -> None:
    payload = _denial_payload(denial_reason="classifier unavailable")
    del payload["classifier_verdict"]
    context_text = auto_mode_denial_quick_fix.build_hook_output(payload)["hookSpecificOutput"][
        "additionalContext"
    ]
    assert "no classifier verdict" in context_text
    assert "powershell" not in context_text


def test_should_print_the_output_from_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_denial_payload())))
    assert auto_mode_denial_quick_fix.main() == 0
    assert (
        json.loads(capsys.readouterr().out)["hookSpecificOutput"]["hookEventName"]
        == "PermissionDenied"
    )


def test_should_stay_quiet_on_malformed_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert auto_mode_denial_quick_fix.main() == 0
    assert capsys.readouterr().out == ""


def test_should_write_the_entry_with_defaults_when_powershell_runs(tmp_path: Path) -> None:
    block = (
        auto_mode_denial_quick_fix.powershell_block_for("it's allowed")
        .replace("claude auto-mode config", "")
        .replace("Join-Path $HOME", f"Join-Path '{tmp_path}'")
    )
    subprocess.run(["pwsh", "-NoProfile", "-Command", block], check=True)
    written_settings = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert written_settings["autoMode"]["allow"] == ["$defaults", "it's allowed"]
