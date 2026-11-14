import importlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from hooks_constants.open_tasks_stop_gate_constants import TASK_LIST_NUDGE

_SESSION_DIR = Path(__file__).resolve().parent
if str(_SESSION_DIR) not in sys.path:
    sys.path.insert(0, str(_SESSION_DIR))

tracking_nudge = importlib.import_module("tracking_nudge")

NUDGE_PATH = _SESSION_DIR / "tracking_nudge.py"
TITLE_TOOL = "mcp__claude-code-remote__set_session_title"
TOOL_LISTING = {"type": "attachment", "attachment": {"tools": [{"name": TITLE_TOOL}]}}


def titled_entries(title: str) -> list[dict[str, object]]:
    title_use = {"type": "tool_use", "id": "t1", "name": TITLE_TOOL, "input": {"title": title}}
    title_done = {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
    return [
        TOOL_LISTING,
        {"type": "assistant", "message": {"content": [title_use]}},
        {"type": "user", "message": {"content": [title_done]}},
    ]


def run_nudge(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    prompt_text: str,
    all_entries: list[dict[str, object]],
    session_id: str | None = None,
) -> str:
    transcript_path = tmp_path / "s.jsonl"
    transcript_path.write_text(
        "\n".join(json.dumps(each) for each in all_entries), encoding="utf-8"
    )
    hook_input: dict[str, object] = {
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt_text,
        "transcript_path": str(transcript_path),
    }
    if session_id is not None:
        hook_input["session_id"] = session_id
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    assert tracking_nudge.main() == 0
    printed_output = capsys.readouterr().out
    return (
        json.loads(printed_output)["hookSpecificOutput"]["additionalContext"]
        if printed_output
        else ""
    )


def test_should_remind_a_work_prompt_to_use_the_task_list(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    context_text = run_nudge(
        monkeypatch, capsys, tmp_path, "Export the APKs", titled_entries("⏳ Export")
    )
    assert "the session's task list tool" in context_text
    assert "TaskCreate" not in context_text
    assert "⏳ Export" not in context_text


COMPACTION_ENTRY = {"type": "system", "subtype": "compact_boundary"}


def test_should_add_the_task_list_note_once_per_session_and_again_after_a_compaction(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    entries = titled_entries("⏳ Export")

    def nudge(prompt_text: str, all_entries: list[dict[str, object]]) -> str:
        return run_nudge(monkeypatch, capsys, tmp_path, prompt_text, all_entries, "session_one")

    assert nudge("thanks!", entries) == ""
    assert TASK_LIST_NUDGE in nudge("Export the APKs", entries)
    assert nudge("Now sign the APKs", entries) == ""
    assert TASK_LIST_NUDGE in nudge("Upload the APKs", [*entries, COMPACTION_ENTRY])
    assert nudge("Tag the release", [*entries, COMPACTION_ENTRY]) == ""


def test_should_keep_the_title_note_on_each_ask_after_the_task_list_note_shows(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    entries = titled_entries("\U0001f6a9 Merge approval")
    run_nudge(monkeypatch, capsys, tmp_path, "Export the APKs", entries, "session_one")
    second_text = run_nudge(
        monkeypatch, capsys, tmp_path, "Now sign the APKs", entries, "session_one"
    )
    assert TASK_LIST_NUDGE not in second_text
    assert "\U0001f6a9 Merge approval" in second_text


@pytest.mark.parametrize("earlier_title", ["\U0001f6a9 Merge approval", "✅ Gate"])
def test_should_ask_to_refresh_a_title_that_says_the_session_waits_or_is_done(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    earlier_title: str,
) -> None:
    context_text = run_nudge(
        monkeypatch, capsys, tmp_path, "Export the APKs", titled_entries(earlier_title)
    )
    assert earlier_title in context_text
    assert TITLE_TOOL in context_text


@pytest.mark.parametrize(
    "prompt_text",
    ["did the export fail?", "thanks!", "<task-notification>done</task-notification>"],
)
def test_should_stay_silent_for_a_prompt_that_asks_for_no_work(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    prompt_text: str,
) -> None:
    assert (
        run_nudge(
            monkeypatch, capsys, tmp_path, prompt_text, titled_entries("\U0001f6a9 Merge approval")
        )
        == ""
    )


def test_should_skip_the_title_note_in_a_session_without_the_title_tool() -> None:
    assert tracking_nudge.title_nudge([], {}) is None
    assert tracking_nudge.title_nudge(titled_entries("✅ Gate"), {}) is not None


def test_should_build_the_note_only_for_a_work_prompt() -> None:
    assert tracking_nudge.ask_tracking_context("did it fail?", [], {}) is None
    assert "task list" in (tracking_nudge.ask_tracking_context("Export the APKs", [], {}) or "")


def test_should_print_the_documented_output_through_a_subprocess(tmp_path: Path) -> None:
    hook_input = {"hook_event_name": "UserPromptSubmit", "prompt": "Export the APKs"}
    completed_process = subprocess.run(
        [sys.executable, str(NUDGE_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env={"HOME": str(tmp_path), "USERPROFILE": str(tmp_path), "PATH": ""},
        check=False,
    )
    assert completed_process.returncode == 0
    hook_output = json.loads(completed_process.stdout)["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "UserPromptSubmit"
    assert "the session's task list tool" in hook_output["additionalContext"]


PACKAGE_ROOT = _SESSION_DIR.parent.parent
HOURGLASS_FORM = "'⏳ <name>'"
UNTITLED_ENTRIES: list[dict[str, object]] = [TOOL_LISTING]


def run_nudge_script(
    tmp_path: Path, prompt_text: str, all_entries: list[dict[str, object]]
) -> subprocess.CompletedProcess[str]:
    transcript_path = tmp_path / "script_session.jsonl"
    transcript_path.write_text(
        "".join(json.dumps(each) + "\n" for each in all_entries), encoding="utf-8"
    )
    hook_input = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "script_session",
        "prompt": prompt_text,
        "transcript_path": str(transcript_path),
    }
    environment = {**os.environ, "TMP": str(tmp_path), "TEMP": str(tmp_path), "TMPDIR": str(tmp_path)}
    return subprocess.run(
        [sys.executable, str(NUDGE_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def script_context(completed_process: subprocess.CompletedProcess[str]) -> str:
    if not completed_process.stdout:
        return ""
    return json.loads(completed_process.stdout)["hookSpecificOutput"]["additionalContext"]


def test_should_ask_for_a_first_title_in_a_titled_tool_session_with_no_title(tmp_path: Path) -> None:
    context_text = script_context(run_nudge_script(tmp_path, "Export the APKs", UNTITLED_ENTRIES))
    assert "no title yet" in context_text
    assert TITLE_TOOL in context_text
    assert HOURGLASS_FORM in context_text


def test_should_ask_for_a_first_title_at_most_once_in_a_session(tmp_path: Path) -> None:
    first_text = script_context(run_nudge_script(tmp_path, "Export the APKs", UNTITLED_ENTRIES))
    second_text = script_context(run_nudge_script(tmp_path, "Now sign the APKs", UNTITLED_ENTRIES))
    after_compaction_text = script_context(
        run_nudge_script(tmp_path, "Upload the APKs", [*UNTITLED_ENTRIES, COMPACTION_ENTRY])
    )
    assert "no title yet" in first_text
    assert "no title yet" not in second_text
    assert "no title yet" not in after_compaction_text


def test_should_not_spend_the_first_title_note_on_a_prompt_that_asks_for_no_work(
    tmp_path: Path,
) -> None:
    assert script_context(run_nudge_script(tmp_path, "did the export fail?", UNTITLED_ENTRIES)) == ""
    assert "no title yet" in script_context(
        run_nudge_script(tmp_path, "Export the APKs", UNTITLED_ENTRIES)
    )


def test_should_add_nothing_about_titles_in_a_session_without_a_title_tool(tmp_path: Path) -> None:
    context_text = script_context(run_nudge_script(tmp_path, "Export the APKs", [{"type": "user"}]))
    assert TASK_LIST_NUDGE in context_text
    assert "title" not in context_text


@pytest.mark.parametrize("earlier_title", ["\U0001f6a9 Merge approval", "✅ Gate"])
def test_should_keep_the_stale_title_note_through_the_script(
    tmp_path: Path, earlier_title: str
) -> None:
    context_text = script_context(
        run_nudge_script(tmp_path, "Export the APKs", titled_entries(earlier_title))
    )
    assert earlier_title in context_text
    assert TITLE_TOOL in context_text
    assert HOURGLASS_FORM in context_text


def test_should_add_no_title_note_when_the_title_already_shows_the_hourglass(tmp_path: Path) -> None:
    context_text = script_context(
        run_nudge_script(tmp_path, "Export the APKs", titled_entries("⏳ Export"))
    )
    assert TASK_LIST_NUDGE in context_text
    assert "title" not in context_text


@pytest.mark.parametrize(
    "all_entries",
    [UNTITLED_ENTRIES, [{"type": "user"}], [TOOL_LISTING, {"type": "assistant", "message": "broken"}]],
)
def test_should_never_block_the_prompt(
    tmp_path: Path, all_entries: list[dict[str, object]]
) -> None:
    completed_process = run_nudge_script(tmp_path, "Export the APKs", all_entries)
    assert (completed_process.returncode, completed_process.stderr) == (0, "")
    assert "decision" not in completed_process.stdout


def test_should_describe_the_prompt_note_and_no_title_send_back_in_the_docs() -> None:
    all_doc_texts = [
        (PACKAGE_ROOT / "docs" / "rule-guides" / "session-title.md").read_text(encoding="utf-8"),
        (PACKAGE_ROOT / "hooks" / "features" / "conduct-gates.md").read_text(encoding="utf-8"),
    ]
    for each_doc_text in all_doc_texts:
        assert "session_title_turn_gate" not in each_doc_text
        assert "No hook holds the end of a turn for the title." in each_doc_text
        assert "no title yet" in each_doc_text
        assert "tracking_nudge.py" in each_doc_text


def test_replay_of_two_asks_and_a_compaction_through_the_script(tmp_path: Path) -> None:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(json.dumps({"type": "user"}) + "\n", encoding="utf-8")
    environment = {**os.environ, "TMP": str(tmp_path), "TEMP": str(tmp_path), "TMPDIR": str(tmp_path)}

    def replay_ask(prompt_text: str) -> str:
        hook_input = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session_one",
            "prompt": prompt_text,
            "transcript_path": str(transcript_path),
        }
        return subprocess.run(
            [sys.executable, str(NUDGE_PATH)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            env=environment,
            check=True,
        ).stdout

    first_stdout = replay_ask("Export the APKs")
    second_stdout = replay_ask("Now sign the APKs")
    with transcript_path.open("a", encoding="utf-8") as transcript:
        transcript.write(json.dumps(COMPACTION_ENTRY) + "\n")
    after_compaction_stdout = replay_ask("Upload the APKs")
    assert TASK_LIST_NUDGE in json.loads(first_stdout)["hookSpecificOutput"]["additionalContext"]
    assert second_stdout == ""
    assert (
        TASK_LIST_NUDGE
        in json.loads(after_compaction_stdout)["hookSpecificOutput"]["additionalContext"]
    )
