import io
import json
from pathlib import Path

import pytest

import issue_close_handoff_gate

COMMENT_TOOL_NAME = "mcp__github__add_issue_comment"
WRITE_TOOL_NAME = "mcp__github__issue_write"
HANDOFF_CLOSE_BODY = (
    "## Fresh-session reading: criteria met, issue closed\n\n"
    "Closing on that basis. Reopen if the comparison matters more.\n\n"
    "Out of scope here and not attributed: the first prompt still grew by 30k."
    " The first-prompt growth belongs to #20."
)
REOPEN_BODY = (
    "## Reopened: the reading came before any message\n\n"
    "The growth after the first message moves the open question to #20 for context."
    " The issue stays open until the transcript is read."
)


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool_name: str,
    tool_input: dict[str, object],
) -> tuple[int, str]:
    hook_input = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
    }
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = issue_close_handoff_gate.main()
    return exit_code, capsys.readouterr().err


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_should_deny_a_closing_comment_that_routes_the_found_defect_to_another_issue(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, COMMENT_TOOL_NAME, {"issue_number": 10, "body": HANDOFF_CLOSE_BODY}
    )
    assert exit_code == 2
    assert "owns it through the fix pull request" in stderr_text


def test_should_deny_a_closed_state_write_whose_comment_hands_the_defect_off(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(
        monkeypatch,
        capsys,
        WRITE_TOOL_NAME,
        {"state": "closed", "body": "Done. The leftover growth is tracked in #20."},
    )
    assert exit_code == 2


def test_should_deny_a_close_that_calls_the_defect_a_separate_finding(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(
        monkeypatch,
        capsys,
        COMMENT_TOOL_NAME,
        {"body": "Closing this issue. The jump is a separate finding for the epic."},
    )
    assert exit_code == 2


def test_should_allow_a_comment_that_routes_work_while_the_issue_stays_open(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(monkeypatch, capsys, COMMENT_TOOL_NAME, {"body": REOPEN_BODY})
    assert exit_code == 0
    assert stderr_text == ""


def test_should_allow_a_close_with_a_plain_cross_reference(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(
        monkeypatch,
        capsys,
        WRITE_TOOL_NAME,
        {"state": "closed", "body": "Closes #12. #13 tracks the docs."},
    )
    assert exit_code == 0


def test_should_allow_a_close_with_no_handoff(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(
        monkeypatch,
        capsys,
        COMMENT_TOOL_NAME,
        {"body": "Fixed by the merged pull request. Closing this issue."},
    )
    assert exit_code == 0


def test_should_ignore_tools_outside_the_issue_set(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(monkeypatch, capsys, "mcp__chat__reply", {"body": HANDOFF_CLOSE_BODY})
    assert exit_code == 0


def test_is_handoff_close_should_need_both_a_close_and_a_handoff() -> None:
    assert issue_close_handoff_gate.is_handoff_close({"body": HANDOFF_CLOSE_BODY})
    assert not issue_close_handoff_gate.is_handoff_close({"body": REOPEN_BODY})
    assert not issue_close_handoff_gate.is_handoff_close(
        {"state": "closed", "body": "Fixed and verified."}
    )
