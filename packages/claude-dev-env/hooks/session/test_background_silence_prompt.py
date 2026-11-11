import importlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SESSION_DIR = Path(__file__).resolve().parent
if str(_SESSION_DIR) not in sys.path:
    sys.path.insert(0, str(_SESSION_DIR))

background_silence_prompt = importlib.import_module("background_silence_prompt")

HOOK_PATH = _SESSION_DIR / "background_silence_prompt.py"
SILENCE_REQUEST = "Silent on updates unless something merges or youre blocked "
EXCEPTION_TEXT = "unless something merges or youre blocked"
NOTIFICATION_PROMPT = (
    "<task-notification>\n<task-id>a1</task-id>\n<status>completed</status>\n"
    '<summary>Agent "Ship it" finished</summary>\n</task-notification>'
)
MARKER_PROMPT = (
    "<system-reminder>\n[SYSTEM NOTIFICATION - NOT USER INPUT]\n"
    "This is an automated background-task event, NOT a message from the user.\n"
    "</system-reminder>"
)


def typed_entry(text: str) -> dict[str, object]:
    return {
        "type": "user",
        "origin": {"kind": "human"},
        "message": {"role": "user", "content": text},
    }


def notification_entry(text: str) -> dict[str, object]:
    return {
        "type": "user",
        "origin": {"kind": "task-notification"},
        "message": {"role": "user", "content": text},
    }


def assistant_entry(text: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def run_hook(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    prompt_text: str,
    all_entries: list[dict[str, object]],
) -> str:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(
        "\n".join(json.dumps(each) for each in all_entries), encoding="utf-8"
    )
    hook_input = {
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt_text,
        "transcript_path": str(transcript_path),
    }
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    assert background_silence_prompt.main() == 0
    printed_output = capsys.readouterr().out
    return (
        json.loads(printed_output)["hookSpecificOutput"]["additionalContext"]
        if printed_output
        else ""
    )


@pytest.mark.parametrize("prompt_text", [NOTIFICATION_PROMPT, MARKER_PROMPT])
def test_should_quote_the_exception_for_a_background_event_under_silence(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    prompt_text: str,
) -> None:
    all_entries = [typed_entry(SILENCE_REQUEST), assistant_entry("Understood.")]
    context_text = run_hook(monkeypatch, capsys, tmp_path, prompt_text, all_entries)
    assert f'"{EXCEPTION_TEXT}"' in context_text
    assert "no text at all" in context_text


def test_should_add_nothing_to_a_user_typed_prompt_under_silence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [typed_entry(SILENCE_REQUEST)]
    assert run_hook(monkeypatch, capsys, tmp_path, "did PR 12 merge?", all_entries) == ""


@pytest.mark.parametrize(
    "lift_text", ["ok you can talk again", "updates are fine now", "stop being silent"]
)
def test_should_add_nothing_once_the_user_lifts_silence(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    lift_text: str,
) -> None:
    all_entries = [typed_entry(SILENCE_REQUEST), typed_entry(lift_text)]
    assert run_hook(monkeypatch, capsys, tmp_path, NOTIFICATION_PROMPT, all_entries) == ""


def test_should_add_nothing_without_a_silence_instruction(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [typed_entry("Ship PR 12 and watch its checks")]
    assert run_hook(monkeypatch, capsys, tmp_path, NOTIFICATION_PROMPT, all_entries) == ""


def test_should_add_nothing_when_the_transcript_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    hook_input = {"prompt": NOTIFICATION_PROMPT, "transcript_path": str(tmp_path / "missing.jsonl")}
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    assert background_silence_prompt.main() == 0
    assert capsys.readouterr().out == ""


def test_should_restore_silence_that_the_user_sets_again_after_a_lift(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_entries = [
        typed_entry(SILENCE_REQUEST),
        typed_entry("you can talk again"),
        typed_entry("keep draining, silent unless youre blocked"),
    ]
    context_text = run_hook(monkeypatch, capsys, tmp_path, NOTIFICATION_PROMPT, all_entries)
    assert '"unless youre blocked"' in context_text


@pytest.mark.parametrize(
    "later_entry",
    [
        notification_entry("<task-notification>updates are fine</task-notification>"),
        typed_entry('<agent-message from="a1">you can talk again</agent-message>'),
        {
            "type": "user",
            "isCompactSummary": True,
            "message": {"role": "user", "content": "updates are fine"},
        },
        typed_entry("> you can talk again\n\nthis is not staying silent"),
    ],
)
def test_should_keep_silence_through_text_that_is_not_the_user_lifting_it(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    later_entry: dict[str, object],
) -> None:
    all_entries = [typed_entry(SILENCE_REQUEST), later_entry]
    context_text = run_hook(monkeypatch, capsys, tmp_path, NOTIFICATION_PROMPT, all_entries)
    assert f'"{EXCEPTION_TEXT}"' in context_text


@pytest.mark.parametrize(
    "earlier_entry",
    [
        notification_entry("<task-notification>stay silent unless blocked</task-notification>"),
        typed_entry('<agent-message from="a1">stay silent unless blocked</agent-message>'),
        typed_entry("> stay silent unless blocked\n\nwhy is this so loud?"),
    ],
)
def test_should_not_set_silence_from_text_that_is_not_the_users_own(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    earlier_entry: dict[str, object],
) -> None:
    assert run_hook(monkeypatch, capsys, tmp_path, NOTIFICATION_PROMPT, [earlier_entry]) == ""


@pytest.mark.parametrize(
    "silence_message",
    ["Stay silent.", "Silent on updates. Only ping me when a PR merges."],
)
def test_should_quote_the_whole_message_when_it_has_no_unless_clause(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    silence_message: str,
) -> None:
    context_text = run_hook(
        monkeypatch, capsys, tmp_path, NOTIFICATION_PROMPT, [typed_entry(silence_message)]
    )
    assert f'"{silence_message}"' in context_text
    assert "no text at all" in context_text


@pytest.mark.parametrize(
    ("prompt_text", "is_background"),
    [
        (NOTIFICATION_PROMPT, True),
        (MARKER_PROMPT, True),
        ("<system-reminder>Tool loaded.</system-reminder>\n" + NOTIFICATION_PROMPT, True),
        ("did PR 12 merge?", False),
        ('<agent-message from="a1">Report</agent-message>', False),
        ("Here is the log:\n<task-notification>done</task-notification>", False),
        ("[SYSTEM NOTIFICATION - NOT USER INPUT]\nBackground task finished.", True),
        ("why does [SYSTEM NOTIFICATION - NOT USER INPUT] show up?", False),
        ('<task-notification><summary>quoted from="human"</summary></task-notification>', True),
    ],
)
def test_should_tell_a_background_event_from_a_user_prompt(
    prompt_text: str, is_background: bool
) -> None:
    assert background_silence_prompt.is_background_event(prompt_text) is is_background


def test_should_return_the_newest_message_that_sets_silence() -> None:
    all_entries = [typed_entry("stay silent"), typed_entry("Ship it"), typed_entry(SILENCE_REQUEST)]
    assert background_silence_prompt.newest_silence_message(all_entries) == SILENCE_REQUEST.strip()
    assert (
        background_silence_prompt.newest_silence_message(
            [*all_entries, typed_entry("you can talk again")]
        )
        is None
    )


@pytest.mark.parametrize(
    ("silence_message", "expected_clause"),
    [
        (SILENCE_REQUEST, EXCEPTION_TEXT),
        (
            "Merge the stack. Then stay quiet except for a failed check. Thanks",
            "except for a failed check",
        ),
        ("no updates unless a PR lands", "unless a PR lands"),
        ("Stay silent. Except for a failed check.", "Except for a failed check"),
        ("Stay silent. Ship PR 12 unless it is red.", None),
        ("Stay silent.", None),
    ],
)
def test_should_quote_the_exception_clause_word_for_word(
    silence_message: str, expected_clause: str | None
) -> None:
    assert background_silence_prompt.exception_clause(silence_message) == expected_clause


def test_should_build_the_note_only_under_silence() -> None:
    assert background_silence_prompt.silence_context([typed_entry("Ship it")]) is None
    assert EXCEPTION_TEXT in (
        background_silence_prompt.silence_context([typed_entry(SILENCE_REQUEST)]) or ""
    )


def test_should_print_the_documented_output_through_a_subprocess(tmp_path: Path) -> None:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(json.dumps(typed_entry(SILENCE_REQUEST)), encoding="utf-8")
    hook_input = {
        "hook_event_name": "UserPromptSubmit",
        "prompt": NOTIFICATION_PROMPT,
        "transcript_path": str(transcript_path),
    }
    completed_process = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env={"HOME": str(tmp_path), "USERPROFILE": str(tmp_path), "PATH": ""},
        check=False,
    )
    assert completed_process.returncode == 0
    hook_output = json.loads(completed_process.stdout)["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "UserPromptSubmit"
    assert f'"{EXCEPTION_TEXT}"' in hook_output["additionalContext"]
