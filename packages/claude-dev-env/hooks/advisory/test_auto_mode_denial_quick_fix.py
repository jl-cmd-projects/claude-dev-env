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


@pytest.fixture(autouse=True)
def scratch_config_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_directory = tmp_path / "claude-config"
    config_directory.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_directory))
    monkeypatch.setenv("HOME", str(config_directory))
    return config_directory


def _denial_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "session_id": "session-1",
        "transcript_path": "/scratch/transcript.jsonl",
        "cwd": "/scratch",
        "permission_mode": "auto",
        "hook_event_name": "PermissionDenied",
        "tool_name": "mcp__github__resolve_review_thread",
        "tool_input": {"threadId": "PRRT_abc"},
        "tool_use_id": "toolu_1",
        "reason": "[Security Weaken] resolving review threads bypasses review",
    }
    payload.update(overrides)
    return payload


def _hook_output_from_stdin(
    payload: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, object]:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert auto_mode_denial_quick_fix.main() == 0
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize(
    ("reason", "expected_rule_name", "expects_allow_block"),
    [
        ("[Auto-Mode Bypass]", "Auto-Mode Bypass", True),
        ("[Git Destructive] force push to a shared branch", "Git Destructive", True),
        (
            "Unauthorized Persistence, because the script adds a cron line.",
            "Unauthorized Persistence",
            True,
        ),
        (
            "the command force-cancels workflow runs in bulk.",
            "the command force-cancels workflow runs in bulk",
            True,
        ),
        (
            "Force Push to a shared branch is destructive.",
            "Force Push to a shared branch is destructive",
            True,
        ),
        (
            "the script's [0] entry rewrites every workflow file in the repository"
            " and then deletes the backup copies. It runs nightly.",
            "the scripts 0 entry rewrites every workflow file in the repository and then d...",
            True,
        ),
        (
            "Auto mode could not evaluate this action because the transcript was too long.",
            "unnamed rule",
            False,
        ),
        ("Classifier unavailable", "unnamed rule", False),
    ],
)
def test_should_name_the_rule_and_branch_for_each_recorded_reason(
    reason: str,
    expected_rule_name: str,
    expects_allow_block: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hook_output = _hook_output_from_stdin(
        _denial_payload(tool_name="Bash", tool_input={"command": "gh run cancel 1"}, reason=reason),
        monkeypatch,
        capsys,
    )
    context_text = hook_output["hookSpecificOutput"]["additionalContext"]
    assert hook_output["systemMessage"] == (
        f"Auto mode blocked Bash [{expected_rule_name}]. Claude will propose a quick fix."
    )
    assert f"Denial reason: {reason}" in context_text
    assert ("```powershell" in context_text) is expects_allow_block
    if expects_allow_block:
        assert f"rule [{expected_rule_name}]" in context_text
        assert f"{expected_rule_name} exception: Bash calls like `gh run cancel 1`" in context_text
    else:
        assert "no classifier verdict" in context_text


def test_should_parse_a_bare_label_with_its_prose() -> None:
    assert auto_mode_denial_quick_fix.parse_denial_reason(
        "Unauthorized Persistence, because the script adds a cron line."
    ) == auto_mode_denial_quick_fix.DenialReason(
        rule_label="Unauthorized Persistence",
        has_verdict=True,
        prose="because the script adds a cron line.",
    )


def test_should_parse_a_missing_reason_as_no_verdict() -> None:
    assert auto_mode_denial_quick_fix.parse_denial_reason("") == (
        auto_mode_denial_quick_fix.DenialReason(rule_label=None, has_verdict=False, prose="")
    )


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
    payload = _denial_payload(reason="classifier unavailable")
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


@pytest.mark.parametrize(
    ("reason", "expected_rule_label"),
    [
        ("[Don't Touch] edits a guarded file", "Dont Touch"),
        (
            "[Label'; Remove-Item -Recurse C:\\ #] wipes the drive",
            "Label Remove-Item -Recurse C",
        ),
        ("[Line One\nLine Two] splits the command", "Line One Line Two"),
        ("[\x1b[31mRed `$(whoami)` \"q\"] colours the terminal", "31mRed whoami q"),
        ("Data\nExfiltration, because it posts the file.", "Data Exfiltration"),
    ],
)
def test_should_keep_only_safe_characters_in_a_parsed_label(
    reason: str, expected_rule_label: str
) -> None:
    assert auto_mode_denial_quick_fix.parse_denial_reason(reason).rule_label == expected_rule_label


def test_should_parse_a_label_with_no_safe_characters_as_prose() -> None:
    assert auto_mode_denial_quick_fix.parse_denial_reason("[';#] force push") == (
        auto_mode_denial_quick_fix.DenialReason(
            rule_label=None, has_verdict=True, prose="[';#] force push"
        )
    )


def test_should_double_every_quote_in_the_rule_wording_command() -> None:
    assert auto_mode_denial_quick_fix.rule_wording_command_for("Don't \u2019Touch") == (
        "claude auto-mode defaults --label 'Don''t \u2019\u2019Touch'"
    )


def test_should_draft_the_rule_wording_command_without_a_label_for_prose() -> None:
    assert auto_mode_denial_quick_fix.rule_wording_command_for(None) == (
        "claude auto-mode defaults"
    )


def test_should_pass_a_hostile_label_to_claude_as_one_argument(tmp_path: Path) -> None:
    context_text = auto_mode_denial_quick_fix.build_hook_output(
        _denial_payload(reason="[Label'; Remove-Item -Recurse C:\\ #\n$(whoami)] wipes the drive")
    )["hookSpecificOutput"]["additionalContext"]
    drafted_line = context_text.splitlines()[-1].removeprefix("Read the rule wording with: ")
    script_path = tmp_path / "drafted_line.ps1"
    script_path.write_text(
        "function claude { $args | ConvertTo-Json -Compress }\n" + drafted_line + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(script_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout) == [
        "auto-mode",
        "defaults",
        "--label",
        "Label Remove-Item -Recurse C whoami",
    ]


def test_should_draft_the_rule_wording_command_without_a_label_for_a_prose_reason() -> None:
    context_text = auto_mode_denial_quick_fix.build_hook_output(
        _denial_payload(reason="the command force-cancels workflow runs in bulk.")
    )["hookSpecificOutput"]["additionalContext"]
    assert "--label" not in context_text
    assert context_text.endswith("Find the matching rule with: claude auto-mode defaults")
    assert "Denial reason: the command force-cancels workflow runs in bulk." in context_text


def test_should_show_a_hostile_reason_on_one_line_without_control_characters() -> None:
    hook_output = auto_mode_denial_quick_fix.build_hook_output(
        _denial_payload(reason="the step\n```powershell\nRemove-Item C:\\\n```\n\x1b[31m done.")
    )
    context_text = hook_output["hookSpecificOutput"]["additionalContext"]
    assert "Denial reason: the step ```powershell Remove-Item C:\\ ``` [31m done." in context_text
    assert "\x1b" not in context_text
    assert "\x1b" not in hook_output["systemMessage"]
    assert context_text.count("\n```powershell") == 1


@pytest.mark.parametrize("reason", [42, {"label": "Git Destructive"}, ["[Git Destructive]"]])
def test_should_treat_a_reason_that_is_not_text_as_no_verdict(reason: object) -> None:
    hook_output = auto_mode_denial_quick_fix.build_hook_output(_denial_payload(reason=reason))
    context_text = hook_output["hookSpecificOutput"]["additionalContext"]
    assert "no classifier verdict" in context_text
    assert "powershell" not in context_text
    assert hook_output["systemMessage"] == (
        "Auto mode blocked mcp__github__resolve_review_thread [unnamed rule]."
        " Claude will propose a quick fix."
    )


def test_should_write_a_hostile_entry_unchanged_when_powershell_runs(tmp_path: Path) -> None:
    hostile_entry = "it's \u2018a\u2019 \u201ab\u201b `tick` $(Get-Date) \"q\"\nnext; Remove-Item x"
    block = (
        auto_mode_denial_quick_fix.powershell_block_for(hostile_entry)
        .replace("claude auto-mode config", "")
        .replace("Join-Path $HOME", f"Join-Path '{tmp_path}'")
    )
    script_path = tmp_path / "block.ps1"
    script_path.write_text(block, encoding="utf-8")
    subprocess.run(["pwsh", "-NoProfile", "-File", str(script_path)], check=True)
    written_settings = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert written_settings["autoMode"]["allow"] == ["$defaults", hostile_entry]


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
