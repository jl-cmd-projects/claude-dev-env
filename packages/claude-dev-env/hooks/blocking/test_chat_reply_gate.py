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


MID_TURN_NARRATION = (
    "These numbers mean the hook never fired. Each headless run reported this session's id,"
    " and the eval settings had no UserPromptSubmit entry to reset the counter."
)
PROMPT_ENTRY = {"type": "user", "message": {"role": "user", "content": "Enforce it everywhere."}}


def assistant_entry(block: dict[str, object]) -> dict[str, object]:
    return {"type": "assistant", "message": {"id": "m1", "role": "assistant", "content": [block]}}


def text_entry(text: str) -> dict[str, object]:
    return assistant_entry({"type": "text", "text": text})


def call_entry(tool_use_id: str) -> dict[str, object]:
    return assistant_entry({"type": "tool_use", "id": tool_use_id, "name": "Bash", "input": {}})


def result_entry(tool_use_id: str) -> dict[str, object]:
    return {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use_id}]},
    }


def post_tool_use_input(transcript_path: Path, tool_use_id: str) -> dict[str, object]:
    return {
        "hook_event_name": "PostToolUse",
        "tool_use_id": tool_use_id,
        "transcript_path": str(transcript_path),
    }


def write_transcript(transcript_path: Path, all_entries: list[dict[str, object]]) -> Path:
    transcript_path.write_text(
        "".join(json.dumps(each_entry) + "\n" for each_entry in all_entries), encoding="utf-8"
    )
    return transcript_path


def test_should_block_post_tool_use_when_mid_turn_text_breaks_the_rule(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_transcript(
        tmp_path / "session.jsonl",
        [PROMPT_ENTRY, call_entry("call_1"), result_entry("call_1"), text_entry(MID_TURN_NARRATION), call_entry("call_2")],
    )
    exit_code, _, error_text = run_hook(monkeypatch, capsys, post_tool_use_input(transcript_path, "call_2"))
    assert exit_code == 2
    assert error_text.startswith("The text you sent before this tool call breaks the reply rule.")
    assert "Sentence too long: 19 words, limit 15" in error_text


def test_should_allow_post_tool_use_when_mid_turn_text_is_a_short_status_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_transcript(
        tmp_path / "session.jsonl",
        [PROMPT_ENTRY, text_entry("Running the eval again."), call_entry("call_1")],
    )
    exit_code, _, error_text = run_hook(monkeypatch, capsys, post_tool_use_input(transcript_path, "call_1"))
    assert exit_code == 0
    assert error_text == ""


def test_should_allow_post_tool_use_from_a_subagent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_transcript(
        tmp_path / "session.jsonl", [PROMPT_ENTRY, text_entry(MID_TURN_NARRATION), call_entry("call_1")]
    )
    hook_input = post_tool_use_input(transcript_path, "call_1") | {"agent_id": "agent_7"}
    exit_code, _, _ = run_hook(monkeypatch, capsys, hook_input)
    assert exit_code == 0


def test_text_before_call_should_give_sibling_calls_no_text() -> None:
    all_entries = [PROMPT_ENTRY, text_entry(MID_TURN_NARRATION), call_entry("call_1"), call_entry("call_2")]
    assert chat_reply_gate.text_before_call(all_entries, "call_1") == MID_TURN_NARRATION
    assert chat_reply_gate.text_before_call(all_entries, "call_2") == ""


def test_text_before_call_should_return_none_for_an_unwritten_call() -> None:
    assert chat_reply_gate.text_before_call([PROMPT_ENTRY], "call_9") is None


def test_wait_for_text_before_call_should_read_the_transcript(tmp_path: Path) -> None:
    transcript_path = write_transcript(
        tmp_path / "session.jsonl", [PROMPT_ENTRY, text_entry("Checking."), call_entry("call_1")]
    )
    assert chat_reply_gate.wait_for_text_before_call(transcript_path, "call_1") == "Checking."


def test_mid_turn_block_reason_should_name_the_violation(tmp_path: Path) -> None:
    transcript_path = write_transcript(
        tmp_path / "session.jsonl", [PROMPT_ENTRY, text_entry(MID_TURN_NARRATION), call_entry("call_1")]
    )
    block_reason = chat_reply_gate.mid_turn_block_reason(
        {"tool_use_id": "call_1", "transcript_path": str(transcript_path)}
    )
    assert block_reason is not None
    assert block_reason.endswith("with no process talk.")
