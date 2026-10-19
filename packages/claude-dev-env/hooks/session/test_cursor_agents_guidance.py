import json
import sys
from pathlib import Path

SESSION_DIRECTORY = Path(__file__).resolve().parent
if str(SESSION_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SESSION_DIRECTORY))

import cursor_agents_guidance


def test_should_emit_the_guidance_file_as_cursor_additional_context(tmp_path: Path) -> None:
    guidance_path = tmp_path / "AGENTS.md"
    guidance_path.write_text("# Agent guidance\n- **Asks.** Work every ask now.\n", encoding="utf-8")
    printed_output = cursor_agents_guidance.guidance_output(["hook", str(guidance_path)])
    assert json.loads(printed_output) == {"additional_context": guidance_path.read_text(encoding="utf-8")}


def test_should_emit_an_empty_object_when_the_file_is_missing(tmp_path: Path) -> None:
    assert cursor_agents_guidance.guidance_output(["hook", str(tmp_path / "absent.md")]) == "{}"


def test_should_emit_an_empty_object_without_a_path_argument() -> None:
    assert cursor_agents_guidance.guidance_output(["hook"]) == "{}"
