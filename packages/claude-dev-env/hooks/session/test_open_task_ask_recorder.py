import json
import subprocess
import sys
from pathlib import Path

RECORDER_PATH = Path(__file__).resolve().parent / "open_task_ask_recorder.py"
SESSION_ID = "s-123"


def submit_prompt(home_directory: Path, prompt_text: str) -> subprocess.CompletedProcess[str]:
    hook_input = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": SESSION_ID,
        "prompt": prompt_text,
    }
    return subprocess.run(
        [sys.executable, str(RECORDER_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env={
            "HOME": str(home_directory),
            "USERPROFILE": str(home_directory),
            "PATH": "",
        },
        check=False,
    )


def recorded_ask_ids(home_directory: Path) -> list[str]:
    asks_path = home_directory / ".claude" / "open-task-asks" / f"{SESSION_ID}.json"
    all_prompts = json.loads(asks_path.read_text(encoding="utf-8"))["prompts"]
    return [each_prompt["ask_id"] for each_prompt in all_prompts if each_prompt["ask_id"]]


def test_should_record_each_ask_outside_the_task_store_and_stay_silent(
    tmp_path: Path,
) -> None:
    first_process = submit_prompt(tmp_path, "Export the OneUI8 and OneUI9 APKs and submit them")
    submit_prompt(tmp_path, "did the export fail?")
    submit_prompt(tmp_path, "<task-notification>\n<task-id>b1</task-id>\n</task-notification>")
    submit_prompt(tmp_path, "can you check the release dates in neon?")
    assert (first_process.returncode, first_process.stdout) == (0, "")
    assert recorded_ask_ids(tmp_path) == ["ask-1", "ask-2"]
    assert not (tmp_path / ".claude" / "tasks").exists()


def test_should_allow_malformed_input(tmp_path: Path) -> None:
    completed_process = subprocess.run(
        [sys.executable, str(RECORDER_PATH)],
        input="not json",
        capture_output=True,
        text=True,
        env={"HOME": str(tmp_path), "USERPROFILE": str(tmp_path), "PATH": ""},
        check=False,
    )
    assert (completed_process.returncode, completed_process.stdout) == (0, "")
