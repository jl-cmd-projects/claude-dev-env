import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import chat_reply_gate
from hooks_constants.chat_reply_gate_constants import REPLY_LIMIT_REMINDER, SHOWN_DRAFT_HEADING
from hooks_constants.reply_length_gate_constants import MAXIMUM_SENTENCE_COUNT

CHAT_REPLY_GATE_SCRIPT = Path(__file__).resolve().parent / "chat_reply_gate.py"

OVER_LIMIT_SENTENCES = [
    f"Status line {each_number} is ready." for each_number in range(MAXIMUM_SENTENCE_COUNT + 1)
]
OVER_LIMIT_REPLY = " ".join(OVER_LIMIT_SENTENCES)
FIRST_HELD_BATCH = " ".join(OVER_LIMIT_SENTENCES[: len(OVER_LIMIT_SENTENCES) // 2])
LAST_HELD_BATCH = " ".join(OVER_LIMIT_SENTENCES[len(OVER_LIMIT_SENTENCES) // 2 :])
THREE_SENTENCE_REPLY = "PR one merged. PR two is queued. Nothing else is open."
PASSING_DRAFT = "PR one merged. Two others wait."


@pytest.fixture(autouse=True)
def default_banned_words(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_REPLY_BANNED_WORDS_PATH", str(tmp_path / "absent.json"))
    monkeypatch.delenv("CHAT_REPLY_DRAFTER_ACTIVE", raising=False)
    monkeypatch.setattr(chat_reply_gate, "log_hook_block", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_reply_gate.tempfile, "gettempdir", lambda: str(tmp_path))


def run_hook(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    hook_input: dict[str, object],
) -> tuple[int, dict[str, object] | None]:
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = chat_reply_gate.main()
    output_text = capsys.readouterr().out
    return exit_code, json.loads(output_text)["hookSpecificOutput"] if output_text else None


def display_input(delta: str, is_final: bool = True) -> dict[str, object]:
    return {
        "hook_event_name": "MessageDisplay",
        "session_id": "abc",
        "message_id": "m1",
        "delta": delta,
        "final": is_final,
    }


def test_should_show_a_passing_draft_in_place_of_a_long_reply(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(chat_reply_gate, "ask_drafter", lambda *_args: PASSING_DRAFT)
    exit_code, hook_output = run_hook(monkeypatch, capsys, display_input(OVER_LIMIT_REPLY))
    assert exit_code == 0
    assert hook_output == {"hookEventName": "MessageDisplay", "displayContent": PASSING_DRAFT}


def test_should_show_a_reply_within_the_limit_unchanged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(chat_reply_gate, "ask_drafter", lambda *_args: pytest.fail("drafter called"))
    exit_code, hook_output = run_hook(monkeypatch, capsys, display_input(THREE_SENTENCE_REPLY))
    assert exit_code == 0
    assert hook_output is None


def test_should_hold_batches_until_the_last_one_arrives(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_requests: list[str] = []
    monkeypatch.setattr(
        chat_reply_gate,
        "ask_drafter",
        lambda reply_text, _violation: all_requests.append(reply_text) or PASSING_DRAFT,
    )
    _, first_output = run_hook(
        monkeypatch, capsys, display_input(FIRST_HELD_BATCH + "\n", False)
    )
    _, last_output = run_hook(
        monkeypatch, capsys, display_input(LAST_HELD_BATCH)
    )
    assert first_output == {"hookEventName": "MessageDisplay", "displayContent": ""}
    assert last_output == {"hookEventName": "MessageDisplay", "displayContent": PASSING_DRAFT}
    assert all_requests == [FIRST_HELD_BATCH + "\n" + LAST_HELD_BATCH]


def test_should_show_the_whole_held_message_when_it_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_hook(monkeypatch, capsys, display_input("PR one merged.\n", False))
    _, hook_output = run_hook(monkeypatch, capsys, display_input("Nothing else is open."))
    assert hook_output == {
        "hookEventName": "MessageDisplay",
        "displayContent": "PR one merged.\nNothing else is open.",
    }


def test_should_show_the_original_when_no_draft_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_calls: list[str] = []
    monkeypatch.setattr(
        chat_reply_gate,
        "ask_drafter",
        lambda reply_text, _violation: all_calls.append(reply_text) or OVER_LIMIT_REPLY,
    )
    _, hook_output = run_hook(monkeypatch, capsys, display_input(OVER_LIMIT_REPLY))
    assert hook_output is None
    assert len(all_calls) == 2


def test_should_tell_the_agent_which_draft_the_user_saw(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(chat_reply_gate, "ask_drafter", lambda *_args: PASSING_DRAFT)
    prompt_input = {"hook_event_name": "UserPromptSubmit", "session_id": "abc"}
    _, first_output = run_hook(monkeypatch, capsys, prompt_input)
    run_hook(monkeypatch, capsys, display_input(OVER_LIMIT_REPLY))
    _, second_output = run_hook(monkeypatch, capsys, prompt_input)
    _, third_output = run_hook(monkeypatch, capsys, prompt_input)
    assert first_output is not None and second_output is not None
    assert str(first_output["additionalContext"]) == REPLY_LIMIT_REMINDER
    assert second_output["additionalContext"] == SHOWN_DRAFT_HEADING + PASSING_DRAFT
    assert third_output is None


def _prompt_input(transcript_path: Path) -> dict[str, object]:
    return {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "abc",
        "prompt": "status?",
        "transcript_path": str(transcript_path),
    }


def test_should_add_the_reply_limit_once_per_session_and_again_after_a_compaction(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(json.dumps({"type": "user"}) + "\n", encoding="utf-8")
    _, first_output = run_hook(monkeypatch, capsys, _prompt_input(transcript_path))
    _, second_output = run_hook(monkeypatch, capsys, _prompt_input(transcript_path))
    with transcript_path.open("a", encoding="utf-8") as transcript:
        transcript.write(json.dumps({"type": "system", "subtype": "compact_boundary"}) + "\n")
    _, after_compaction_output = run_hook(monkeypatch, capsys, _prompt_input(transcript_path))
    _, later_output = run_hook(monkeypatch, capsys, _prompt_input(transcript_path))
    assert first_output is not None
    assert first_output["additionalContext"] == REPLY_LIMIT_REMINDER
    assert second_output is None
    assert after_compaction_output is not None
    assert after_compaction_output["additionalContext"] == REPLY_LIMIT_REMINDER
    assert later_output is None


def test_replay_of_two_prompts_and_a_compaction_through_the_script(tmp_path: Path) -> None:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(json.dumps({"type": "user"}) + "\n", encoding="utf-8")
    environment = {
        **os.environ,
        "TMP": str(tmp_path),
        "TEMP": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "CLAUDE_REPLY_BANNED_WORDS_PATH": str(tmp_path / "absent.json"),
    }
    environment.pop("CHAT_REPLY_DRAFTER_ACTIVE", None)

    def replay_prompt() -> str:
        return subprocess.run(
            [sys.executable, str(CHAT_REPLY_GATE_SCRIPT)],
            input=json.dumps(_prompt_input(transcript_path)),
            capture_output=True,
            text=True,
            env=environment,
            check=True,
        ).stdout

    first_stdout = replay_prompt()
    second_stdout = replay_prompt()
    with transcript_path.open("a", encoding="utf-8") as transcript:
        transcript.write(json.dumps({"type": "system", "subtype": "compact_boundary"}) + "\n")
    after_compaction_stdout = replay_prompt()
    assert REPLY_LIMIT_REMINDER in json.loads(first_stdout)["hookSpecificOutput"]["additionalContext"]
    assert second_stdout == ""
    assert (
        REPLY_LIMIT_REMINDER
        in json.loads(after_compaction_stdout)["hookSpecificOutput"]["additionalContext"]
    )


def test_should_delete_the_shown_draft_at_session_end(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(chat_reply_gate, "ask_drafter", lambda *_args: PASSING_DRAFT)
    run_hook(monkeypatch, capsys, {"hook_event_name": "UserPromptSubmit", "session_id": "abc"})
    run_hook(monkeypatch, capsys, display_input(OVER_LIMIT_REPLY))
    shown_draft_path = chat_reply_gate.state_file_path("claude-chat-reply-shown-", "abc")
    assert shown_draft_path.exists()
    assert list(Path(chat_reply_gate.tempfile.gettempdir()).glob("claude-once-*"))
    exit_code, hook_output = run_hook(
        monkeypatch, capsys, {"hook_event_name": "SessionEnd", "session_id": "abc"}
    )
    assert exit_code == 0
    assert hook_output is None
    assert not shown_draft_path.exists()
    assert not list(Path(chat_reply_gate.tempfile.gettempdir()).glob("claude-once-*"))


def test_should_add_the_reply_limit_to_a_prompt_with_no_session_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, hook_output = run_hook(
        monkeypatch, capsys, {"hook_event_name": "UserPromptSubmit", "prompt": "status?"}
    )
    assert exit_code == 0
    assert hook_output is not None
    assert hook_output["hookEventName"] == "UserPromptSubmit"
    assert f"{MAXIMUM_SENTENCE_COUNT} sentences or fewer" in str(hook_output["additionalContext"])


def test_should_do_nothing_inside_the_drafter_process(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CHAT_REPLY_DRAFTER_ACTIVE", "1")
    exit_code, hook_output = run_hook(monkeypatch, capsys, display_input(OVER_LIMIT_REPLY))
    assert exit_code == 0
    assert hook_output is None


def test_should_ignore_the_stop_event(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, hook_output = run_hook(
        monkeypatch,
        capsys,
        {"hook_event_name": "Stop", "last_assistant_message": OVER_LIMIT_REPLY},
    )
    assert exit_code == 0
    assert hook_output is None


def test_ask_drafter_should_read_the_result_field(monkeypatch: pytest.MonkeyPatch) -> None:
    class CompletedDrafter:
        stdout = json.dumps({"result": f"  {PASSING_DRAFT}\n"})

    all_commands: list[list[str]] = []
    monkeypatch.setattr(chat_reply_gate.shutil, "which", lambda _name: "C:/npm/claude.cmd")
    monkeypatch.setattr(
        chat_reply_gate.subprocess,
        "run",
        lambda command, **_kwargs: all_commands.append(command) or CompletedDrafter(),
    )
    assert chat_reply_gate.ask_drafter(OVER_LIMIT_REPLY, "too long") == PASSING_DRAFT
    assert all_commands[0][:4] == ["C:/npm/claude.cmd", "-p", "--model", "haiku"]


def test_ask_drafter_should_return_none_for_an_error_result(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailedDrafter:
        stdout = json.dumps({"is_error": True, "result": "Credit balance is too low"})

    monkeypatch.setattr(chat_reply_gate.subprocess, "run", lambda *_args, **_kwargs: FailedDrafter())
    assert chat_reply_gate.ask_drafter(OVER_LIMIT_REPLY, "too long") is None


def test_should_forget_the_shown_draft_when_a_later_reply_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(chat_reply_gate, "ask_drafter", lambda *_args: PASSING_DRAFT)
    run_hook(monkeypatch, capsys, display_input(OVER_LIMIT_REPLY))
    run_hook(monkeypatch, capsys, {**display_input(THREE_SENTENCE_REPLY), "message_id": "m2"})
    _, hook_output = run_hook(monkeypatch, capsys, {"hook_event_name": "UserPromptSubmit", "session_id": "abc"})
    assert hook_output is not None
    assert PASSING_DRAFT not in str(hook_output["additionalContext"])


def test_should_show_a_batch_without_a_message_id_as_it_is(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(chat_reply_gate, "ask_drafter", lambda *_args: pytest.fail("drafter called"))
    batch_input = {**display_input("PR one merged. PR two", is_final=False), "message_id": None}
    exit_code, hook_output = run_hook(monkeypatch, capsys, batch_input)
    assert exit_code == 0
    assert hook_output is None


def test_drafter_environment_should_carry_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent")
    environment = chat_reply_gate.drafter_environment()
    assert environment["CHAT_REPLY_DRAFTER_ACTIVE"] == "1"
    assert "CLAUDE_CODE_SESSION_ID" not in environment


def test_state_file_path_should_strip_unsafe_characters(tmp_path: Path) -> None:
    state_path = chat_reply_gate.state_file_path("claude-chat-reply-held-", "../a b/c")
    assert state_path == tmp_path / "claude-chat-reply-held-abc.txt"
