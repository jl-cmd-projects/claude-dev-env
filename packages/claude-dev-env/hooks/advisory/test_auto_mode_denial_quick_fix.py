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


@pytest.mark.parametrize(
    "reason",
    [
        "Reason: [Git Destructive] force push",
        "Permission for this action was denied by the Claude Code auto mode classifier. "
        "Reason: [Git Destructive] force push",
    ],
)
def test_should_read_the_same_label_after_a_leading_reason_marker(reason: str) -> None:
    assert auto_mode_denial_quick_fix.parse_denial_reason(reason) == (
        auto_mode_denial_quick_fix.DenialReason(
            rule_label="Git Destructive", has_verdict=True, prose="force push"
        )
    )


def _flow_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    playbook_path = tmp_path / "agent-channels" / "docs" / "auto-mode-rule.md"
    playbook_path.parent.mkdir(parents=True)
    playbook_path.write_text("# Playbook\n", encoding="utf-8")
    repository_root = playbook_path.parent.parent
    (repository_root / ".git").mkdir()
    (repository_root / "setup").mkdir()
    (repository_root / "setup" / "add_auto_mode_rule.py").write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_AUTO_MODE_RULE_PLAYBOOK", str(playbook_path))
    return playbook_path


def _ledger_payload(tmp_path: Path, **overrides: object) -> dict[str, object]:
    all_fields: dict[str, object] = {
        "tool_name": "Bash",
        "tool_input": {"command": "git push -f origin claude/x"},
        "reason": "[Git Destructive] force push",
        "transcript_path": str(tmp_path / "transcript.jsonl"),
    }
    all_fields.update(overrides)
    return _denial_payload(**all_fields)


def test_should_record_one_entry_and_return_its_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scratch_config_directory: Path
) -> None:
    _flow_on(tmp_path, monkeypatch)
    expected_question = (
        "Auto mode refused 1 Bash step under the Git Destructive rule. "
        "Should auto mode have refused it?"
    )
    for _ in range(2):
        context_text = auto_mode_denial_quick_fix.hook_output_with_ledger(
            _ledger_payload(tmp_path)
        )["hookSpecificOutput"]["additionalContext"]
        assert expected_question in context_text
    ledger_directory = scratch_config_directory / "state" / "auto-mode-refusals" / "session-1"
    all_entry_files = [
        each_path
        for each_path in ledger_directory.glob("*.json")
        if not each_path.name.startswith("question-")
    ]
    assert len(all_entry_files) == 1
    assert json.loads(all_entry_files[0].read_text(encoding="utf-8"))["answer"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"reason": "the command cancels runs."},
        {"tool_input": {"command": "python3 setup/add_auto_mode_rule.py add --rule-file r.txt"}},
    ],
)
def test_should_record_nothing_for_prose_or_the_rule_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, overrides: dict[str, object]
) -> None:
    playbook_path = _flow_on(tmp_path, monkeypatch)
    payload = _ledger_payload(tmp_path, cwd=str(playbook_path.parent.parent), **overrides)
    assert auto_mode_denial_quick_fix.hook_output_with_ledger(
        payload
    ) == auto_mode_denial_quick_fix.build_hook_output(payload)


def test_should_append_the_question_only_when_the_flow_is_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _ledger_payload(tmp_path)
    assert auto_mode_denial_quick_fix.hook_output_with_ledger(
        payload
    ) == auto_mode_denial_quick_fix.build_hook_output(payload)
    _flow_on(tmp_path, monkeypatch)
    context_text = auto_mode_denial_quick_fix.hook_output_with_ledger(payload)[
        "hookSpecificOutput"
    ]["additionalContext"]
    assert context_text.startswith("=== AUTO MODE DENIAL QUICK FIX ===")
    assert "```powershell" in context_text
    assert "=== AUTO MODE QUESTION ===" in context_text
    assert "Auto mode refused 1 Bash step under the Git Destructive rule." in context_text


UNEXPLAINED_DANGER_REASON = (
    "The server-side auto mode classifier judged this action dangerous (it gave no explanation)"
)


def test_should_parse_an_unexplained_danger_reason_as_the_unexplained_rule() -> None:
    assert auto_mode_denial_quick_fix.parse_denial_reason(UNEXPLAINED_DANGER_REASON) == (
        auto_mode_denial_quick_fix.DenialReason(
            rule_label="Unexplained", has_verdict=True, prose=UNEXPLAINED_DANGER_REASON
        )
    )


def test_should_parse_a_timed_out_server_reason_with_no_label() -> None:
    timed_out_reason = "The server-side auto mode classifier gave no verdict (timed out)"
    assert auto_mode_denial_quick_fix.parse_denial_reason(timed_out_reason).rule_label is None


def test_should_record_an_unexplained_refusal_and_ask_its_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scratch_config_directory: Path
) -> None:
    _flow_on(tmp_path, monkeypatch)
    context_text = auto_mode_denial_quick_fix.hook_output_with_ledger(
        _ledger_payload(tmp_path, reason=UNEXPLAINED_DANGER_REASON)
    )["hookSpecificOutput"]["additionalContext"]
    assert (
        "Auto mode refused 1 Bash step under the Unexplained rule. "
        "Should auto mode have refused it?"
    ) in context_text
    assert "Unexplained exception: Bash calls like `git push -f origin claude/x`" in context_text
    assert "Find the matching rule with: claude auto-mode defaults" in context_text
    assert "--label" not in context_text
    ledger_directory = scratch_config_directory / "state" / "auto-mode-refusals" / "session-1"
    all_entry_files = [
        each_path
        for each_path in ledger_directory.glob("*.json")
        if not each_path.name.startswith("question-")
    ]
    assert len(all_entry_files) == 1


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


def _allowed_ledger_entry(scratch_config_directory: Path) -> Path:
    ledger_directory = scratch_config_directory / "state" / "auto-mode-refusals" / "session-1"
    ledger_directory.mkdir(parents=True, exist_ok=True)
    allowed_input = {"command": "git push -f origin claude/allowed"}
    (ledger_directory / "allowed.json").write_text(
        json.dumps(
            {
                "id": "allowed",
                "tool_name": "Bash",
                "tool_input": allowed_input,
                "rule_label": "Git Destructive",
                "action_summary": allowed_input["command"],
                "sequence": 1,
                "answer": "allowed",
            }
        ),
        encoding="utf-8",
    )
    return ledger_directory


def _entry_file_count(ledger_directory: Path) -> int:
    return sum(
        1
        for each_path in ledger_directory.glob("*.json")
        if not each_path.name.startswith("question-")
    )


@pytest.mark.parametrize(
    ("file_name", "file_fields"),
    [
        ("no-id.json", {"answer": None, "tool_name": "Bash", "rule_label": "Git Destructive"}),
        (
            "bad-sequence.json",
            {
                "id": "bad-sequence",
                "tool_name": "Bash",
                "rule_label": "Git Destructive",
                "sequence": "first",
                "answer": None,
            },
        ),
        (
            "question-bad-offset.json",
            {
                "record": "question",
                "question": "Q?",
                "entry_ids": ["x"],
                "transcript_offset": "late",
            },
        ),
    ],
)
def test_should_skip_a_ledger_file_that_does_not_parse_and_still_ask(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    scratch_config_directory: Path,
    file_name: str,
    file_fields: dict[str, object],
) -> None:
    _flow_on(tmp_path, monkeypatch)
    ledger_directory = scratch_config_directory / "state" / "auto-mode-refusals" / "session-1"
    ledger_directory.mkdir(parents=True)
    (ledger_directory / file_name).write_text(json.dumps(file_fields), encoding="utf-8")
    payload = _ledger_payload(tmp_path)
    context_text = _hook_output_from_stdin(payload, monkeypatch, capsys)["hookSpecificOutput"][
        "additionalContext"
    ]
    today_context = auto_mode_denial_quick_fix.build_hook_output(payload)["hookSpecificOutput"][
        "additionalContext"
    ]
    assert context_text.startswith(today_context)
    assert "Auto mode refused 1 Bash step under the Git Destructive rule." in context_text


def test_should_fall_back_to_todays_output_on_any_ledger_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _flow_on(tmp_path, monkeypatch)

    def raise_lookup_error(*_: object) -> None:
        raise LookupError("ledger broke")

    monkeypatch.setattr(
        auto_mode_denial_quick_fix.auto_mode_refusal_ledger,
        "apply_transcript_answers",
        raise_lookup_error,
    )
    payload = _ledger_payload(tmp_path)
    assert _hook_output_from_stdin(
        payload, monkeypatch, capsys
    ) == auto_mode_denial_quick_fix.build_hook_output(payload)


def test_should_fall_back_to_todays_output_for_a_playbook_at_the_filesystem_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    scratch_config_directory: Path,
) -> None:
    ledger_directory = _allowed_ledger_entry(scratch_config_directory)
    monkeypatch.setattr(
        auto_mode_denial_quick_fix.auto_mode_refusal_ledger,
        "playbook_path_from_environment",
        lambda: Path("/auto-mode-rule.md"),
    )
    payload = _ledger_payload(tmp_path)
    assert _hook_output_from_stdin(
        payload, monkeypatch, capsys
    ) == auto_mode_denial_quick_fix.build_hook_output(payload)
    assert _entry_file_count(ledger_directory) == 1


def _rule_worktree(tmp_path: Path, branch_name: str) -> Path:
    repository_git_directory = tmp_path / "agent-channels" / ".git"
    worktree_git_directory = repository_git_directory / "worktrees" / "agent-channels-rule"
    worktree_git_directory.mkdir(parents=True)
    (worktree_git_directory / "HEAD").write_text(
        f"ref: refs/heads/{branch_name}\n", encoding="utf-8"
    )
    (worktree_git_directory / "commondir").write_text("../..\n", encoding="utf-8")
    worktree_directory = tmp_path / "scratch" / "agent-channels-rule"
    worktree_directory.mkdir(parents=True)
    (worktree_directory / ".git").write_text(
        f"gitdir: {worktree_git_directory}\n", encoding="utf-8"
    )
    (worktree_git_directory / "gitdir").write_text(
        f"{worktree_directory / '.git'}\n", encoding="utf-8"
    )
    return worktree_directory


@pytest.mark.parametrize(
    ("branch_name", "command", "is_entry_expected"),
    [
        (
            "claude/auto-mode-rule-own-push",
            'git commit -m "Add the Own push auto mode rule"',
            False,
        ),
        (
            "claude/auto-mode-rule-own-push",
            "git push -u origin claude/auto-mode-rule-own-push",
            False,
        ),
        ("claude/project-thread-rule", 'git commit -m "Add a rule"', True),
        ("claude/auto-mode-rule-own-push", "git push -u origin claude/project-thread-rule", True),
    ],
)
def test_should_skip_only_a_rule_branch_commit_or_push_in_a_rule_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scratch_config_directory: Path,
    branch_name: str,
    command: str,
    is_entry_expected: bool,
) -> None:
    _flow_on(tmp_path, monkeypatch)
    ledger_directory = _allowed_ledger_entry(scratch_config_directory)
    worktree_directory = _rule_worktree(tmp_path, branch_name)
    payload = _ledger_payload(
        tmp_path,
        tool_input={"command": command},
        reason="[Destructive or Unwanted Actions] writes a branch",
        cwd=str(worktree_directory),
    )
    auto_mode_denial_quick_fix.hook_output_with_ledger(payload)
    assert _entry_file_count(ledger_directory) == (2 if is_entry_expected else 1)
