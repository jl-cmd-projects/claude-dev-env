import io
import json
from pathlib import Path

import pytest

import final_reply_gate

GUESSED_REPLY = "My guess is one to two hours if those builds pass first time."
UNCONFIRMED_REPLY = "Merge queue: I didn\u2019t confirm this one."
MEASURED_REPLY = "The last queue build took 39 minutes, run 18239174012."
INSIGHTS_REPLY = (
    "Your shareable insights report is ready:\n"
    "file://C:\\Reports\\.claude-profiles\\org\\usage-data\\report-2026-10-20-094705.html"
)


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reply_text: str,
    transcript_path: Path | None = None,
) -> tuple[int, str]:
    hook_input: dict[str, object] = {
        "hook_event_name": "Stop",
        "stop_hook_active": False,
        "last_assistant_message": reply_text,
    }
    if transcript_path is not None:
        hook_input["transcript_path"] = str(transcript_path)
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = final_reply_gate.main()
    return exit_code, capsys.readouterr().out


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("CLAUDE_REPLY_BANNED_WORDS_PATH", raising=False)


def write_tool_result_transcript(transcript_path: Path, result_text: str) -> Path:
    tool_result = {"type": "tool_result", "tool_use_id": "t1", "content": result_text}
    transcript_path.write_text(
        json.dumps({"type": "user", "message": {"content": [tool_result]}}), encoding="utf-8"
    )
    return transcript_path


@pytest.mark.parametrize(
    ("reply_text", "quoted_text"),
    [
        (GUESSED_REPLY, 'Banned word "guess"'),
        (UNCONFIRMED_REPLY, 'No tool validated this: "Merge queue: I didn\u2019t confirm this one."'),
        ("It should take about 40 minutes.", "It should take about 40 minutes."),
    ],
)
def test_should_block_a_closing_reply_that_guesses(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reply_text: str,
    quoted_text: str,
) -> None:
    exit_code, stdout_text = run_gate(monkeypatch, capsys, reply_text)
    decision = json.loads(stdout_text)
    assert exit_code == 0
    assert decision["decision"] == "block"
    assert quoted_text in decision["reason"]
    assert decision["reason"].endswith("Rewrite the reply without it.")


def test_should_block_a_run_no_tool_result_shows(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_tool_result_transcript(tmp_path / "s.jsonl", "run 18239170000 ok")
    _, stdout_text = run_gate(monkeypatch, capsys, MEASURED_REPLY, transcript_path)
    assert 'cites "run 18239174012"' in json.loads(stdout_text)["reason"]


def test_should_allow_a_run_a_tool_result_shows(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_tool_result_transcript(tmp_path / "s.jsonl", "run 18239174012 took 39m")
    assert run_gate(monkeypatch, capsys, MEASURED_REPLY, transcript_path) == (0, "")


def test_should_allow_a_closing_reply_with_no_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b'{"hook_event_name": "Stop"}')))
    assert (final_reply_gate.main(), capsys.readouterr().out) == (0, "")


def test_should_return_none_for_a_measured_reply_without_a_transcript() -> None:
    assert final_reply_gate.final_reply_violation(MEASURED_REPLY, None) is None


@pytest.mark.parametrize(
    ("reply_text", "quoted_text"),
    [
        (INSIGHTS_REPLY, 'Path "file://C:\\Reports\\.claude-profiles'),
        ("The report is at C:\\Reports\\.claude\\report.html now.", 'Path "C:\\Reports'),
        ("Run C:\\Tools\\-v\\x.exe once.", 'Path "C:\\Tools\\-v'),
        ("Wait ~~~ then open C:\\Reports\\.claude\\r.html now.", 'Path "C:\\Reports'),
        ("Wait ``` then open C:\\Reports\\.claude\\r.html now.", 'Path "C:\\Reports'),
        ("Escaped \\` then C:\\Reports\\.claude\\r.html then `x`.", 'Path "\\`"'),
        ("Open C:\\Shared Files\\.claude\\x.html now.", 'Path "Files\\.claude'),
        ("Open `C:\\Reports`\\.claude\\x.html now.", 'Path "\\.claude'),
        ("Saved to C:\\Reports\\..\\out\\x.html now.", 'Path "C:\\Reports'),
        ("Saved to D:\\Reports\\. now", 'Path "D:\\Reports\\."'),
    ],
)
def test_should_block_a_windows_path_markdown_mangles(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reply_text: str,
    quoted_text: str,
) -> None:
    _, stdout_text = run_gate(monkeypatch, capsys, reply_text)
    decision = json.loads(stdout_text)
    assert decision["decision"] == "block"
    assert quoted_text in decision["reason"]


@pytest.mark.parametrize(
    "reply_text",
    [
        "Open `file:///C:/Reports/.claude/report.html` now.",
        "The report is at `C:\\Reports\\.claude\\report.html` now.",
        "Paths:\n```text\nC:\\Reports\\.claude\\report.html\n```",
        "The report is at C:\\Reports\\report.html now.",
        "The report is at C:\\\\Reports\\\\.claude\\\\report.html now.",
        "The report is at ``C:\\Reports\\.claude\\report.html`` now.",
        "Paths:\n~~~\nC:\\Reports\\.claude\\report.html\n~~~",
    ],
)
def test_should_allow_a_windows_path_inside_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], reply_text: str
) -> None:
    assert run_gate(monkeypatch, capsys, reply_text) == (0, "")
