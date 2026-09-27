import io
import json
from pathlib import Path

import pytest

import edit_marker_gate

UPDATE_TOOL_NAME = "mcp__chat__update_message"


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
    exit_code = edit_marker_gate.main()
    return exit_code, capsys.readouterr().err


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_should_allow_a_clean_replacement_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, UPDATE_TOOL_NAME, {"message_id": "m1", "text": "The fix is filed."}
    )
    assert (exit_code, stderr_text) == (0, "")


def test_should_deny_strikethrough_and_ask_for_the_clean_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch,
        capsys,
        UPDATE_TOOL_NAME,
        {"text": "~~Please pass this on.~~ The thread files it."},
    )
    assert exit_code == 2
    assert "strikethrough" in stderr_text
    assert "clean new text" in stderr_text


@pytest.mark.parametrize(
    "edited_text",
    [
        "Please pass this on. [Edit: nothing needed from you here.]",
        "Done. [edit: the thread filed it]",
        "Done. [ Edit : filed]",
    ],
)
def test_should_deny_an_edit_note_in_any_case(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    edited_text: str,
) -> None:
    exit_code, stderr_text = run_gate(monkeypatch, capsys, UPDATE_TOOL_NAME, {"text": edited_text})
    assert exit_code == 2
    assert "[Edit:" in stderr_text


def test_should_deny_a_marker_inside_a_replacement_card(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    card = {"blocks": [{"type": "section", "text": "~~Old plan~~ New plan."}]}
    exit_code, _ = run_gate(
        monkeypatch, capsys, UPDATE_TOOL_NAME, {"text": "New plan.", "card": card}
    )
    assert exit_code == 2


def test_should_allow_markers_on_tools_that_edit_no_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(
        monkeypatch, capsys, "mcp__chat__reply", {"text": "~~old~~ [Edit: new]"}
    )
    assert exit_code == 0


def test_should_allow_a_single_tilde_pair_and_the_word_edit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(
        monkeypatch,
        capsys,
        UPDATE_TOOL_NAME,
        {"text": "Edit the file at ~/notes, about ~5 lines."},
    )
    assert exit_code == 0


def test_should_allow_input_without_a_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"not json")))
    assert edit_marker_gate.main() == 0
