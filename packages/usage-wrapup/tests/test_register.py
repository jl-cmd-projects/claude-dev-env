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
        "const justAbove = lowest([{kind: 'five_hour', percentUsed: 94.96}], 5); "
        "const empty = lowest([], 5); "
        "console.log(JSON.stringify({low, note: wrapUpNote(low), "
        "atThreshold: lowest([{kind: 'five_hour', percentUsed: 95}], 5), "
        "aboveThreshold: above === undefined ? 'undefined' : above, "
        "justAboveThreshold: justAbove === undefined ? 'undefined' : justAbove, "
        "empty: empty === undefined ? 'undefined' : empty, "
        "overspent: lowest([{kind: 'five_hour', percentUsed: 101}], 5), "
        "fractionalAtThreshold: lowest([{kind: 'five_hour', percentUsed: 99.1}], 0.9), "
        "fractionalBelowThreshold: lowest([{kind: 'five_hour', percentUsed: 98.9}], 1.1)}));"
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
    assert selection_report["justAboveThreshold"] == "undefined"
    assert selection_report["empty"] == "undefined"
    assert selection_report["overspent"] == {"kind": "five_hour", "left": 0}
    assert selection_report["fractionalAtThreshold"] == {"kind": "five_hour", "left": 0.9}
    assert selection_report["fractionalBelowThreshold"] == {"kind": "five_hour", "left": 1.1}


def test_tool_call_skips_usage_after_a_failed_read_until_the_next_measurement(
    run_repository_command: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> None:
    script = (
        "import {register} from './packages/usage-wrapup/hooks/register.ts'; "
        "const handlers = {}; "
        "register((name, handler) => { handlers[name] = handler; }, {threshold: 5}); "
        "let usageReads = 0; "
        "const $ = {ui: {status: () => {}, toast: () => {}}, "
        "session: {usage: async () => { usageReads += 1; "
        "throw new Error('usage read failed'); }}}; "
        "const next = async (event) => (event ?? {result: 'ok'}); "
        "const first = await handlers['tool.call']($, undefined, next); "
        "const second = await handlers['tool.call']($, undefined, next); "
        "await handlers['session.measure']($, "
        "{rateLimits: [{kind: 'five_hour', percentUsed: 99}]}, next); "
        "const third = await handlers['tool.call']($, undefined, next); "
        "console.log(JSON.stringify({first, second, third, usageReads}));"
    )
    measurement_run = run_repository_command(["bun", "-e", script])
    measurement_report = json.loads(measurement_run.stdout)

    assert measurement_report["first"] == {"result": "ok"}
    assert measurement_report["second"] == {"result": "ok"}
    assert measurement_report["usageReads"] == 1
    assert "5-hour usage limit: only 1% left." in "\n".join(
        measurement_report["third"]["context"]
    )
