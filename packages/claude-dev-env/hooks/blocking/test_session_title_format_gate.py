import io
import json
from pathlib import Path

import pytest

import session_title_format_gate
from hooks_constants.session_title_constants import (
    BRANCH_NAME_MESSAGE,
    IDENTIFIER_MESSAGE,
    SENTENCE_CASE_MESSAGE,
    SINGLE_LINE_MESSAGE,
    STATUS_PREFIX_MESSAGE,
    TRAILING_PUNCTUATION_MESSAGE,
)

REMOTE_TITLE_TOOL = "mcp__claude-code-remote__set_session_title"
DESKTOP_TITLE_TOOL = "mcp__ccd_session_mgmt__set_session_title"
RED_FLAG = "\U0001f6a9"
CHECK_MARK = "✅"
HOURGLASS = "⏳"


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool_name: str,
    tool_input: object,
) -> tuple[int, str]:
    hook_input = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = session_title_format_gate.main()
    return exit_code, capsys.readouterr().err


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


@pytest.mark.parametrize("tool_name", [REMOTE_TITLE_TOOL, DESKTOP_TITLE_TOOL])
@pytest.mark.parametrize(
    "title",
    [
        f"{HOURGLASS} Broker gate + replay rule",
        f"{CHECK_MARK} Session title gate",
        f"{RED_FLAG}️ Runner sign-in",
        f"{RED_FLAG} CI gate + docs",
    ],
)
def test_should_allow_a_well_formed_title_on_each_title_tool(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tool_name: str, title: str
) -> None:
    assert run_gate(monkeypatch, capsys, tool_name, {"session_id": "s", "title": title}) == (0, "")


@pytest.mark.parametrize(
    ("title", "expected_message"),
    [
        ("Broker gate + replay rule", STATUS_PREFIX_MESSAGE),
        ("\U0001f680 Broker gate", STATUS_PREFIX_MESSAGE),
        (f"{HOURGLASS}Broker gate", STATUS_PREFIX_MESSAGE),
        (f"{HOURGLASS} Broker gate\nand more", SINGLE_LINE_MESSAGE),
        (f"{HOURGLASS} Broker gate.", TRAILING_PUNCTUATION_MESSAGE),
        (f"{HOURGLASS} broker gate", SENTENCE_CASE_MESSAGE),
        (f"{HOURGLASS} PR 5608 review", IDENTIFIER_MESSAGE),
        (f"{HOURGLASS} Plan for 2026-10-04", IDENTIFIER_MESSAGE),
        (f"{HOURGLASS} Feature/title cleanup", BRANCH_NAME_MESSAGE),
    ],
)
def test_should_deny_a_title_and_name_the_rule_it_breaks(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    title: str,
    expected_message: str,
) -> None:
    exit_code, stderr_text = run_gate(monkeypatch, capsys, REMOTE_TITLE_TOOL, {"title": title})
    assert exit_code == 2
    assert stderr_text.startswith(expected_message)
    assert "Call the title tool again" in stderr_text


def test_should_deny_a_name_longer_than_twenty_five_characters(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        DESKTOP_TITLE_TOOL,
        {"title": f"{CHECK_MARK} Broker gate and replay rules"},
    )
    assert exit_code == 2
    assert "1 to 25 characters; it has 28" in stderr_text


def test_should_allow_a_name_of_exactly_twenty_five_characters(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    title = f"{CHECK_MARK} " + "A" * 25
    assert run_gate(monkeypatch, capsys, REMOTE_TITLE_TOOL, {"title": title}) == (0, "")


@pytest.mark.parametrize(
    ("tool_name", "tool_input"),
    [
        ("mcp__chat__update_message", {"title": "fix stuff."}),
        (REMOTE_TITLE_TOOL, {"name": "fix stuff."}),
        (REMOTE_TITLE_TOOL, "fix stuff."),
    ],
)
def test_should_leave_other_tools_and_schemas_alone(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool_name: str,
    tool_input: object,
) -> None:
    assert run_gate(monkeypatch, capsys, tool_name, tool_input) == (0, "")


def test_title_format_violation_returns_none_for_a_good_title() -> None:
    assert session_title_format_gate.title_format_violation(f"{RED_FLAG} Runner sign-in") is None


def test_title_format_violation_names_the_missing_emoji() -> None:
    assert (
        session_title_format_gate.title_format_violation("Runner sign-in") == STATUS_PREFIX_MESSAGE
    )
