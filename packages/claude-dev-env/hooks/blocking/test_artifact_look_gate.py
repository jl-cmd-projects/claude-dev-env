"""Behavior tests for the artifact look gate.

The refused case replays a session that wrote a page and published it with no
render in between, the way a text-card page reached the person who asked for
a diagram.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

_BLOCKING_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _BLOCKING_DIR.parent
for each_sys_path_entry in (str(_BLOCKING_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import artifact_look_gate

HOOK_SCRIPT = _BLOCKING_DIR / "artifact_look_gate.py"


def _tool_use(call_id: str, tool_name: str, file_path: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": tool_name,
                    "input": {"file_path": file_path},
                }
            ]
        },
    }


def _tool_result(call_id: str, is_error: bool = False) -> dict[str, object]:
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": "ok",
                    "is_error": is_error,
                }
            ]
        },
    }


def _run_hook(tmp_path: Path, all_records: list[dict[str, object]], page_path: Path) -> str:
    transcript_path = tmp_path / "transcript.jsonl"
    transcript_path.write_text(
        "".join(json.dumps(each_record) + "\n" for each_record in all_records), encoding="utf-8"
    )
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Artifact",
                "tool_input": {"file_path": str(page_path), "icon": "map"},
                "transcript_path": str(transcript_path),
            }
        ),
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def _file_at(file_path: Path, modified_time: float) -> Path:
    file_path.write_text("x", encoding="utf-8")
    os.utime(file_path, (modified_time, modified_time))
    return file_path


def _read_records(image_path: Path, is_error: bool = False) -> list[dict[str, object]]:
    return [_tool_use("r1", "Read", str(image_path)), _tool_result("r1", is_error)]


def test_should_refuse_a_page_published_without_a_look(tmp_path: Path) -> None:
    page_path = _file_at(tmp_path / "page.html", 1000)
    hook_output = json.loads(
        _run_hook(
            tmp_path, [_tool_use("w1", "Write", str(page_path)), _tool_result("w1")], page_path
        )
    )
    specific_output = hook_output["hookSpecificOutput"]
    assert specific_output["permissionDecision"] == "deny"
    assert "--screenshot" in specific_output["permissionDecisionReason"]


def test_should_allow_a_page_whose_newer_screenshot_was_read(tmp_path: Path) -> None:
    page_path = _file_at(tmp_path / "page.html", 1000)
    image_path = _file_at(tmp_path / "page.png", 1001)
    assert _run_hook(tmp_path, _read_records(image_path), page_path) == ""


def test_should_refuse_when_the_page_changed_after_the_screenshot(tmp_path: Path) -> None:
    image_path = _file_at(tmp_path / "page.png", 1000)
    page_path = _file_at(tmp_path / "page.html", 1001)
    assert "deny" in _run_hook(tmp_path, _read_records(image_path), page_path)


def test_should_refuse_when_the_screenshot_read_failed(tmp_path: Path) -> None:
    page_path = _file_at(tmp_path / "page.html", 1000)
    image_path = _file_at(tmp_path / "page.png", 1001)
    assert "deny" in _run_hook(tmp_path, _read_records(image_path, is_error=True), page_path)


def test_page_was_looked_at_ignores_reads_of_other_files(tmp_path: Path) -> None:
    page_path = _file_at(tmp_path / "page.html", 1000)
    notes_path = _file_at(tmp_path / "notes.md", 1001)
    all_lines = [json.dumps(each_record) for each_record in _read_records(notes_path)]
    assert not artifact_look_gate.page_was_looked_at(all_lines, str(page_path))


def test_unseen_page_reason_passes_non_publish_calls() -> None:
    assert (
        artifact_look_gate.unseen_page_reason(
            {"tool_name": "Artifact", "tool_input": {"action": "read", "url": "x"}}
        )
        is None
    )
    assert (
        artifact_look_gate.unseen_page_reason(
            {"tool_name": "Artifact", "tool_input": {"file_path": "image.png", "asset": True}}
        )
        is None
    )
