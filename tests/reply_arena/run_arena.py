#!/usr/bin/env python3
"""Run every chat reply contender on every arena prompt with headless ``claude -p``.

Usage::

    python3 run_arena.py --out /path/to/runs --model opus --parallel 4 [--contenders A,B] [--prompts venv,cap]

Each run gets a fresh session id, an empty CLAUDE_CONFIG_DIR, no setting
sources, and a work folder that holds only copies of the two gate files.
The run folder keeps the stream-json transcript, the display log the
hooks write, the helper log, and the wall time.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

arena_directory = Path(__file__).resolve().parent
package_directory = arena_directory.parents[1] / "packages" / "claude-dev-env"
blocking_directory = package_directory / "hooks" / "blocking"
hooks_script = arena_directory / "contenders" / "arena_hooks.py"
gate_script = blocking_directory / "chat_reply_gate.py"
RUN_TIMEOUT_SECONDS = 600
MAXIMUM_AGENT_TURNS = 20
DISPLAY_TIMEOUT_SECONDS = 90
STOP_TIMEOUT_SECONDS = 90
PROMPT_HOOK_MODELS = {
    "haiku": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
}
REMOVED_ENVIRONMENT_KEYS = (
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_REMOTE_SESSION_ID",
)
PROMPT_STOP_HOOK_TEXT = (
    "You check a chat reply against these rules. At most 3 sentences, each at most 15 words;"
    " each line and each list item counts as one sentence. No colon in the middle of a sentence. No em dash."
    " Pull request numbers only inside a markdown link. A sentence with so, because, caused, due to,"
    " therefore, or means must hold inline code, a URL, or a link. None of these words: real, really,"
    " genuine, actual, actually, likely, probably, seems, maybe, perhaps, may be, might be."
    " Hook input: $ARGUMENTS. Check last_assistant_message. When stop_hook_active is true, or the reply"
    ' obeys every rule, return {"ok": true}. Otherwise return {"ok": false, "reason":'
    ' "Send this rewrite as your whole reply, word for word: <a rewrite that keeps the outcome and obeys every rule>"}.'
)


def command_hook(
    command_text: str, timeout_seconds: int | None = None
) -> dict[str, object]:
    """Return one command hook entry."""
    hook_entry: dict[str, object] = {"type": "command", "command": command_text}
    if timeout_seconds is not None:
        hook_entry["timeout"] = timeout_seconds
    return hook_entry


def arena_hook(role: str, timeout_seconds: int | None = None) -> dict[str, object]:
    """Return the command hook entry for one arena_hooks.py role."""
    return command_hook(f"python3 {hooks_script} {role}", timeout_seconds)


def event(*all_hooks: dict[str, object]) -> list[dict[str, object]]:
    """Wrap hook entries in the event list shape settings expect."""
    return [{"hooks": list(all_hooks)}]


def contender_settings() -> dict[str, dict[str, object]]:
    """Return the settings document for each contender."""
    baseline_gate = command_hook(f"python3 {gate_script}")
    display_log = event(arena_hook("display-log"))
    display_gate = event(arena_hook("display-gate", DISPLAY_TIMEOUT_SECONDS))
    return {
        "D": {
            "UserPromptSubmit": event(arena_hook("strong-reminder")),
            "MessageDisplay": display_log,
        },
        "E": {
            "UserPromptSubmit": event(arena_hook("seen-reminder")),
            "MessageDisplay": display_gate,
        },
        "F": {
            "UserPromptSubmit": event(arena_hook("strong-reminder")),
            "MessageDisplay": display_gate,
        },
        "F-shipped": {
            "UserPromptSubmit": event(baseline_gate),
            "MessageDisplay": event(command_hook(f"python3 {gate_script}", DISPLAY_TIMEOUT_SECONDS + 10)),
        },
        "F-sonnet": {
            "UserPromptSubmit": event(arena_hook("strong-reminder")),
            "MessageDisplay": event(
                command_hook(
                    f"CHAT_REPLY_DRAFTER_MODEL=sonnet python3 {hooks_script} display-gate",
                    DISPLAY_TIMEOUT_SECONDS,
                )
            ),
        },
        **{
            f"G-{each_model_alias}": {
                "UserPromptSubmit": event(baseline_gate),
                "Stop": event(
                    {
                        "type": "prompt",
                        "prompt": PROMPT_STOP_HOOK_TEXT,
                        "model": each_model_id,
                        "timeout": STOP_TIMEOUT_SECONDS,
                    }
                ),
                "MessageDisplay": display_log,
            }
            for each_model_alias, each_model_id in PROMPT_HOOK_MODELS.items()
        },
    }


def run_one(
    contender: str, prompt_record: dict[str, str], output_root: Path, model_name: str
) -> None:
    """Run one contender on one prompt and save its transcript and logs."""
    run_directory = output_root / contender / prompt_record["id"]
    if (run_directory / "meta.json").exists():
        return
    run_directory.mkdir(parents=True, exist_ok=True)
    work_directory = run_directory / "work"
    config_directory = run_directory / "config"
    work_directory.mkdir(exist_ok=True)
    config_directory.mkdir(exist_ok=True)
    for each_name in ("chat_reply_gate.py", "reply_length_gate.py"):
        shutil.copy(blocking_directory / each_name, work_directory / each_name)
    settings_path = run_directory / "settings.json"
    settings_path.write_text(
        json.dumps({"hooks": contender_settings()[contender]}), encoding="utf-8"
    )
    session_id = str(uuid.uuid4())
    environment = {
        each_key: each_value
        for each_key, each_value in os.environ.items()
        if each_key not in REMOVED_ENVIRONMENT_KEYS
    }
    environment["CLAUDE_CONFIG_DIR"] = str(config_directory)
    environment["ARENA_RUN_DIR"] = str(run_directory)
    command = [
        "claude",
        "-p",
        prompt_record["prompt"],
        "--model",
        model_name,
        "--setting-sources",
        "",
        "--settings",
        str(settings_path),
        "--session-id",
        session_id,
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-hook-events",
        "--max-turns",
        str(MAXIMUM_AGENT_TURNS),
        "--tools",
        "Read,Grep,Glob",
    ]
    started_at = time.monotonic()
    with open(run_directory / "stream.jsonl", "w", encoding="utf-8") as stream_file:
        try:
            subprocess.run(
                command,
                cwd=work_directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stream_file,
                stderr=subprocess.STDOUT,
                timeout=RUN_TIMEOUT_SECONDS,
                check=False,
            )
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
    meta = {
        "contender": contender,
        "prompt_id": prompt_record["id"],
        "session_id": session_id,
        "model": model_name,
        "seconds": round(time.monotonic() - started_at, 2),
        "timed_out": timed_out,
    }
    (run_directory / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    print(json.dumps(meta), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--model", default="opus")
    parser.add_argument("--parallel", default=4, type=int)
    parser.add_argument("--contenders", default=",".join(contender_settings()))
    parser.add_argument("--prompts", default="")
    arguments = parser.parse_args()
    all_prompts = json.loads(
        (arena_directory / "prompts.json").read_text(encoding="utf-8")
    )
    if arguments.prompts:
        chosen_ids = set(arguments.prompts.split(","))
        all_prompts = [
            each_prompt
            for each_prompt in all_prompts
            if each_prompt["id"] in chosen_ids
        ]
    all_jobs = [
        (each_contender, each_prompt)
        for each_prompt in all_prompts
        for each_contender in arguments.contenders.split(",")
    ]
    with ThreadPoolExecutor(max_workers=arguments.parallel) as executor:
        for each_future in [
            executor.submit(
                run_one, each_contender, each_prompt, arguments.out, arguments.model
            )
            for each_contender, each_prompt in all_jobs
        ]:
            each_future.result()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
