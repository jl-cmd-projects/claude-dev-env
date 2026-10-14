import io
import json
from pathlib import Path

import pytest

import chat_reply_gate

FOUR_SENTENCE_REPLY = "PR one merged. PR two is queued. PR three needs a fix. Nothing else is open."
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
    exit_code, hook_output = run_hook(monkeypatch, capsys, display_input(FOUR_SENTENCE_REPLY))
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
        monkeypatch, capsys, display_input("PR one merged. PR two is queued.\n", False)
    )
    _, last_output = run_hook(
        monkeypatch, capsys, display_input("PR three needs a fix. Nothing else is open.")
    )
    assert first_output == {"hookEventName": "MessageDisplay", "displayContent": ""}
    assert last_output == {"hookEventName": "MessageDisplay", "displayContent": PASSING_DRAFT}
    assert all_requests == [
        "PR one merged. PR two is queued.\nPR three needs a fix. Nothing else is open."
    ]


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
        lambda reply_text, _violation: all_calls.append(reply_text) or FOUR_SENTENCE_REPLY,
    )
    _, hook_output = run_hook(monkeypatch, capsys, display_input(FOUR_SENTENCE_REPLY))
    assert hook_output is None
    assert len(all_calls) == 2


def test_should_tell_the_agent_which_draft_the_user_saw(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(chat_reply_gate, "ask_drafter", lambda *_args: PASSING_DRAFT)
    run_hook(monkeypatch, capsys, display_input(FOUR_SENTENCE_REPLY))
    prompt_input = {"hook_event_name": "UserPromptSubmit", "session_id": "abc"}
    _, first_output = run_hook(monkeypatch, capsys, prompt_input)
    _, second_output = run_hook(monkeypatch, capsys, prompt_input)
    assert first_output is not None and second_output is not None
    assert str(first_output["additionalContext"]).endswith(PASSING_DRAFT)
    assert PASSING_DRAFT not in str(second_output["additionalContext"])


def test_should_delete_the_shown_draft_at_session_end(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(chat_reply_gate, "ask_drafter", lambda *_args: PASSING_DRAFT)
    run_hook(monkeypatch, capsys, display_input(FOUR_SENTENCE_REPLY))
    shown_draft_path = chat_reply_gate.state_file_path("claude-chat-reply-shown-", "abc")
    assert shown_draft_path.exists()
    exit_code, hook_output = run_hook(
        monkeypatch, capsys, {"hook_event_name": "SessionEnd", "session_id": "abc"}
    )
    assert exit_code == 0
    assert hook_output is None
    assert not shown_draft_path.exists()


def test_should_add_the_reply_limit_on_each_user_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, hook_output = run_hook(
        monkeypatch, capsys, {"hook_event_name": "UserPromptSubmit", "prompt": "status?"}
    )
    assert exit_code == 0
    assert hook_output is not None
    assert hook_output["hookEventName"] == "UserPromptSubmit"
    assert "3 sentences or fewer" in str(hook_output["additionalContext"])


def test_should_do_nothing_inside_the_drafter_process(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CHAT_REPLY_DRAFTER_ACTIVE", "1")
    exit_code, hook_output = run_hook(monkeypatch, capsys, display_input(FOUR_SENTENCE_REPLY))
    assert exit_code == 0
    assert hook_output is None


def test_should_ignore_the_stop_event(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, hook_output = run_hook(
        monkeypatch,
        capsys,
        {"hook_event_name": "Stop", "last_assistant_message": FOUR_SENTENCE_REPLY},
    )
    assert exit_code == 0
    assert hook_output is None


def test_ask_drafter_should_read_the_result_field(monkeypatch: pytest.MonkeyPatch) -> None:
    class CompletedDrafter:
        stdout = json.dumps({"result": f"  {PASSING_DRAFT}\n"})

    all_commands: list[list[str]] = []
    monkeypatch.setattr(
        chat_reply_gate.subprocess,
        "run",
        lambda command, **_kwargs: all_commands.append(command) or CompletedDrafter(),
    )
    assert chat_reply_gate.ask_drafter(FOUR_SENTENCE_REPLY, "too long") == PASSING_DRAFT
    assert all_commands[0][:4] == ["claude", "-p", "--model", "haiku"]


def test_drafter_environment_should_carry_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent")
    environment = chat_reply_gate.drafter_environment()
    assert environment["CHAT_REPLY_DRAFTER_ACTIVE"] == "1"
    assert "CLAUDE_CODE_SESSION_ID" not in environment


def test_state_file_path_should_strip_unsafe_characters(tmp_path: Path) -> None:
    state_path = chat_reply_gate.state_file_path("claude-chat-reply-held-", "../a b/c")
    assert state_path == tmp_path / "claude-chat-reply-held-abc.txt"
