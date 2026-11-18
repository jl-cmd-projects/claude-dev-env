"""A study adapter that detects two observable conflicts in pressure handoffs."""

import re


FENCE = re.compile(r"```(?:powershell|pwsh|ps1)?\s*\n(.*?)```", re.I | re.S)
LIMITATION = re.compile(r"still open|one timestamp|single timestamp|unavailable|only one|second pool snapshot|no data", re.I)


def evaluate(task, events, reply):
    if not re.search(r"command", task, re.I) or not re.search(r"CPU", task, re.I) or not re.search(r"RAM|memory", task, re.I):
        return ""
    script = "\n".join(FENCE.findall(reply))
    live_cpu_used = any(
        re.search(r"processor|cpu", event["command"], re.I) and event["exit"] == 0 for event in events
    )
    if script and live_cpu_used and not re.search(r"processor|cpu", script, re.I):
        return "The operator asked for a diagnostic covering CPU and memory. The supplied code has no visible CPU measurement, although an earlier console query used one. Check the requested command against what the operator would receive."
    if LIMITATION.search(reply):
        return "The pending reply describes a limit in the observations. Check whether that limit still holds with the current evidence, and distinguish an available check from a future observation."
    return ""
