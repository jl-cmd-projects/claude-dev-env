import json
import os
import subprocess
from pathlib import Path


def test_entry_point_registers_both_hook_groups() -> None:
    root = Path(__file__).resolve().parents[3]
    script = (
        "import {register} from './packages/usage-wrapup/hooks/index.ts'; "
        "const events = []; "
        "register((event) => events.push(event), {}); "
        "console.log(JSON.stringify(events));"
    )
    result = subprocess.run(
        ["bun", "-e", script],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        shell=os.name == "nt",
    )

    assert json.loads(result.stdout) == ["session.measure", "tool.call", "turn.complete"]
