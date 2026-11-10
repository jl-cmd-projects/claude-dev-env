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


def test_should_steer_a_skipped_check_to_an_open_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    skipped_check_reply = "I have not checked the pivot, reach, or screen 26 captures yet."
    _, stdout_text = run_gate(monkeypatch, capsys, skipped_check_reply)
    block_reason = json.loads(stdout_text)["reason"]
    assert "`Open: <check> - <next step>`" in block_reason
    assert "leave the claim out" not in block_reason


def test_should_allow_an_open_line_for_a_skipped_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    open_line = "Open: pivot, reach, and screen 26 checks - the next check-in measures them."
    assert run_gate(monkeypatch, capsys, open_line) == (0, "")


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
        ("Saved to D:\\Reports\\\\\\.claude now", 'Path "D:\\Reports'),
        ("```\n```python\n```\nOpen C:\\Reports\\.claude\\x.html now.\n```", 'Path "C:\\Reports'),
        ("Check `this\nand `C:\\Reports\\.claude\\r.html` now.", 'Path "C:\\Reports'),
        ("```foo` bar\nOpen C:\\Reports\\.claude\\r.html now.", 'Path "C:\\Reports'),
        ("Saved to D:\\Reports\\\n.claude\\x.html now.", 'Path "D:\\Reports\\"'),
        ("\\\\`x` now C:\\Reports\\.claude\\r.html and `y`", 'Path "C:\\Reports'),
        ("Check `this\n\nand C:\\Reports\\.claude\\r.html` now.", 'Path "C:\\Reports'),
        ("- Stray ` here\n- Saved to D:\\Reports\\.claude\\r.html\n- Run `x`", 'Path "D:\\Reports'),
        ("# Stray ` here\nSaved to D:\\Reports\\.claude\\r.html `x`", 'Path "D:\\Reports'),
        ("Check `this\n2. and `C:\\Reports\\.claude\\r.html` now.", 'Path "C:\\Reports'),
        ("Check `this\n    - and `C:\\Reports\\.claude\\r.html` now.", 'Path "C:\\Reports'),
        ("Check `this\n    # and `C:\\Reports\\.claude\\r.html` now.", 'Path "C:\\Reports'),
        ("Check `this\n\t# and `C:\\Reports\\.claude\\r.html` now.", 'Path "C:\\Reports'),
        ("Check `this\n---\nand C:\\Reports\\.claude\\r.html `x`", 'Path "C:\\Reports'),
        ("Check `this\n===\nand C:\\Reports\\.claude\\r.html `x`", 'Path "C:\\Reports'),
        ("Check `this\n* * *\nand C:\\Reports\\.claude\\r.html `x`", 'Path "C:\\Reports'),
        ("Check `this\n___\nand C:\\Reports\\.claude\\r.html `x`", 'Path "C:\\Reports'),
        ("Check `this\n<!-- note -->\nand C:\\Reports\\.claude\\r.html `x`", 'Path "C:\\Reports'),
        ("Check `this\n<details>\n\nand C:\\Reports\\.claude\\r.html `x`", 'Path "C:\\Reports'),
        ("Check `this\n<span>a` and C:\\Reports\\.claude\\r.html `x`", 'Path "C:\\Reports'),
        ("<!-- ` -->\nSaved to C:\\Reports\\.claude\\r.html `x`", 'Path "C:\\Reports'),
        ("Check `this\n```\ncode\n```\nand C:\\Reports\\.claude\\r.html `x`", 'Path "C:\\Reports'),
        ("- ```bash\n  echo hi\n  ```\nSaved to D:\\Reports\\.claude\\r.html now.", 'Path "D:\\Reports'),
        ("```\nC:\\Reports\\.claude\\open.html", 'Path "C:\\Reports'),
        ("> stray ` here\n> and `C:\\Reports\\.claude\\r.html` now", 'Path "C:\\Reports'),
        ("> stray `\n>> and C:\\Reports\\.claude\\r.html `x`", 'Path "C:\\Reports'),
        ("> stray `\nlazy\n> and `C:\\Reports\\.claude\\r.html` now", 'Path "C:\\Reports'),
        ("```\r\ncode\r\n```\r\nOpen C:\\Reports\\.claude\\r.html now.", 'Path "C:\\Reports'),
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
        "Paths `C:\\Reports\\.claude\nreport.html` here.",
        "<pre>\nC:\\Reports\\.claude\\report.html\n</pre>",
        "> Saved to `C:\\Reports\\.claude\\report.html`\n> now.",
    ],
)
def test_should_allow_a_windows_path_inside_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], reply_text: str
) -> None:
    assert run_gate(monkeypatch, capsys, reply_text) == (0, "")


@pytest.mark.parametrize(
    ("text", "masked_text"),
    [
        ("a\n<!--\nb\n-->\nc", "a\n\n\n\nc"),
        ("a\n<!--\nb\nc", "a\n<!--\nb\nc"),
        ("<!--\n<!--\nb -->\nc", "\n\n\nc"),
        ("<details>\nb\n\nc", "\n\n\n\nc"),
    ],
)
def test_should_mask_html_blocks_only_where_they_close(text: str, masked_text: str) -> None:
    assert (
        final_reply_gate.blocks_masked(
            text,
            final_reply_gate.HTML_BLOCK_OPENER_PATTERN,
            final_reply_gate._html_block_closer_for,
        )
        == masked_text
    )


@pytest.mark.parametrize(
    ("text", "unwrapped_text"),
    [
        ("> a\n> b", "\na\nb"),
        ("> a\n>> b", "\na\n\nb"),
        ("> a\nb\n> c", "\na\nb\nc"),
        ("> a\n\n> b", "\na\n\n\nb"),
        ("plain", "plain"),
    ],
)
def test_should_unwrap_quotes_into_their_paragraphs(text: str, unwrapped_text: str) -> None:
    assert final_reply_gate.quotes_unwrapped(text) == unwrapped_text


@pytest.mark.parametrize(
    ("paragraph_text", "masked_text"),
    [
        ("see `a\\.b` and more", "see   and more"),
        ("\\`x` stays", "\\`x` stays"),
        ("\\\\`x` gone", "\\\\  gone"),
        ("``a`b`` end", "  end"),
        ("`open only", "`open only"),
    ],
)
def test_should_mask_code_spans_the_way_commonmark_pairs_them(
    paragraph_text: str, masked_text: str
) -> None:
    assert final_reply_gate.code_spans_masked(paragraph_text) == masked_text


BARE_QUESTION_REPLY = (
    "PR 8093 merged into the branch of PR 8007 by mistake.\n\n"
    "My question on PR 8093 still stands. Keep it merged into the branch of PR 8007, or revert it?"
)
STANDING_QUESTION_REPLY = "Checks are green.\n\nMy question on the revert still stands."
REPORT_ONLY_REPLY = "Both branches are rebuilt.\n\nThe tests pass on each."


def prompt_record(prompt_text: str) -> dict[str, object]:
    return {"type": "user", "message": {"role": "user", "content": prompt_text}}


def assistant_tool_record(tool_name: str, tool_input: dict[str, object]) -> dict[str, object]:
    tool_use = {"type": "tool_use", "id": "q1", "name": tool_name, "input": tool_input}
    return {"type": "assistant", "message": {"role": "assistant", "content": [tool_use]}}


def assistant_text_record(reply_text: str) -> dict[str, object]:
    text_block = {"type": "text", "text": reply_text}
    return {"type": "assistant", "message": {"role": "assistant", "content": [text_block]}}


def stop_feedback_record() -> dict[str, object]:
    feedback = {"role": "user", "content": "Stop hook feedback: send the question"}
    return {"type": "user", "isMeta": True, "message": feedback}


def write_records(transcript_path: Path, all_records: list[dict[str, object]]) -> Path:
    transcript_path.write_text(
        "\n".join(json.dumps(each_record) for each_record in all_records), encoding="utf-8"
    )
    return transcript_path


ASK_INPUT: dict[str, object] = {"questions": [{"question": "Keep PR 8093 merged?", "options": []}]}


@pytest.mark.parametrize(
    ("reply_text", "all_turn_records"),
    [
        (BARE_QUESTION_REPLY, [prompt_record("what now"), assistant_text_record(BARE_QUESTION_REPLY)]),
        (STANDING_QUESTION_REPLY, [prompt_record("status"), assistant_text_record(STANDING_QUESTION_REPLY)]),
        (
            BARE_QUESTION_REPLY,
            [
                prompt_record("first"),
                assistant_tool_record("AskUserQuestion", ASK_INPUT),
                prompt_record("second"),
                assistant_text_record(BARE_QUESTION_REPLY),
            ],
        ),
        (
            BARE_QUESTION_REPLY,
            [
                prompt_record("what now"),
                assistant_tool_record("mcp__ccd_turn__wrap_up", {"recap": "r", "ask": "Keep or revert?"}),
                assistant_text_record(BARE_QUESTION_REPLY),
            ],
        ),
    ],
)
def test_should_block_a_closing_question_no_question_tool_sent(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    reply_text: str,
    all_turn_records: list[dict[str, object]],
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", all_turn_records)
    _, stdout_text = run_gate(monkeypatch, capsys, reply_text, transcript_path)
    decision = json.loads(stdout_text)
    assert decision["decision"] == "block"
    assert "AskUserQuestion" in decision["reason"]
    assert "Rewrite the reply without it." not in decision["reason"]


@pytest.mark.parametrize(
    ("reply_text", "all_turn_records"),
    [
        (
            BARE_QUESTION_REPLY,
            [
                prompt_record("what now"),
                assistant_tool_record("AskUserQuestion", ASK_INPUT),
                assistant_text_record(BARE_QUESTION_REPLY),
            ],
        ),
        (
            BARE_QUESTION_REPLY,
            [
                prompt_record("what now"),
                assistant_text_record(BARE_QUESTION_REPLY),
                stop_feedback_record(),
                assistant_tool_record("AskUserQuestion", ASK_INPUT),
                assistant_text_record(BARE_QUESTION_REPLY),
            ],
        ),
        (REPORT_ONLY_REPLY, [prompt_record("status"), assistant_text_record(REPORT_ONLY_REPLY)]),
        (
            "Your question about the flaky test is resolved, but the PR is still open.",
            [prompt_record("status"), assistant_text_record("x")],
        ),
        (
            "Checks pass.\n> Keep it or revert?",
            [prompt_record("status"), assistant_text_record("x")],
        ),
        (
            "The question of the API is open-ended, and the decision is open source.",
            [prompt_record("status"), assistant_text_record("x")],
        ),
        (
            "The log shows:\n\n```\nretry?\n```",
            [prompt_record("status"), assistant_text_record("x")],
        ),
        (
            "He wrote:\n\n> Keep it or revert it?",
            [prompt_record("status"), assistant_text_record("x")],
        ),
        (
            "The flag reads `--confirm?`",
            [prompt_record("status"), assistant_text_record("x")],
        ),
    ],
)
def test_should_pass_a_reply_whose_question_went_through_the_tool_or_that_asks_nothing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    reply_text: str,
    all_turn_records: list[dict[str, object]],
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", all_turn_records)
    exit_code, stdout_text = run_gate(monkeypatch, capsys, reply_text, transcript_path)
    assert exit_code == 0
    assert stdout_text == ""


def test_should_pass_a_closing_question_when_the_transcript_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _, stdout_text = run_gate(monkeypatch, capsys, BARE_QUESTION_REPLY, tmp_path / "missing.jsonl")
    assert stdout_text == ""
