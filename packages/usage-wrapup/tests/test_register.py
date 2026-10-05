import json
import os
import subprocess
from pathlib import Path


def test_lowest_selects_the_window_below_the_threshold() -> None:
    root = Path(__file__).resolve().parents[3]
    script = (
        "import {lowest, wrapUpNote} from './packages/usage-wrapup/hooks/register.ts'; "
        "const limits = [{kind: 'five_hour', percentUsed: 96, resetsAt: '2026-10-05T03:10:00Z'}, "
        "{kind: 'seven_day', percentUsed: 99}]; "
        "const low = lowest(limits, 5); "
        "console.log(JSON.stringify({low, note: wrapUpNote(low), "
        "aboveThreshold: lowest([{kind: 'five_hour', percentUsed: 94}], 5)}));"
    )
    result = subprocess.run(
        ["bun", "-e", script],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        shell=os.name == "nt",
    )
    output = json.loads(result.stdout)

    assert output["low"] == {
        "kind": "seven_day",
        "left": 1,
    }
    assert "weekly usage limit: only 1% left." in output["note"]
    assert "aboveThreshold" not in output
