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
        "atThresholdWithFloatExcess: lowest([{kind: 'five_hour', percentUsed: 99.1}], 0.9), "
        "atThresholdWithFloatShortfall: lowest([{kind: 'five_hour', percentUsed: 98.9}], 1.1), "
        "unreadableWindowSkipped: lowest([{kind: 'five_hour', percentUsed: NaN}, "
        "{kind: 'seven_day', percentUsed: 99}], 5), "
        "unreadableThreshold: String(lowest([{kind: 'five_hour', percentUsed: 40}], NaN))}));"
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
    assert selection_report["atThresholdWithFloatExcess"] == {"kind": "five_hour", "left": 0.9}
    assert selection_report["atThresholdWithFloatShortfall"] == {"kind": "five_hour", "left": 1.1}
    assert selection_report["unreadableWindowSkipped"] == {"kind": "seven_day", "left": 1}
    assert selection_report["unreadableThreshold"] == "undefined"


def test_tool_call_skips_usage_after_a_failed_read_until_the_next_measurement(
    run_repository_command: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> None:
    script = (
        "import {register} from './packages/usage-wrapup/hooks/register.ts'; "
        "const handlers = {}; "
        "register((name, handler) => { handlers[name] = handler; }, {threshold: 5}); "
        "Date.now = () => 0; "
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


def test_tool_call_reads_usage_again_after_the_retry_cooldown(
    run_repository_command: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> None:
    script = (
        "import {register} from './packages/usage-wrapup/hooks/register.ts'; "
        "const handlers = {}; "
        "register((name, handler) => { handlers[name] = handler; }, {threshold: 5}); "
        "let now = 0; "
        "Date.now = () => now; "
        "let usageReads = 0; "
        "const $ = {session: {usage: async () => { usageReads += 1; "
        "if (usageReads === 1) throw new Error('usage read failed'); "
        "return {rateLimits: [{kind: 'five_hour', percentUsed: 99}]}; }}}; "
        "const next = async () => ({result: 'ok'}); "
        "const first = await handlers['tool.call']($, undefined, next); "
        "now = 1000; "
        "const withinCooldown = await handlers['tool.call']($, undefined, next); "
        "const readsWithinCooldown = usageReads; "
        "now = 61000; "
        "const afterCooldown = await handlers['tool.call']($, undefined, next); "
        "console.log(JSON.stringify({first, withinCooldown, readsWithinCooldown, "
        "afterCooldown, usageReads}));"
    )
    cooldown_run = run_repository_command(["bun", "-e", script])
    cooldown_report = json.loads(cooldown_run.stdout)

    assert cooldown_report["first"] == {"result": "ok"}
    assert cooldown_report["withinCooldown"] == {"result": "ok"}
    assert cooldown_report["readsWithinCooldown"] == 1
    assert cooldown_report["usageReads"] == 2
    assert "5-hour usage limit: only 1% left." in "\n".join(
        cooldown_report["afterCooldown"]["context"]
    )


def test_tool_call_reads_usage_again_when_the_clock_moves_back(
    run_repository_command: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> None:
    script = (
        "import {register} from './packages/usage-wrapup/hooks/register.ts'; "
        "const handlers = {}; "
        "register((name, handler) => { handlers[name] = handler; }, {threshold: 5}); "
        "let now = 3600000; "
        "Date.now = () => now; "
        "let usageReads = 0; "
        "const $ = {session: {usage: async () => { usageReads += 1; "
        "if (usageReads === 1) throw new Error('usage read failed'); "
        "return {rateLimits: [{kind: 'five_hour', percentUsed: 99}]}; }}}; "
        "const next = async () => ({result: 'ok'}); "
        "await handlers['tool.call']($, undefined, next); "
        "now = 0; "
        "const afterClockStep = await handlers['tool.call']($, undefined, next); "
        "console.log(JSON.stringify({afterClockStep, usageReads}));"
    )
    clock_run = run_repository_command(["bun", "-e", script])
    clock_report = json.loads(clock_run.stdout)

    assert clock_report["usageReads"] == 2
    assert "5-hour usage limit: only 1% left." in "\n".join(
        clock_report["afterClockStep"]["context"]
    )


def test_concurrent_tool_calls_share_one_usage_read(
    run_repository_command: Callable[[list[str]], subprocess.CompletedProcess[str]],
) -> None:
    script = (
        "import {register} from './packages/usage-wrapup/hooks/register.ts'; "
        "const handlers = {}; "
        "register((name, handler) => { handlers[name] = handler; }, {threshold: 5}); "
        "let usageReads = 0; "
        "const $ = {session: {usage: async () => { usageReads += 1; "
        "await new Promise((resolve) => setTimeout(resolve, 10)); "
        "return {rateLimits: [{kind: 'five_hour', percentUsed: 99}]}; }}}; "
        "const next = async () => ({result: 'ok'}); "
        "const results = await Promise.all([1, 2, 3].map(() => "
        "handlers['tool.call']($, undefined, next))); "
        "console.log(JSON.stringify({results, usageReads}));"
    )
    concurrency_run = run_repository_command(["bun", "-e", script])
    concurrency_report = json.loads(concurrency_run.stdout)

    assert concurrency_report["usageReads"] == 1
    for each_result in concurrency_report["results"]:
        assert "5-hour usage limit: only 1% left." in "\n".join(each_result["context"])
