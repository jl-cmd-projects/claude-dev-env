"""Tests for compaction_recall_prompt and the hooks.json entry that runs it."""

import json
import subprocess
import sys
from pathlib import Path

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import compaction_recall_prompt as recall

HOOK_PATH = _SESSION_DIR / "compaction_recall_prompt.py"
FIXTURE_DIRECTORY = _SESSION_DIR / "fixtures" / "compaction_user_messages"
ALL_HOOK_REGISTRATIONS = json.loads((_HOOKS_ROOT / "hooks.json").read_text(encoding="utf-8"))[
    "hooks"
]


def compact_input(transcript_path: str) -> dict[str, object]:
    return {
        "hook_event_name": "SessionStart",
        "source": "compact",
        "transcript_path": transcript_path,
    }


def test_recall_context_should_return_the_trimmed_messages_of_the_transcript() -> None:
    context_text = recall.recall_context(
        compact_input(str(FIXTURE_DIRECTORY / "deploy_session.jsonl"))
    )
    assert context_text is not None
    assert context_text.startswith("The context was just compacted")
    assert "batch-07.internal" in context_text
    assert "https://github.com/acme/billing/pull/812" in context_text
    assert "(overruled by #6)" in context_text


def test_recall_context_should_read_a_codex_rollout() -> None:
    context_text = recall.recall_context(
        compact_input(str(FIXTURE_DIRECTORY / "codex_rollout.jsonl"))
    )
    assert context_text is not None
    assert "#1 " in context_text
    assert "environment_context" not in context_text


def test_recall_context_should_stay_quiet_outside_a_compaction(tmp_path: Path) -> None:
    transcript_path = str(FIXTURE_DIRECTORY / "deploy_session.jsonl")
    assert recall.recall_context({**compact_input(transcript_path), "source": "startup"}) is None
    assert recall.recall_context({**compact_input(transcript_path), "hook_event_name": "Stop"}) is None
    assert recall.recall_context({"hook_event_name": "SessionStart", "source": "compact"}) is None
    assert recall.recall_context(compact_input(str(tmp_path / "absent.jsonl"))) is None


def test_recall_context_should_stay_quiet_when_no_message_was_typed(tmp_path: Path) -> None:
    transcript_path = tmp_path / "s.jsonl"
    transcript_path.write_text(
        json.dumps({"type": "user", "message": {"content": "skill"}, "isMeta": True}) + "\n",
        encoding="utf-8",
    )
    assert recall.recall_context(compact_input(str(transcript_path))) is None


def test_main_should_print_the_trimmed_messages_as_session_start_output(tmp_path: Path) -> None:
    transcript_path = tmp_path / "it's a session.jsonl"
    transcript_path.write_text(
        json.dumps({"type": "user", "message": {"content": "Please keep the port 8443"}}) + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(compact_input(str(transcript_path))),
        capture_output=True,
        text=True,
        check=True,
    )
    hook_output = json.loads(completed.stdout)["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "SessionStart"
    assert hook_output["additionalContext"].endswith("\n\n#1 keep port 8443")


def test_hooks_json_should_run_the_recall_hook_after_every_compaction() -> None:
    all_compact_commands = [
        each_hook.get("command", "")
        for each_group in ALL_HOOK_REGISTRATIONS["SessionStart"]
        if each_group.get("matcher") == "compact"
        for each_hook in each_group["hooks"]
    ]
    assert any(
        each_command.endswith("/hooks/session/compaction_recall_prompt.py")
        for each_command in all_compact_commands
    )


def test_hooks_json_should_register_no_model_hook_for_the_recall() -> None:
    all_hooks_json_text = json.dumps(ALL_HOOK_REGISTRATIONS)
    assert "compaction_user_messages.py" not in all_hooks_json_text
    assert all(
        each_hook.get("type") == "command"
        for each_group in ALL_HOOK_REGISTRATIONS["PostToolUse"]
        for each_hook in each_group["hooks"]
        if "compaction" in json.dumps(each_hook)
    )
