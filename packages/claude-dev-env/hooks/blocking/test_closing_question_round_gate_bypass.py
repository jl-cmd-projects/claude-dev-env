import importlib
import io
import json
import sys
import tempfile
from pathlib import Path

import pytest

import closing_question_gate_flag
import closing_question_round_gate

SESSION_HOOKS_DIRECTORY = str(Path(__file__).resolve().parent.parent / "session")
if SESSION_HOOKS_DIRECTORY not in sys.path:
    sys.path.insert(0, SESSION_HOOKS_DIRECTORY)

closing_question_gate_bypass = importlib.import_module("closing_question_gate_bypass")
from hooks_constants.closing_question_round_gate_constants import CLOSING_ROUND_REASON_LEAD

FIRST_SESSION_ID = "s-first"
SECOND_SESSION_ID = "s-second"
DEFERRAL_LINE = "I deferred the backoff setting to a later change."
OFF_CONTEXT = "Question-card stop gate is now OFF"
ON_CONTEXT = "Question-card stop gate is now ON"


@pytest.fixture(autouse=True)
def interactive_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "1")
    flag_folder = tmp_path / "temp"
    flag_folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(flag_folder))


def deferral_transcript(tmp_path: Path) -> Path:
    all_records = [
        {
            "type": "user",
            "turnOrigin": "human",
            "promptSource": "typed",
            "message": {"role": "user", "content": "Add the retry flag to the export job."},
        },
        {
            "type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": DEFERRAL_LINE}]},
        },
    ]
    transcript_path = tmp_path / "s.jsonl"
    transcript_path.write_text(
        "\n".join(json.dumps(each_record) for each_record in all_records), encoding="utf-8"
    )
    return transcript_path


def set_stdin(monkeypatch: pytest.MonkeyPatch, all_payload_fields: dict[str, object]) -> None:
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(all_payload_fields).encode("utf-8")))
    )


def submit_prompt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    session_id: str,
    prompt_text: str,
) -> str | None:
    set_stdin(
        monkeypatch,
        {"hook_event_name": "UserPromptSubmit", "session_id": session_id, "prompt": prompt_text},
    )
    assert closing_question_gate_bypass.main() == 0
    printed_text = capsys.readouterr().out
    if not printed_text:
        return None
    hook_output = json.loads(printed_text)["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "UserPromptSubmit"
    return hook_output["additionalContext"]


def stop_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    session_id: str,
) -> str | None:
    set_stdin(
        monkeypatch,
        {
            "hook_event_name": "Stop",
            "session_id": session_id,
            "stop_hook_active": False,
            "transcript_path": str(deferral_transcript(tmp_path)),
        },
    )
    exit_code = closing_question_round_gate.main()
    printed_text = capsys.readouterr().out
    block_output = json.loads(printed_text) if printed_text else {}
    assert exit_code == (2 if block_output else 0)
    return block_output.get("reason")


def test_should_hold_the_stop_by_default_and_leave_no_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert not closing_question_gate_flag.is_bypass_on({"session_id": FIRST_SESSION_ID})
    reason = stop_reason(monkeypatch, capsys, tmp_path, FIRST_SESSION_ID)
    assert reason is not None
    assert reason.startswith(CLOSING_ROUND_REASON_LEAD)


@pytest.mark.parametrize(
    "keyword_prompt",
    [
        "!nocards",
        "Ship it. !NoCards",
        "!NOCARDS, then merge",
        "<system-reminder>x</system-reminder> !nocards",
    ],
)
def test_should_allow_the_stop_after_a_prompt_with_the_keyword(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    keyword_prompt: str,
) -> None:
    assert submit_prompt(monkeypatch, capsys, FIRST_SESSION_ID, keyword_prompt) == OFF_CONTEXT
    assert stop_reason(monkeypatch, capsys, tmp_path, FIRST_SESSION_ID) is None


def test_should_hold_again_after_a_second_prompt_with_the_keyword(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert submit_prompt(monkeypatch, capsys, FIRST_SESSION_ID, "!nocards") == OFF_CONTEXT
    assert stop_reason(monkeypatch, capsys, tmp_path, FIRST_SESSION_ID) is None
    assert submit_prompt(monkeypatch, capsys, FIRST_SESSION_ID, "back on !NOCARDS") == ON_CONTEXT
    reason = stop_reason(monkeypatch, capsys, tmp_path, FIRST_SESSION_ID)
    assert reason is not None
    assert reason.startswith(CLOSING_ROUND_REASON_LEAD)


def test_should_keep_each_session_toggle_apart(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert submit_prompt(monkeypatch, capsys, FIRST_SESSION_ID, "!nocards") == OFF_CONTEXT
    assert stop_reason(monkeypatch, capsys, tmp_path, FIRST_SESSION_ID) is None
    assert stop_reason(monkeypatch, capsys, tmp_path, SECOND_SESSION_ID) is not None
    assert submit_prompt(monkeypatch, capsys, SECOND_SESSION_ID, "!nocards") == OFF_CONTEXT
    assert submit_prompt(monkeypatch, capsys, FIRST_SESSION_ID, "!nocards") == ON_CONTEXT
    assert stop_reason(monkeypatch, capsys, tmp_path, FIRST_SESSION_ID) is not None
    assert stop_reason(monkeypatch, capsys, tmp_path, SECOND_SESSION_ID) is None


@pytest.mark.parametrize(
    "plain_prompt",
    [
        "Add the retry flag to the export job.",
        "nocards",
        "!nocardsplease",
        "x!nocards",
        "!!nocards",
        "<system-reminder>!nocards</system-reminder> Add the flag.",
    ],
)
def test_should_change_nothing_for_a_prompt_without_the_keyword(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    plain_prompt: str,
) -> None:
    assert submit_prompt(monkeypatch, capsys, FIRST_SESSION_ID, plain_prompt) is None
    assert not closing_question_gate_flag.is_bypass_on({"session_id": FIRST_SESSION_ID})
    assert stop_reason(monkeypatch, capsys, tmp_path, FIRST_SESSION_ID) is not None
    assert submit_prompt(monkeypatch, capsys, FIRST_SESSION_ID, "!nocards") == OFF_CONTEXT
    assert submit_prompt(monkeypatch, capsys, FIRST_SESSION_ID, plain_prompt) is None
    assert closing_question_gate_flag.is_bypass_on({"session_id": FIRST_SESSION_ID})
    assert stop_reason(monkeypatch, capsys, tmp_path, FIRST_SESSION_ID) is None
