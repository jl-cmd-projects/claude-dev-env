import json
import subprocess
import sys
from pathlib import Path

HOOK_SCRIPT = Path(__file__).resolve().parent / "subagent_effort_route_hook.py"


def _write_transcript(tmp_path: Path, parent_model: str) -> Path:
    transcript_path = tmp_path / "transcript.jsonl"
    all_entries = [
        {"type": "user", "message": {"role": "user", "content": "hi"}},
        {"type": "assistant", "message": {"model": "claude-fable-5-2", "content": []}},
        {"type": "assistant", "message": {"model": parent_model, "content": []}},
        {"type": "user", "message": {"role": "user", "content": "tool result"}},
    ]
    transcript_path.write_text(
        "\n".join(json.dumps(each_entry) for each_entry in all_entries) + "\nnot json\n",
        encoding="utf-8",
    )
    return transcript_path


def _run_hook(tool_input: object, transcript_path: Path | None = None) -> str:
    hook_payload: dict[str, object] = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_input": tool_input,
    }
    if transcript_path is not None:
        hook_payload["transcript_path"] = str(transcript_path)
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(hook_payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def _hook_specific_output(stdout: str) -> dict[str, object]:
    return json.loads(stdout)["hookSpecificOutput"]


def test_should_move_an_opus_spawn_at_xhigh_to_medium() -> None:
    spawn_input = {"subagent_type": "general-purpose", "model": "opus", "effort": "xhigh", "prompt": "Do X."}
    decision = _hook_specific_output(_run_hook(spawn_input))
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["updatedInput"] == {**spawn_input, "effort": "medium"}
    assert decision["additionalContext"] == (
        "Subagent model and effort rule: this opus spawn now runs at medium effort."
    )
    assert "permissionDecision" not in decision


def test_should_give_a_sonnet_spawn_with_no_effort_high() -> None:
    decision = _hook_specific_output(_run_hook({"model": "sonnet", "prompt": "Do X."}))
    assert decision["updatedInput"]["effort"] == "high"


def test_should_use_the_last_parent_model_when_the_spawn_names_none(tmp_path: Path) -> None:
    decision = _hook_specific_output(
        _run_hook({"subagent_type": "Explore", "prompt": "Find X."}, _write_transcript(tmp_path, "claude-opus-5-5"))
    )
    assert decision["updatedInput"] == {"subagent_type": "Explore", "prompt": "Find X.", "effort": "medium"}


def test_should_print_nothing_for_an_allowed_pair() -> None:
    assert _run_hook({"model": "haiku", "effort": "max", "prompt": "Do X."}) == ""


def test_should_print_nothing_for_a_fork(tmp_path: Path) -> None:
    assert _run_hook({"subagent_type": "fork", "prompt": "Do X."}, _write_transcript(tmp_path, "claude-opus-5-5")) == ""


def test_should_print_nothing_when_no_model_is_known(tmp_path: Path) -> None:
    assert _run_hook({"prompt": "Do X."}, tmp_path / "absent.jsonl") == ""


def test_should_print_nothing_for_stdin_that_is_not_an_object() -> None:
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)], input="[1, 2]", capture_output=True, text=True, check=True
    )
    assert completed.stdout == ""
