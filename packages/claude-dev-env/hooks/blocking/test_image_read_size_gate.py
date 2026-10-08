"""Behavior tests for the image read size gate."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

_BLOCKING_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _BLOCKING_DIR.parent
for each_sys_path_entry in (str(_BLOCKING_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import image_read_size_gate

HOOK_SCRIPT = _BLOCKING_DIR / "image_read_size_gate.py"


def _image(file_path: Path, width: int, height: int) -> Path:
    Image.new("RGB", (width, height), "white").save(file_path)
    return file_path


def _run_hook(file_path: Path) -> str:
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": str(file_path)},
            }
        ),
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def test_should_refuse_a_full_size_preview_read(tmp_path: Path) -> None:
    hook_output = json.loads(_run_hook(_image(tmp_path / "preview.png", 1440, 2560)))
    specific_output = hook_output["hookSpecificOutput"]
    assert specific_output["permissionDecision"] == "deny"
    assert "1440x2560" in specific_output["permissionDecisionReason"]
    assert "agent_image_copy.py" in specific_output["permissionDecisionReason"]


def test_should_allow_an_image_at_the_cap(tmp_path: Path) -> None:
    assert _run_hook(_image(tmp_path / "preview.agent.png", 288, 512)) == ""


def test_should_allow_a_text_file(tmp_path: Path) -> None:
    notes_path = tmp_path / "notes.md"
    notes_path.write_text("x" * 4000, encoding="utf-8")
    assert _run_hook(notes_path) == ""


def test_should_allow_a_missing_file(tmp_path: Path) -> None:
    assert _run_hook(tmp_path / "gone.png") == ""


@pytest.mark.parametrize("suffix", [".png", ".jpg", ".gif", ".webp"])
def test_image_size_reads_each_format(tmp_path: Path, suffix: str) -> None:
    image_path = _image(tmp_path / f"wide{suffix}", 900, 300)
    assert image_read_size_gate.image_size(image_path.read_bytes()[:65536]) == (900, 300)


def test_oversized_image_reason_passes_other_tools(tmp_path: Path) -> None:
    image_path = _image(tmp_path / "big.png", 2000, 2000)
    assert (
        image_read_size_gate.oversized_image_reason(
            {"tool_name": "Write", "tool_input": {"file_path": str(image_path)}}
        )
        is None
    )
