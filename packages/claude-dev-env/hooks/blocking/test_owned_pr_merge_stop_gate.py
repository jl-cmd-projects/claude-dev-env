"""Behavior tests for the owned pull request merge Stop gate."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

import owned_pr_merge_stop_gate
import owned_pr_session_record

SESSION_ID = "session-abc"
PULL_REQUEST = {
    "owner": "jl-cmd",
    "repository": "snake-game",
    "number": "9",
    "url": "https://github.com/jl-cmd/snake-game/pull/9",
}


@pytest.fixture(autouse=True)
def isolated_temp_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(owned_pr_session_record.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))


def _gh_reports(
    monkeypatch: pytest.MonkeyPatch, state_text: str, exit_code: int = 0
) -> list[list[str]]:
    all_calls: list[list[str]] = []

    def fake_run(all_arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        all_calls.append(all_arguments)
        return subprocess.CompletedProcess(all_arguments, exit_code, stdout=state_text, stderr="")

    monkeypatch.setattr(owned_pr_merge_stop_gate.subprocess, "run", fake_run)
    return all_calls


def _run_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], reply_text: str
) -> str:
    hook_input = {
        "hook_event_name": "Stop",
        "session_id": SESSION_ID,
        "last_assistant_message": reply_text,
    }
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    assert owned_pr_merge_stop_gate.main() == 0
    return capsys.readouterr().out


def test_main_should_block_while_a_recorded_pull_request_is_open(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    owned_pr_session_record.record_pull_request(SESSION_ID, PULL_REQUEST)
    all_calls = _gh_reports(monkeypatch, "open\n")
    decision = json.loads(_run_gate(monkeypatch, capsys, "Draft PR is open."))
    assert decision["decision"] == "block"
    assert PULL_REQUEST["url"] in decision["reason"]
    assert "/efficient-review" in decision["reason"]
    assert all_calls == [["gh", "api", "repos/jl-cmd/snake-game/pulls/9", "--jq", ".state"]]


def test_main_should_allow_once_the_pull_request_is_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    owned_pr_session_record.record_pull_request(SESSION_ID, PULL_REQUEST)
    _gh_reports(monkeypatch, "closed\n")
    assert _run_gate(monkeypatch, capsys, "Merged.") == ""


def test_main_should_allow_a_blocked_line_that_names_the_pull_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    owned_pr_session_record.record_pull_request(SESSION_ID, PULL_REQUEST)
    _gh_reports(monkeypatch, "open\n")
    reply_text = "Review is clean.\nBlocked: jl-cmd/snake-game#9 - the owner must approve the merge"
    assert _run_gate(monkeypatch, capsys, reply_text) == ""


def test_main_should_block_when_the_blocked_line_names_another_pull_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    owned_pr_session_record.record_pull_request(SESSION_ID, PULL_REQUEST)
    _gh_reports(monkeypatch, "open\n")
    reply_text = "Blocked: jl-cmd/snake-game#90 - the owner must approve the merge"
    assert json.loads(_run_gate(monkeypatch, capsys, reply_text))["decision"] == "block"


def test_main_should_allow_when_the_state_lookup_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    owned_pr_session_record.record_pull_request(SESSION_ID, PULL_REQUEST)
    _gh_reports(monkeypatch, "", exit_code=1)
    assert _run_gate(monkeypatch, capsys, "Draft PR is open.") == ""


def test_main_should_allow_a_session_that_opened_no_owned_pull_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_calls = _gh_reports(monkeypatch, "open\n")
    assert _run_gate(monkeypatch, capsys, "Done.") == ""
    assert all_calls == []


def test_is_pull_request_open_should_read_the_github_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _gh_reports(monkeypatch, "open\n")
    assert owned_pr_merge_stop_gate.is_pull_request_open(PULL_REQUEST)


def test_is_reported_blocked_should_accept_the_url() -> None:
    reply_text = f"- Blocked: {PULL_REQUEST['url']} - needs the owner"
    assert owned_pr_merge_stop_gate.is_reported_blocked(PULL_REQUEST, reply_text)


def test_unfinished_pull_requests_should_list_the_open_one(monkeypatch: pytest.MonkeyPatch) -> None:
    owned_pr_session_record.record_pull_request(SESSION_ID, PULL_REQUEST)
    _gh_reports(monkeypatch, "open\n")
    hook_input: dict[str, object] = {"session_id": SESSION_ID, "last_assistant_message": "Open."}
    assert owned_pr_merge_stop_gate.unfinished_pull_requests(hook_input) == [PULL_REQUEST]


def test_block_reason_for_should_name_each_pull_request_and_the_blocked_form() -> None:
    reason = owned_pr_merge_stop_gate.block_reason_for([PULL_REQUEST])
    assert PULL_REQUEST["url"] in reason
    assert "Blocked: <owner>/<repository>#<number>" in reason
