import json
import subprocess
from collections.abc import Callable


def test_window_to_compact_skips_a_window_with_no_finite_reading(
    run_repository_command: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> None:
    script = (
        "import {windowToCompact} from './packages/usage-wrapup/hooks/compact.ts'; "
        "const thresholds = {five_hour: 97, seven_day: 99}; "
        "const unreadable = windowToCompact("
        "[{kind: 'five_hour', percentUsed: NaN, resetsAt: 'A'}], thresholds, {}); "
        "const missing = windowToCompact("
        "[{kind: 'five_hour', resetsAt: 'B'}], thresholds, {}); "
        "console.log(JSON.stringify({"
        "unreadable: unreadable === undefined ? 'undefined' : unreadable, "
        "missing: missing === undefined ? 'undefined' : missing, "
        "readable: windowToCompact([{kind: 'five_hour', percentUsed: NaN, resetsAt: 'A'}, "
        "{kind: 'seven_day', percentUsed: 99, resetsAt: 'C'}], thresholds, {})}));"
    )
    compact_run = run_repository_command(["bun", "-e", script])
    compact_report = json.loads(compact_run.stdout)

    assert compact_report["unreadable"] == "undefined"
    assert compact_report["missing"] == "undefined"
    assert compact_report["readable"] == {"kind": "seven_day", "resetsAt": "C"}
