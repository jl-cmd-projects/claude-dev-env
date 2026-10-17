import json
import shutil
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_deepen_helpers_shape_the_gate_request_and_accept_marked_output() -> None:
    bun = shutil.which("bun")
    assert bun is not None
    script = """
import { deepenHookInput, deepenHookScriptPath, hasPriorUserMessage, rewrittenPromptFrom } from './packages/deepen-first-prompt/hooks/deepen.ts';
console.log(JSON.stringify({
  scriptPath: deepenHookScriptPath('/config', '/home'),
  fallbackPath: deepenHookScriptPath(undefined, '/home'),
  payload: JSON.parse(deepenHookInput('Write tests', 'session-1')),
  rewritten: rewrittenPromptFrom('  CDE_DEEPEN:v1 Write tests  '),
  unmarked: rewrittenPromptFrom('Write tests') ?? null,
  firstPrompt: hasPriorUserMessage([{ role: 'user', text: 'Write tests' }], 'Write tests'),
  laterPrompt: hasPriorUserMessage([{ role: 'user', text: 'Earlier' }], 'Write tests'),
}))
"""
    completed_run = subprocess.run(
        [bun, "-e", script.replace("\n", " ")],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed_run.returncode == 0, completed_run.stderr

    assert json.loads(completed_run.stdout) == {
        "scriptPath": "/config/hooks/session/deepen_first_prompt.py",
        "fallbackPath": "/home/.claude/hooks/session/deepen_first_prompt.py",
        "payload": {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Write tests",
            "session_id": "session-1",
        },
        "rewritten": "CDE_DEEPEN:v1 Write tests",
        "unmarked": None,
        "firstPrompt": False,
        "laterPrompt": True,
    }
