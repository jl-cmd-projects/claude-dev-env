import json
import shutil
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_first_prompt_uses_the_marked_gate_text_and_later_prompts_skip_it() -> None:
    bun = shutil.which("bun")
    assert bun is not None
    script = """
import { register } from './packages/deepen-first-prompt/hooks/index.ts';
let submit;
register((name, callback) => { if (name === 'prompt.submit') submit = callback });
const calls = [];
const session = {
  id: async () => 'session-1',
  messages: async () => [{ role: 'user', text: 'Write tests' }],
};
const host = {
  env: { get: async name => name === 'CLAUDE_CONFIG_DIR' ? '/config' : undefined },
  session,
  process: { run: async (command, options) => {
    calls.push({ command, options });
    return { exitCode: 0, stdout: 'CDE_DEEPEN:v1 Write tests and check edge cases' }
  } },
};
const next = event => event;
const rewritten = await submit(host, { text: 'Write tests' }, next);
session.messages = async () => [{ role: 'user', text: 'Earlier' }];
const skipped = await submit(host, { text: 'Another task' }, next);
console.log(JSON.stringify({ rewritten, skipped, calls }));
"""
    completed_run = subprocess.run(
        [bun, "-e", script.replace("\n", " ")],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed_run.returncode == 0, completed_run.stderr
    report = json.loads(completed_run.stdout)

    assert report["rewritten"] == {
        "text": "CDE_DEEPEN:v1 Write tests and check edge cases"
    }
    assert report["skipped"] == {"text": "Another task"}
    assert len(report["calls"]) == 1
    assert report["calls"][0]["command"] == [
        "python3",
        "/config/hooks/session/deepen_first_prompt.py",
    ]
    assert report["calls"][0]["options"]["env"] == {
        "CDE_DEEPEN_OUTPUT": "rewrite"
    }
    assert json.loads(report["calls"][0]["options"]["stdin"]) == {
        "hook_event_name": "UserPromptSubmit",
        "prompt": "Write tests",
        "session_id": "session-1",
    }
