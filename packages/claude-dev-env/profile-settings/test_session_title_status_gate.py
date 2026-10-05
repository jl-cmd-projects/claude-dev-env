"""Run the installed session-title gate as the Stop hook runs it."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

GATE_SOURCE_DIRECTORY = Path(__file__).resolve().parent
GATE_FILE_NAME = "session_title_status_gate.py"
ALL_GATE_RELATIVE_PATHS = (
    Path(GATE_FILE_NAME),
    Path("config") / "__init__.py",
    Path("config") / "session_title_gate_constants.py",
)
TITLE_TOOL_NAME = "mcp__claude-code-remote__set_session_title"


def _install_gate(claude_directory: Path) -> Path:
    for each_relative_path in ALL_GATE_RELATIVE_PATHS:
        target_path = claude_directory / each_relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(GATE_SOURCE_DIRECTORY / each_relative_path, target_path)
    return claude_directory / GATE_FILE_NAME


def _user_text_entry(text: str) -> dict:
    return {"type": "user", "message": {"content": text}}


def _title_call_entry() -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": TITLE_TOOL_NAME, "input": {}}]
        },
    }


def _run_gate(
    tmp_path: Path, all_entries: list[dict], is_stop_hook_active: bool = False
) -> str:
    gate_path = _install_gate(tmp_path / ".claude")
    transcript_path = tmp_path / "transcript.jsonl"
    transcript_path.write_text(
        "\n".join(json.dumps(each_entry) for each_entry in all_entries) + "\n\n",
        encoding="utf-8",
    )
    payload = {
        "transcript_path": str(transcript_path),
        "stop_hook_active": is_stop_hook_active,
    }
    gate_run = subprocess.run(
        [sys.executable, str(gate_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return gate_run.stdout


def should_allow_stop_when_title_follows_last_user_text(tmp_path: Path) -> None:
    assert (
        _run_gate(tmp_path, [_user_text_entry("fix the bug"), _title_call_entry()])
        == ""
    )


def should_block_stop_when_user_text_follows_last_title(tmp_path: Path) -> None:
    gate_output = _run_gate(
        tmp_path, [_title_call_entry(), _user_text_entry("one more thing")]
    )

    decision = json.loads(gate_output)
    assert decision["decision"] == "block"
    assert "set_session_title" in decision["reason"]


def should_allow_stop_when_stop_hook_is_already_active(tmp_path: Path) -> None:
    assert (
        _run_gate(tmp_path, [_user_text_entry("fix the bug")], is_stop_hook_active=True)
        == ""
    )


def should_allow_stop_when_transcript_is_missing(tmp_path: Path) -> None:
    gate_path = _install_gate(tmp_path / ".claude")
    payload = {"transcript_path": str(tmp_path / "absent.jsonl")}

    gate_run = subprocess.run(
        [sys.executable, str(gate_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )

    assert gate_run.stdout == ""
