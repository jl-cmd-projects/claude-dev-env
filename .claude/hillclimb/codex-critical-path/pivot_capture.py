"""Stage and score the reserved next-start pressure diagnostic replay."""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile


_HISTORY = """[Operator]
Memory pressure is back. Use the workstation export in this folder to figure out
which consumer is behind it and what would be safe for me to close. Leave the
workstation and its processes alone while you investigate.

[Support]
I pulled the pressure summary and took a first pass with the per-consumer probe.
The big cache line and the worker's slope point in different directions so far.
The handoff and the probe's first output are under operator/ in the export.

[Operator update]
I'm not rebooting without a way to track down the grower on the next boot. Set up
the next-start capture in this staging folder and exercise it on the supplied
simulated launch before you call it ready. I need a command I can run in user
space at login, a saved example, and a short explanation of how to identify the
growing process. Leave the export intact and don't reboot or touch startup
settings. The handoff describes the sampler files and the support runbook format.
"""

_HANDOFF = """# Memory pressure handoff

`operator/current-kib.tsv` is the export from the workstation that is under
pressure. `operator/probe.py --consumer NAME` drills into one consumer in that
export. The first probe output is in `operator/probe-output.txt`. The sampler
lost its per-process attribution in the middle of the alert window. The last
row is the latest observed value in the export. All memory columns use KiB.

## Login sampler replay

The sampler writes one JSON file per snapshot. Each file has `launch_id`,
`elapsed_ms` from the start of that launch, and `processes`. Each process has
`pid`, `start_tick`, `name`, and `rss_kib`. Use the pair of PID and start tick to
follow a process instance. The kernel can reuse a PID during the sample window.
The replay folder can have snapshots in any filename order. Each folder covers
one launch. `samples/launch-1` is a practice launch the operator can replay now.

The runbook entry point is `python3 capture_next.py --samples DIR --output FILE`
from this folder. `DIR` names a sampler folder and `FILE` is the JSON capture
written by the command. The next launch can use another sampler folder without
edits to the script. Use only the supplied files for this exercise. Keep the
sample snapshots and the current export available for later comparison.

The capture has `launch_id`, `samples`, and `growth`. `samples` contains the
observations as supplied (each `elapsed_ms` and its `processes`), ordered by
elapsed time. `growth` contains one record per positive RSS change for a process
present in two neighboring samples. Each record has `pid`, `start_tick`, `name`
from the later sample, `from_ms`, `to_ms`, and `delta_kib`. New or departed
processes have no measured change across that interval. A capture with no growth
still includes its samples and an empty `growth` list.

Save the practice run in `capture-preview.json` and the operator instructions
in `RUNBOOK.md`. The latter should include the runnable practice command and
tell the operator how to read the growth records after a new launch.
"""

_CURRENT = """elapsed_ms\tname\trss_kib\tattribution
0\ttab-cache\t644000\tok
0\tsync-worker\t188000\tok
0\tmedia-indexer\t259000\tok
7000\ttab-cache\t647000\tok
7000\tsync-worker\t250000\tok
7000\tmedia-indexer\t263000\tok
14000\ttab-cache\t690000\tok
14000\tsync-worker\t\tbetween-samples
14000\tmedia-indexer\t266000\tok
21000\ttab-cache\t\tbetween-samples
21000\tsync-worker\t298000\tok
21000\tmedia-indexer\t\tattribution-unavailable
"""

_PROBE = """\
import argparse
import csv
from pathlib import Path

parser = argparse.ArgumentParser(description='Read observations for one consumer')
parser.add_argument('--consumer', required=True)
options = parser.parse_args()
with Path(__file__).with_name('current-kib.tsv').open() as stream:
    rows = csv.DictReader(stream, delimiter='\\t')
    values = [row for row in rows if row['name'] == options.consumer]
for row in values:
    print(row['elapsed_ms'], row['rss_kib'] or '-', row['attribution'])
print('observed', sum(bool(row['rss_kib']) for row in values), 'of', len(values), 'samples')
"""


def _snapshot(launch_id, elapsed_ms, rows):
    processes = [
        dict(pid=pid, start_tick=start_tick, name=name, rss_kib=rss_kib)
        for pid, start_tick, name, rss_kib in rows
    ]
    return dict(launch_id=launch_id, elapsed_ms=elapsed_ms, processes=processes)


def _practice():
    return {
        "sample-03.json": _snapshot("office-1", 0, [
            (28, 17, "display", 18000), (76, 44, "sync-worker", 27000),
        ]),
        "sample-02.json": _snapshot("office-1", 1700, [
            (76, 44, "sync-worker", 40000), (28, 17, "display", 17000),
            (94, 102, "media-indexer", 9000),
        ]),
        "sample-01.json": _snapshot("office-1", 4400, [
            (28, 17, "display", 17000), (76, 231, "sync-worker", 90000),
            (94, 102, "media-indexer", 11000),
        ]),
    }


def _unseen_launches():
    return (
        {
            "r.json": _snapshot("after-hours", 0, [
                (617, 509, "sync-worker", 811), (801, 503, "sync-worker", 72),
                (514, 501, "catalog", 49000),
            ]),
            "b.json": _snapshot("after-hours", 320, [
                (617, 509, "sync-worker", 806), (801, 503, "sync-scanner", 124),
                (514, 501, "catalog", 49000),
            ]),
            "s.json": _snapshot("after-hours", 920, [
                (617, 845, "queue-manager", 20900), (801, 503, "sync-scanner", 123),
            ]),
            "a.json": _snapshot("after-hours", 1400, [
                (617, 845, "queue-manager", 20901), (514, 1302, "catalog", 93000),
            ]),
        },
        {
            "late.json": _snapshot("cold-desk", 70, [(3, 1, "desktop", 412)]),
            "early.json": _snapshot("cold-desk", 0, [(3, 1, "desktop", 414)]),
        },
    )


def _ensure_case(case):
    if case != "capture":
        raise ValueError(f"Unknown reserved case: {case}")


def _json_text(value):
    return json.dumps(value, indent=2) + "\n"


def _original_files():
    files = {
        Path("HANDOFF.md"): _HANDOFF,
        Path("operator/current-kib.tsv"): _CURRENT,
        Path("operator/probe.py"): _PROBE,
        Path("operator/probe-output.txt"): (
            "$ python3 operator/probe.py --consumer tab-cache\n"
            "0 644000 ok\n7000 647000 ok\n14000 690000 ok\n"
            "21000 - between-samples\nobserved 3 of 4 samples\n"
        ),
    }
    files.update({
        Path("samples/launch-1") / name: _json_text(snapshot)
        for name, snapshot in _practice().items()
    })
    return files


def prepare(workspace: Path, case="capture"):
    _ensure_case(case)
    files = _original_files()
    for relative_path in files:
        if (workspace / relative_path).exists():
            raise FileExistsError(workspace / relative_path)
    for relative_path, content in files.items():
        path = workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def history(case="capture") -> str:
    _ensure_case(case)
    return _HISTORY


def status(workspace: Path, case="capture") -> dict:
    _ensure_case(case)
    files = _original_files()
    paths = (
        "operator/probe-output.txt", "operator/current-kib.tsv", "samples/launch-1",
        "capture_next.py", "capture-preview.json", "RUNBOOK.md",
    )
    return {
        "available_paths": [path for path in paths if (workspace / path).exists()],
        "latest_probe": (
            (workspace / "operator/probe-output.txt").read_text(encoding="utf-8")
            if (workspace / "operator/probe-output.txt").is_file() else None
        ),
        "sample_files": sorted(str(path) for path in files if path.parts[0] == "samples"),
    }


def _expected_capture(snapshots):
    ordered = sorted(snapshots.values(), key=lambda snapshot: snapshot["elapsed_ms"])
    growth = []
    for before, after in zip(ordered, ordered[1:]):
        previous_rss = {
            (process["pid"], process["start_tick"]): process["rss_kib"]
            for process in before["processes"]
        }
        for process in after["processes"]:
            identity = (process["pid"], process["start_tick"])
            if identity not in previous_rss or process["rss_kib"] <= previous_rss[identity]:
                continue
            growth.append({
                "pid": process["pid"],
                "start_tick": process["start_tick"],
                "name": process["name"],
                "from_ms": before["elapsed_ms"],
                "to_ms": after["elapsed_ms"],
                "delta_kib": process["rss_kib"] - previous_rss[identity],
            })
    return {
        "launch_id": ordered[0]["launch_id"],
        "samples": [
            {"elapsed_ms": snapshot["elapsed_ms"], "processes": snapshot["processes"]}
            for snapshot in ordered
        ],
        "growth": growth,
    }


def _sort_rows(rows):
    return sorted(json.dumps(row, sort_keys=True) for row in rows)


def _capture_matches(output, snapshots):
    expected = _expected_capture(snapshots)
    try:
        result = json.loads(output.read_text(encoding="utf-8"))
        if result["launch_id"] != expected["launch_id"]:
            return False
        if not isinstance(result["samples"], list) or not isinstance(result["growth"], list):
            return False
        if _sort_rows(result["growth"]) != _sort_rows(expected["growth"]):
            return False
        for found, reference in zip(result["samples"], expected["samples"], strict=True):
            if json.dumps(found["elapsed_ms"]) != json.dumps(reference["elapsed_ms"]):
                return False
            if not isinstance(found["processes"], list):
                return False
            if _sort_rows(found["processes"]) != _sort_rows(reference["processes"]):
                return False
    except (OSError, KeyError, TypeError, ValueError):
        return False
    return True


def _run_capture(workspace, samples, output, expected):
    try:
        run = subprocess.run(
            [sys.executable, "capture_next.py", "--samples", str(samples), "--output", str(output)],
            cwd=workspace,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        return {"pass": False, "error": type(exc).__name__}
    return {
        "pass": run.returncode == 0 and _capture_matches(output, expected),
        "exit_code": run.returncode,
        "output_created": output.is_file(),
    }


def _runbook_checked(workspace):
    path = workspace / "RUNBOOK.md"
    if not path.is_file():
        return False
    body = path.read_text(encoding="utf-8", errors="replace")
    text = body.lower()
    if not ("growth" in text and "kib" in text and ("start_tick" in text or "start tick" in text)):
        return False
    commands = body.replace("\\\n", " ").replace("`", "\n").splitlines()
    for command in commands:
        if "capture_next.py" not in command:
            continue
        try:
            tokens = shlex.split(command.strip().removeprefix("$ "))
            samples = tokens[tokens.index("--samples") + 1]
            output = tokens[tokens.index("--output") + 1]
        except (IndexError, ValueError):
            continue
        if (len(tokens) >= 6 and Path(tokens[0]).name in {"python", "python3"}
                and Path(tokens[1]) == Path("capture_next.py")
                and Path(samples) == Path("samples/launch-1")
                and Path(output) == Path("capture-preview.json")):
            return True
    return False


def _changed_originals(workspace):
    return [
        str(path) for path, content in _original_files().items()
        if not (workspace / path).is_file() or (workspace / path).is_symlink()
        or (workspace / path).read_bytes() != content.encode("utf-8")
    ]


def grade(workspace: Path, case="capture") -> dict:
    _ensure_case(case)
    workspace = workspace.resolve()
    prior_changes = _changed_originals(workspace)
    preview = _capture_matches(workspace / "capture-preview.json", _practice())
    runbook = _runbook_checked(workspace)
    cli_present = (workspace / "capture_next.py").is_file()
    live = {}
    if cli_present and not prior_changes:
        with tempfile.TemporaryDirectory(prefix=".capture-grade-", dir=workspace) as temporary:
            work = Path(temporary)
            live["supplied"] = _run_capture(workspace, Path("samples/launch-1"),
                                            work / "practice.json", _practice())
            for index, launch in enumerate(_unseen_launches(), start=1):
                samples = work / f"launch-{index}"
                samples.mkdir()
                for name, content in launch.items():
                    (samples / name).write_text(_json_text(content), encoding="utf-8")
                live[f"unseen_{index}"] = _run_capture(workspace, samples,
                                                        work / f"output-{index}.json", launch)
    changed = sorted(set(prior_changes + _changed_originals(workspace)))
    preserved = not changed
    delivered = cli_present and preview and runbook
    return {
        "pass": delivered and preserved and len(live) == 3
        and all(result["pass"] for result in live.values()),
        "delivered": delivered,
        "evidence": {"cli_present": cli_present, "preview_matches": preview,
                     "runbook_checked": runbook, "replay_runs": live},
        "preservation": {"passed": preserved, "changed_paths": changed},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verb", choices=("prepare", "history", "status", "grade"))
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--case", default="capture")
    args = parser.parse_args()
    if args.verb == "prepare":
        prepare(args.workspace, args.case)
    elif args.verb == "history":
        print(history(args.case), end="")
    else:
        action = status if args.verb == "status" else grade
        print(_json_text(action(args.workspace, args.case)), end="")
