import io
import json
from pathlib import Path

import pytest

import chat_reply_gate

FOUR_SENTENCE_REPLY = "PR one merged. PR two is queued. PR three needs a fix. Nothing else is open."
THREE_SENTENCE_REPLY = "PR one merged. PR two is queued. Nothing else is open."


@pytest.fixture(autouse=True)
def default_banned_words(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_REPLY_BANNED_WORDS_PATH", str(tmp_path / "absent.json"))
    monkeypatch.setattr(chat_reply_gate, "log_hook_block", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_reply_gate.tempfile, "gettempdir", lambda: str(tmp_path))


def run_hook(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    hook_input: dict[str, object],
) -> tuple[int, str, str]:
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = chat_reply_gate.main()
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_should_block_stop_when_reply_has_four_sentences(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _, error_text = run_hook(
        monkeypatch,
        capsys,
        {"hook_event_name": "Stop", "last_assistant_message": FOUR_SENTENCE_REPLY},
    )
    assert exit_code == 2
    assert "Reply too long: 4 sentences, limit 3." in error_text
    assert "Rewrite the reply" in error_text


def test_should_allow_stop_when_reply_fits_the_limit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _, error_text = run_hook(
        monkeypatch,
        capsys,
        {"hook_event_name": "Stop", "last_assistant_message": THREE_SENTENCE_REPLY},
    )
    assert exit_code == 0
    assert error_text == ""


def test_should_allow_stop_after_three_rewrites_in_one_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stop_input = {
        "hook_event_name": "Stop",
        "session_id": "abc",
        "last_assistant_message": FOUR_SENTENCE_REPLY,
    }
    all_exit_codes = [run_hook(monkeypatch, capsys, stop_input)[0] for _ in range(4)]
    assert all_exit_codes == [2, 2, 2, 0]


def test_should_block_again_after_the_next_user_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stop_input = {
        "hook_event_name": "Stop",
        "session_id": "abc",
        "last_assistant_message": FOUR_SENTENCE_REPLY,
    }
    for _ in range(3):
        run_hook(monkeypatch, capsys, stop_input)
    run_hook(monkeypatch, capsys, {"hook_event_name": "UserPromptSubmit", "session_id": "abc"})
    exit_code, _, _ = run_hook(monkeypatch, capsys, stop_input)
    assert exit_code == 2


def test_should_allow_stop_when_no_reply_text_arrives(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _, _ = run_hook(monkeypatch, capsys, {"hook_event_name": "Stop"})
    assert exit_code == 0


def test_should_add_the_reply_limit_on_each_user_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, output_text, _ = run_hook(
        monkeypatch, capsys, {"hook_event_name": "UserPromptSubmit", "prompt": "status?"}
    )
    hook_output = json.loads(output_text)["hookSpecificOutput"]
    assert exit_code == 0
    assert hook_output["hookEventName"] == "UserPromptSubmit"
    assert "3 sentences or fewer" in hook_output["additionalContext"]


def test_stop_block_reason_should_name_an_em_dash() -> None:
    block_reason = chat_reply_gate.stop_block_reason(
        {"last_assistant_message": "PR one merged \u2014 nothing else."}
    )
    assert block_reason is not None
    assert block_reason.startswith("An em dash is in the text.")


def test_rewrite_count_path_should_strip_unsafe_session_characters(tmp_path: Path) -> None:
    count_path = chat_reply_gate.rewrite_count_path("../a b/c")
    assert count_path == tmp_path / "claude-chat-reply-rewrites-abc.txt"


def test_read_rewrite_count_should_return_zero_for_a_missing_file(tmp_path: Path) -> None:
    assert chat_reply_gate.read_rewrite_count(tmp_path / "absent.txt") == 0


def test_write_rewrite_count_should_store_the_count(tmp_path: Path) -> None:
    count_path = tmp_path / "count.txt"
    chat_reply_gate.write_rewrite_count(count_path, 2)
    assert chat_reply_gate.read_rewrite_count(count_path) == 2


def test_write_reply_limit_reminder_should_print_additional_context(
    capsys: pytest.CaptureFixture[str],
) -> None:
    chat_reply_gate.write_reply_limit_reminder()
    hook_output = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert "Lead with the outcome" in hook_output["additionalContext"]
