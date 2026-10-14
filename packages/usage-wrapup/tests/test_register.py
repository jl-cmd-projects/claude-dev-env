import json
import subprocess
from collections.abc import Callable


def test_lowest_returns_the_lowest_window_at_or_below_the_threshold(
    run_repository_command: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> None:
    script = (
        "import {lowest, wrapUpNote} from './packages/usage-wrapup/hooks/register.ts'; "
        "const limits = [{kind: 'five_hour', percentUsed: 96, resetsAt: '2026-10-05T03:10:00Z'}, "
        "{kind: 'seven_day', percentUsed: 99}]; "
        "const low = lowest(limits, 5); "
        "const above = lowest([{kind: 'five_hour', percentUsed: 94}], 5); "
        "console.log(JSON.stringify({low, note: wrapUpNote(low), "
        "atThreshold: lowest([{kind: 'five_hour', percentUsed: 95}], 5), "
        "aboveThreshold: above === undefined ? 'undefined' : above}));"
    )
    selection_run = run_repository_command(["bun", "-e", script])
    selection_report = json.loads(selection_run.stdout)

    assert selection_report["low"] == {
        "kind": "seven_day",
        "left": 1,
    }
    assert "weekly usage limit: only 1% left." in selection_report["note"]
    assert selection_report["atThreshold"] == {"kind": "five_hour", "left": 5}
    assert selection_report["aboveThreshold"] == "undefined"
