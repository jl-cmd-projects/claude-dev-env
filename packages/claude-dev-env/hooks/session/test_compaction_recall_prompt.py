"""Tests for compaction_recall_prompt and the hooks.json entries that carry its recall."""

import fnmatch
import json
import shlex
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
ALL_HOOK_REGISTRATIONS = json.loads((_HOOKS_ROOT / "hooks.json").read_text(encoding="utf-8"))[
    "hooks"
]


def compact_input(transcript_path: str) -> dict[str, object]:
    return {
        "hook_event_name": "SessionStart",
        "source": "compact",
        "transcript_path": transcript_path,
    }


def recall_command(transcript_path: str) -> str:
    context_text = recall.recall_context(compact_input(transcript_path))
    assert context_text is not None
    return next(line for line in context_text.splitlines() if "compaction_user_messages.py" in line)


def test_recall_context_should_name_a_command_that_writes_the_users_messages(
    tmp_path: Path,
) -> None:
    transcript_path = tmp_path / "it's a session.jsonl"
    transcript_path.write_text(
        json.dumps({"type": "user", "message": {"content": "keep port 8443"}}) + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        shlex.split(recall_command(str(transcript_path))),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "keep port 8443" in Path(completed.stdout.strip()).read_text(encoding="utf-8")


def test_recall_context_should_stay_quiet_outside_a_compaction() -> None:
    assert recall.recall_context({**compact_input("/t.jsonl"), "source": "startup"}) is None
    assert recall.recall_context({**compact_input("/t.jsonl"), "hook_event_name": "Stop"}) is None
    assert recall.recall_context({"hook_event_name": "SessionStart", "source": "compact"}) is None


def test_main_should_print_the_context_as_session_start_output() -> None:
    completed = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(compact_input("/t/abc.jsonl")),
        capture_output=True,
        text=True,
        check=True,
    )
    hook_output = json.loads(completed.stdout)["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "SessionStart"
    assert "compaction_user_messages.py" in hook_output["additionalContext"]


def test_hooks_json_should_run_the_recall_prompt_after_every_compaction() -> None:
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


def condensing_hooks() -> list[dict[str, object]]:
    return [
        each_hook
        for each_group in ALL_HOOK_REGISTRATIONS["PostToolUse"]
        if each_group.get("matcher") == "Bash"
        for each_hook in each_group["hooks"]
        if each_hook.get("type") == "agent"
    ]


def test_hooks_json_condensing_hook_should_match_the_command_the_recall_names() -> None:
    all_hooks = condensing_hooks()
    assert len(all_hooks) == 1
    if_rule = str(all_hooks[0]["if"])
    assert if_rule.startswith("Bash(") and if_rule.endswith(")")
    command_pattern = if_rule[len("Bash(") : -1]
    assert fnmatch.fnmatchcase(
        recall_command("/home/u/.claude/projects/p/s.jsonl"), command_pattern
    )
    spaced_home_command = shlex.join(
        [sys.executable, "/home/a b/.claude/hooks/session/compaction_user_messages.py", "/t.jsonl"]
    )
    assert fnmatch.fnmatchcase(spaced_home_command, command_pattern)
    assert not fnmatch.fnmatchcase("python3 other_script.py /t.jsonl", command_pattern)


def test_hooks_json_condensing_hook_should_always_return_its_text_as_the_block_reason() -> None:
    condensing_hook = condensing_hooks()[0]
    assert '"ok": false' in str(condensing_hook["prompt"])
    assert "$ARGUMENTS" in str(condensing_hook["prompt"])
    assert str(condensing_hook["statusMessage"]).startswith("claude-dev-env: ")
