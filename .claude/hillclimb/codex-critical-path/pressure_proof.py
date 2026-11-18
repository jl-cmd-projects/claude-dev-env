"""Export masked workstation replay evidence and verify the archived first-pass grades."""

import argparse
import csv
import io
import json
import re
import secrets
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

import pressure_run
from proof import directory_name, json_digest, read_json
from trial import HERE, digest, write_json


SCHEMA = 1
SCHEDULE = HERE / "pressure_schedule.json"
PROMPT = HERE / "pressure_prompt.txt"
INTERVENTION = HERE / "pressure_intervention.txt"
SCHEDULE_SHA256 = "c3cb5aa925b737ffb7794177c0210dc861c066432e1eac385ead89431d51ecca"
LAUNCHES = "pressure_launches.json"
MANIFEST = "pressure_blind_manifest.json"
GRADES = "pressure_grades.json"
RESCUES = "pressure_rescues.json"
RESCUE_MANIFEST = "pressure_rescue_blind_manifest.json"
RESCUE_GRADES = "pressure_rescue_grades.json"
NUDGE = "Keep going. Closing one service improved the reading, but I still need the verdict I asked for."
OPAQUE = re.compile(r"blind-[0-9a-f]{24}")
HOST_PATH = re.compile(r"(?<![\w.])/(?:tmp|workspace|var/tmp)/[^\s\"'`<>:;,|&()\[\]{}\\]+")
ARM_LABEL = re.compile(r"\b(?:candidate|baseline|control|treatment) (?:arm|instructions|trial)\b", re.I)
MODEL_LABEL = re.compile(r"\b(?:gpt-6\.[12]-sol|gpt-6\.[12] sol)\b", re.I)
ACTION_FIELDS = ("action", "shell", "command", "start_elapsed_seconds", "command_elapsed_seconds",
                 "seconds", "exit", "stdout", "stderr", "timed_out")
BOOL_FIELDS = ("delivery", "usable_command", "limits", "sustained_detour", "missed_dependency",
               "false_done", "unassisted_incomplete", "nudge_needed")
ACTION_LISTS = ("side_actions", "mixed_actions", "repeated_no_progress_actions")
MEMORY_FIELDS = {
    "available mbytes": "AvailableMBytes", "available bytes": "AvailableBytes",
    "committed bytes": "CommittedBytes", "commit limit": "CommitLimit",
    "pool paged bytes": "PoolPagedBytes", "pool nonpaged bytes": "PoolNonpagedBytes",
    "pages/sec": "PagesPersec", "pages input/sec": "PagesInputPersec",
    "pages output/sec": "PagesOutputPersec", "page faults/sec": "PageFaultsPersec",
    "% committed bytes in use": "PercentCommittedBytesInUse",
}
PARSE_SCRIPT = r'''
$tokens = $null
$issues = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput(
    [Console]::In.ReadToEnd(), [ref]$tokens, [ref]$issues)
$commands = @($ast.FindAll({param($node) $node -is [System.Management.Automation.Language.CommandAst]}, $true))
$names = @($commands |
    ForEach-Object { $_.GetCommandName() })
@{errors=@($issues | ForEach-Object { $_.Message }); names=$names; command_count=$commands.Count} | ConvertTo-Json -Compress
'''
STATE_CHANGE = re.compile(r"^(?:.*\\)?(?:Stop-Process|Stop-Service|Restart-Service|Restart-Computer|"
                          r"Clear-EventLog|Remove-Item|Set-Service|taskkill(?:\.exe)?|shutdown(?:\.exe)?)$", re.I)


def text_file(path):
    return path.read_text(encoding="utf-8")


def checked_schedule():
    if digest(SCHEDULE.read_bytes()) != SCHEDULE_SHA256:
        raise ValueError("The trial schedule differs from the frozen order.")
    schedule = read_json(SCHEDULE)
    rows, groups = schedule["rows"], defaultdict(list)
    for row in rows:
        groups[row["pair"]].append(row)
    if (schedule["budget_seconds"] != pressure_run.BUDGET_SECONDS or len(rows) != 12
            or len({row["id"] for row in rows}) != 12 or len(groups) != 6):
        raise ValueError("The trial schedule has incomplete allocation.")
    for pair in groups.values():
        if ({row["arm"] for row in pair} != {"baseline", "candidate"}
                or len({tuple(row[field] for field in ("model", "reasoning_effort", "case", "rep"))
                        for row in pair}) != 1):
            raise ValueError("A matched allocation has different inputs.")
    return rows


def validate_launch(row, launch):
    if any(launch[key] != row[key] for key in ("model", "reasoning_effort")):
        raise ValueError("The archived launch disagrees with its allocation.")
    receipt = launch["receipt"]
    if launch["status"] not in ("opened", "failed") or not isinstance(receipt, dict) or not receipt:
        raise ValueError("A trial is missing a launch receipt or failure receipt.")
    if launch["status"] == "opened":
        task = receipt.get("task_name")
        if not launch.get("session_id") or task != "/root/" + row["id"]:
            raise ValueError("An opened launch lacks its scheduled worker receipt.")
    for field in ("model", "reasoning_effort", "session_id"):
        if field in receipt and receipt[field] != launch.get(field):
            raise ValueError(f"A launch receipt disagrees on {field}.")


def operation_groups(directory, record):
    raw = io.BytesIO((directory / pressure_run.RECEIPTS).read_bytes())
    fixture = pressure_run.fixture()
    groups = []
    for event in record["events"]:
        lines = raw.read(event["receipts"]["bytes"] - raw.tell()).splitlines()
        seconds = event["start_elapsed_seconds"]
        latest = fixture.samples(record["manifest"]["case"], seconds)[-1]["timestamp"]
        if not lines:
            if event.get("execution_error") and event["exit"] == 125:
                groups.append({"timestamp": latest, "operations": []})
                continue
            raise ValueError("A recorded command is missing its execution receipt.")
        command, *operations = map(json.loads, lines)
        if (command["operation"] != "command" or command["timestamp"] != latest
                or command["elapsed_seconds"] != seconds
                or not 0 <= command["duration_seconds"] <= event["seconds"]
                or any(command[key] != event[key] for key in ("shell", "command", "exit", "timed_out"))
                or any(op["operation"] == "command" or op["timestamp"] != latest for op in operations)):
            raise ValueError("A command and its execution receipts disagree.")
        groups.append({"timestamp": command["timestamp"], "operations": operations})
    if raw.read(1):
        raise ValueError("Some receipts have no recorded command.")
    return groups


def study(root):
    rows, launches = checked_schedule(), read_json(root / LAUNCHES)
    if set(launches) != {row["id"] for row in rows}:
        raise ValueError("Launch receipts do not cover the frozen order.")
    sessions, pair_inputs, runs = set(), {}, {}
    for row in rows:
        key = row["id"]
        launch, directory = launches[key], root / key
        validate_launch(row, launch)
        opened = launch["status"] == "opened"
        if opened:
            session = launch["session_id"]
            if session in sessions:
                raise ValueError("Two first-pass trials share one worker session.")
            sessions.add(session)
        recorded = (directory / "started.json").is_file()
        if recorded and not opened:
            raise ValueError("A failed launch has recorded worker actions.")
        run = {"row": row, "launch": launch, "directory": directory, "record": None, "operations": []}
        if recorded:
            record = pressure_run.replay(directory)
            manifest = record["manifest"]
            if ("recovery" in manifest or any(manifest[field] != row[field] for field in ("case", "arm"))
                    or (directory / "task.txt").read_bytes() != PROMPT.read_bytes()
                    or (row["arm"] == "candidate" and (directory / "intervention.txt").read_bytes()
                        != INTERVENTION.read_bytes().strip())):
                raise ValueError("The archived first-pass trial has different inputs.")
            if pair_inputs.setdefault(row["pair"], manifest["match_key"]) != manifest["match_key"]:
                raise ValueError("The archived paired trial has unmatched inputs.")
            run.update(record=record, operations=operation_groups(directory, record))
        runs[key] = run
    return runs


def scrubber(root, runs):
    replacements = {str(root): "<run-root>", text_file(INTERVENTION).strip(): "<masked instructions>"}
    for run_id, run in runs.items():
        directory = run["directory"]
        replacements.update({str(directory / "work"): "<workspace>", str(directory): "<run>"})
        for field in ("session_id", "agent_id", "task_name"):
            value = run["launch"].get(field) or run["launch"]["receipt"].get(field)
            if isinstance(value, str) and len(value) >= 7:
                replacements[value] = "<session>"
        for filename in ("baseline.md", "instructions.md"):
            path = directory / filename
            if path.is_file():
                replacements[text_file(path).strip()] = "<masked instructions>"
    replacements = sorted(replacements.items(), key=lambda item: -len(item[0]))
    ids = re.compile(r"\b(?:" + "|".join(re.escape(run_id) for run_id in runs) + r")\b")

    def scrub(value):
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()}
        if isinstance(value, str):
            for source, replacement in replacements:
                if source:
                    value = value.replace(source, replacement)
            value = ids.sub("<run>", value)
            value = ARM_LABEL.sub("<masked arm>", value)
            value = MODEL_LABEL.sub("<masked model>", value)
            return HOST_PATH.sub("<host path>", value)
        return value

    return scrub


def trial_state(run):
    if run["launch"]["status"] == "failed":
        return "launch-failed"
    if run["record"] is None:
        return "workspace-not-started"
    if run["record"]["outcome"] is None:
        return "terminal-record-missing"
    return run["record"]["outcome"]["outcome"]


def packet(run, scrub):
    record = run["record"]
    state = trial_state(run)
    actions = [
        {**{field: event[field] for field in ACTION_FIELDS}, "sample_timestamp_at_call": batch["timestamp"],
         "observed_operations": batch["operations"], "execution_error": event.get("execution_error")}
        for event, batch in zip(record["events"], run["operations"], strict=True)
    ] if record else []
    contents = {
        "task": text_file(PROMPT), "status": state, "actions": actions,
        "first_terminal_answer": record["reply"] if record else None,
        "terminal_clock": record["outcome"]["clock"] if record and record["outcome"] else None,
    }
    if "before_nudge" in run:
        contents.update(before_nudge=packet(run["before_nudge"], scrub), nudge=NUDGE)
    return scrub(contents)


def ground_card(run):
    record = run["record"]
    elapsed = 0
    if record and record["outcome"]:
        elapsed = record["outcome"]["clock"]["elapsed_seconds"]
    elif record and record["events"]:
        elapsed = record["events"][-1]["command_elapsed_seconds"]
    fixture = pressure_run.fixture()
    case = run["row"]["case"]
    samples = fixture.samples(case, elapsed)

    def process_summary(rows):
        fields = ("Name", "Id", "WorkingSet64", "PrivateMemorySize64", "CpuPercent")
        top = sorted(rows, key=lambda row: row["PrivateMemorySize64"], reverse=True)[:6]
        return {"working_set_bytes": sum(row["WorkingSet64"] for row in rows),
                "private_bytes": sum(row["PrivateMemorySize64"] for row in rows),
                "top_private_allocations": [{field: row[field] for field in fields} for row in top]}

    frames = [{"timestamp": row["timestamp"], "active_workers": row["workers"],
               "completed_jobs": row["completed"], "cpu_percent": row["cpu"],
               "processor_queue": row["queue"], "available_bytes": row["memory"]["AvailableBytes"],
               "total_visible_bytes": row["total_bytes"], "memory_counters": row["memory"],
               "pool_tag_rows": row["pool"], "process_summary": process_summary(row["processes"])} for row in samples]
    return {
        "read_only_fixture": True, "opening_timestamp": fixture.samples(case, 0)[-1]["timestamp"],
        "job_transition_active_seconds": list(fixture.TRANSITIONS), "visible_through_active_seconds": elapsed,
        "frames": frames,
        "tag_routes": ["native snapshot", "opening export only"] if "PoolPagedBytes" in samples[-1]["memory"]
        else ["semicolon-delimited export series"],
        "scope": "The sampled intervals can support a bounded pressure verdict and do not identify a driver or prove a leak.",
    }


def blind_entries(root, output, runs, manifest_name, provenance_name):
    if output.resolve().is_relative_to(root.resolve()):
        raise ValueError("Keep grading packets outside the archive with worker identities.")
    if (root / manifest_name).exists():
        raise ValueError("The blind manifest is already frozen.")
    scrub = scrubber(root, runs)
    entries = {"blind-" + secrets.token_hex(12): (key, packet(run, scrub), ground_card(run))
               for key, run in runs.items()}
    output.mkdir(parents=True, exist_ok=False)
    manifest = {}
    for opaque, (key, visible, ground) in sorted(entries.items()):
        write_json(output / (opaque + ".json"), visible)
        write_json(output / (opaque + ".ground.json"), ground)
        manifest[opaque] = {"id": key, "packet_sha256": json_digest(visible), "ground_sha256": json_digest(ground)}
    write_json(output / "checksums.json", {key: {field: value for field, value in entry.items() if field != "id"}
                                           for key, entry in manifest.items()})
    write_json(root / manifest_name, {"schema": SCHEMA, "schedule_sha256": SCHEDULE_SHA256,
                                      "provenance_sha256": digest((root / provenance_name).read_bytes()),
                                      "entries": manifest})
    return {"packets": len(manifest), "pending_grade": sum(run["record"] is not None for run in runs.values())}


def blind(root, output):
    return blind_entries(root, output, study(root), MANIFEST, LAUNCHES)


def counter_value(path, frame):
    if path.startswith("\\memory\\"):
        field = MEMORY_FIELDS.get(path.rsplit("\\", 1)[-1])
        signal = {"AvailableBytes": "available", "AvailableMBytes": "available", "PoolPagedBytes": "paged_pool",
                  "PoolNonpagedBytes": "nonpaged_pool"}.get(field)
        return signal, frame["memory"].get(field)
    if path.startswith("\\processor") and "\\% processor " in path:
        return "cpu", frame["cpu"]
    fields = {"\\system\\processor queue length": "queue", "\\paging file(_total)\\% usage": "pagefile_usage",
              "\\physicaldisk(_total)\\avg. disk queue length": "disk_queue"}
    return None, frame.get(fields.get(path))


def cim_signals(operation, frame):
    if not operation["found"] or not operation["rows"]:
        return ()
    properties = operation.get("fields") or []
    properties = {value.lower() for value in properties} if not isinstance(properties, str) else {properties.lower()}
    classes = {
        "win32_operatingsystem": {"freephysicalmemory": "available"},
        "win32_perfformatteddata_perfos_memory": {"availablebytes": "available", "availablembytes": "available",
                                                  "poolpagedbytes": "paged_pool", "poolnonpagedbytes": "nonpaged_pool"},
        "win32_perfformatteddata_perfos_processor": {"percentprocessortime": "cpu", "percentprocessorutility": "cpu"},
        "win32_processor": {"loadpercentage": "cpu"},
        "win32_process": {"workingsetsize": "process_memory", "workingset64": "process_memory"},
        "win32_perfformatteddata_perfproc_process": {"workingset": "process_memory", "workingsetprivate": "process_memory"},
    }
    return {signal for key, signal in classes.get(operation["class"].lower(), {}).items()
            if (not properties or key in properties or "*" in properties)
            and (signal not in ("paged_pool", "nonpaged_pool") or "PoolPagedBytes" in frame["memory"])}


def archive_bytes(frame):
    out = io.StringIO(newline="")
    names = ("Timestamp", "Tag", "Type", "Bytes", "CIActive", "CICompleted")
    writer = csv.DictWriter(out, names, delimiter=";")
    writer.writeheader()
    for tag in frame["pool"]:
        writer.writerow({**tag, "Timestamp": frame["timestamp"], "CIActive": frame["workers"],
                         "CICompleted": frame["completed"]})
    return out.getvalue().encode()


def archive_samples(case, frames):
    opening = frames[2]
    following = frames[3:] if case == "archive" else []
    for frame in (opening, *following):
        stamp = frame["timestamp"].replace("-", "").replace(":", "").replace("T", "-")[:-2]
        yield f"captures/memory/{stamp}.csv", frame


def archive_sample(operation, event, known):
    path = operation["path"].replace("\\", "/").removeprefix("./").lower()
    frame = known.get(path)
    if frame is None or event["exit"] or event["timed_out"]:
        return None
    payload = archive_bytes(frame)
    received = operation.get("source_sha256") or operation.get("sha256")
    if received and received.lower() != digest(payload):
        raise ValueError("An archive read differs from the replay sample.")
    if operation.get("operation") == "archive_read" and received and operation.get("parsed"):
        return frame
    stdout = event["stdout"]
    tag_bytes = str(next(row["Bytes"] for row in frame["pool"] if row["Tag"] == "File"))
    compact = re.sub(r"(?<=\d)[ ,](?=\d)", "", stdout)
    has_time = frame["timestamp"] in stdout or frame["timestamp"].split("T")[-1] in stdout
    has_value = tag_bytes in compact and re.search(r"\bFile\b", stdout) is not None
    csv_parsed = operation.get("cmdlet", "").lower() != "import-csv" or operation.get("delimiter") == ";"
    return frame if csv_parsed and has_value and (has_time or len(known) == 1) else None


def spans_transition(stamps, frames):
    completed = {frame["completed"] for frame in frames if frame["timestamp"] in stamps}
    return len(completed) >= 2


def telemetry(run):
    record = run["record"]
    if record is None:
        return None
    fixture, case = pressure_run.fixture(), run["row"]["case"]
    observed = defaultdict(set)
    unverified, action_sources = [], []
    events, operations = record["events"], run["operations"]
    if "before_nudge" in run:
        prefix = run["before_nudge"]
        events = prefix["record"]["events"] + events
        operations = prefix["operations"] + operations
    for action, (event, batch) in enumerate(zip(events, operations, strict=True), 1):
        frames = fixture.samples(case, event["start_elapsed_seconds"])
        latest, by_time = frames[-1], {row["timestamp"]: row for row in frames}
        archives = dict(archive_samples(case, frames))
        sources = defaultdict(set)
        for operation in batch["operations"]:
            op = operation["operation"]
            if op == "counters":
                for sample in operation["samples"]:
                    frame = by_time.get(sample["timestamp"])
                    if frame is None:
                        raise ValueError("A counter sample occurs before its replay frame is available.")
                    signal, expected = counter_value(sample["path"], frame)
                    if expected is not None and sample["value"] != expected:
                        raise ValueError("Counter telemetry differs from the replay sample.")
                    if signal and expected is not None:
                        sources[signal].add(frame["timestamp"])
                    if expected is None:
                        unverified.append({"action": action, "source": sample["path"],
                                           "reason": "counter reading has no matching fixture sample"})
            elif op == "cim":
                for signal in cim_signals(operation, latest):
                    sources[signal].add(latest["timestamp"])
            elif op == "processes" and operation["rows"]:
                sources["process_memory"].add(latest["timestamp"])
            elif op == "poolmon":
                expected = sorted(latest["pool"], key=lambda row: row["Tag"])
                if case != "native" or sorted(operation["tag_rows"], key=lambda row: row["Tag"]) != expected:
                    raise ValueError("Pool tag telemetry differs from the replay sample.")
                if operation["tag_rows"]:
                    for signal in ("file_tag", "tagged_pool"):
                        sources[signal].add(latest["timestamp"])
            elif op in ("archive_open", "archive_read"):
                frame = archive_sample(operation, event, archives)
                if frame is not None:
                    for signal in ("file_tag", "tagged_pool"):
                        sources[signal].add(frame["timestamp"])
                else:
                    unverified.append({"action": action, "source": operation["path"],
                                       "reason": "archive access recorded without corroborating sample data"})
        if not sources and not batch["operations"] and event["stdout"].strip():
            unverified.append({"action": action, "source": "command output",
                               "reason": "output has no instrumented source; inspect for alternative evidence"})
        for signal, stamps in sources.items():
            observed[signal].update(stamps)
        if sources:
            action_sources.append({"action": action, "signals": {key: sorted(value)
                                                                         for key, value in sources.items()}})
    elapsed = record["outcome"]["clock"]["elapsed_seconds"] if record["outcome"] else pressure_run.BUDGET_SECONDS
    frames = fixture.samples(case, elapsed)
    coverage = {signal: spans_transition(observed[signal], frames)
                for signal in ("cpu", "available", "process_memory", "file_tag", "tagged_pool", "paged_pool", "nonpaged_pool")}
    return {"coverage_across_completed_jobs": coverage, "actions": action_sources, "reviewable_sources": unverified,
            "corroborated": coverage["cpu"] and coverage["available"] and coverage["file_tag"]
            and (coverage["tagged_pool"] or (coverage["paged_pool"] and coverage["nonpaged_pool"]))}


def command_syntax(excerpt):
    executable = shutil.which("pwsh")
    if executable is None:
        return {"status": "parser-unavailable"}
    parsed = subprocess.run([executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", PARSE_SCRIPT],
                            input=excerpt, text=True, capture_output=True, timeout=15, check=True)
    result = json.loads(parsed.stdout)
    names = [name for name in result["names"] if isinstance(name, str)]
    flagged = [name for name in names if STATE_CHANGE.fullmatch(name)]
    status = "parsed"
    if result["errors"]:
        status = "syntax-error"
    elif flagged:
        status = "state-change"
    elif not result["command_count"]:
        status = "no-command"
    return {"status": status, "errors": result["errors"], "state_change_commands": flagged}


def grade_times(grade, visible):
    actions = visible["actions"]

    def valid(index, minimum=1):
        return type(index) is int and minimum <= index <= len(actions)

    for field in BOOL_FIELDS:
        if type(grade[field]) is not bool:
            raise ValueError(f"The blind grade requires a boolean {field}.")
    for field in ACTION_LISTS:
        indices = grade[field]
        if (not isinstance(indices, list) or any(not valid(index) for index in indices)
                or len(set(indices)) != len(indices)):
            raise ValueError(f"The blind grade has invalid action indices for {field}.")
    if set(grade["mixed_actions"]) & set(grade["side_actions"]):
        raise ValueError("A mixed action must be counted separately from side actions.")
    first, useful = grade["first_consequential_action"], grade["first_useful_action"]
    answer = visible["first_terminal_answer"]
    if ((first is not None and not valid(first) and not (first == "answer" and answer))
            or (useful is not None and (not valid(useful) or not valid(first) or useful < first))):
        raise ValueError("A first action is missing from the eligible trace.")
    known = grade["irrelevance_knowable_after"]
    if known is not None and not valid(known, 0):
        raise ValueError("The irrelevance decision point is missing from the trace.")
    later = sum(index > known for index in grade["side_actions"]) if known is not None else 0
    if grade["sustained_detour"] != (later >= 2):
        raise ValueError("A sustained detour needs at least two side actions after the decision point.")
    if ((grade["delivery"] and (not answer or grade["false_done"] or grade["unassisted_incomplete"]))
            or (grade["false_done"] and not answer) or (grade["nudge_needed"] and not grade["unassisted_incomplete"])):
        raise ValueError("Delivery, incomplete work and nudge grades disagree.")
    if not isinstance(grade["basis"], str) or not grade["basis"].strip():
        raise ValueError("The blind grade has no evidence basis.")
    excerpt = grade["command_excerpt"]
    if excerpt is not None and (not isinstance(excerpt, str) or not excerpt.strip() or excerpt not in (answer or "")):
        raise ValueError("The PowerShell excerpt does not appear in the terminal answer.")
    if grade["usable_command"] and excerpt is None:
        raise ValueError("The grade requires the operator-facing PowerShell excerpt.")
    syntax = command_syntax(excerpt) if excerpt else None

    def selected_seconds(field):
        return round(sum(actions[index - 1]["seconds"] for index in grade[field]), 6)

    return {"first_useful_seconds": actions[useful - 1]["command_elapsed_seconds"] if useful else None,
            "first_consequential_completion_seconds": actions[first - 1]["command_elapsed_seconds"] if valid(first)
            else visible["terminal_clock"]["elapsed_seconds"] if first == "answer" else None,
            "side_shell_seconds": selected_seconds("side_actions"), "mixed_shell_seconds": selected_seconds("mixed_actions"),
            "repeated_shell_seconds": selected_seconds("repeated_no_progress_actions"), "command_syntax": syntax}


def coverage(mark, oracle, times, visible):
    if mark is None:
        return "not-graded"
    if (visible["status"] != "finished" or not all(mark[field] for field in ("delivery", "usable_command", "limits"))
            or mark["missed_dependency"]):
        return "incomplete"
    if times["command_syntax"]["status"] in ("syntax-error", "state-change", "no-command"):
        return "command-failed-validation"
    if not oracle["corroborated"] or times["command_syntax"]["status"] != "parsed":
        return "needs-evidence-review"
    return "verified"


def scored(root, runs, manifest_name, provenance_name, grades_name):
    manifest, grades = (read_json(root / name) for name in (manifest_name, grades_name))
    entries, marks = manifest["entries"], grades["grades"]
    if (manifest["schema"] != SCHEMA or manifest["schedule_sha256"] != SCHEDULE_SHA256 or grades["schema"] != SCHEMA
            or manifest["provenance_sha256"] != digest((root / provenance_name).read_bytes())
            or len(entries) != len(runs) or {entry["id"] for entry in entries.values()} != set(runs)
            or any(not OPAQUE.fullmatch(key) for key in entries)):
        raise ValueError("The blind manifest differs from the scheduled trials or launch evidence.")
    if any(not isinstance(grades["judge"].get(key), str) or not grades["judge"][key].strip() for key in ("id", "method")):
        raise ValueError("Blind grade provenance is missing.")
    required = {key for key, entry in entries.items() if runs[entry["id"]]["record"] is not None}
    if set(marks) != required:
        raise ValueError("Blind grades must cover every started workspace exactly once.")
    by_id, summaries = {entry["id"]: key for key, entry in entries.items()}, {}
    scrub = scrubber(root, runs)
    for key, run in runs.items():
        opaque = by_id[key]
        entry, grade = entries[opaque], marks.get(opaque)
        visible, ground = packet(run, scrub), ground_card(run)
        for field, value in (("packet_sha256", visible), ("ground_sha256", ground)):
            if entry[field] != json_digest(value) or (grade is not None and grade[field] != entry[field]):
                raise ValueError("Archived evidence does not match the sealed grading packet.")
        oracle = telemetry(run)
        measures = grade_times(grade, visible) if grade is not None else None
        if measures and "before_nudge" in run:
            started_at = run["record"]["started"]["prior_seconds"]
            useful_at = measures["first_useful_seconds"]
            measures["first_useful_seconds_after_nudge"] = useful_at - started_at if useful_at is not None else None
        summaries[key] = {**run["row"], "launch_status": run["launch"]["status"], "outcome": visible["status"],
                          "grade": grade, "telemetry_oracle": oracle, "measures": measures,
                          "first_pass_delivery": coverage(grade, oracle, measures, visible)}
    return summaries, grades["judge"]


def rescue_runs(root, runs, first):
    rescues = read_json(root / RESCUES)
    added = {}
    for key, rescue in rescues.items():
        original = runs[key]
        mark, record = first[key]["grade"], original["record"]
        if (not mark or not mark["unassisted_incomplete"] or record["outcome"] is None
                or rescue["session_id"] != original["launch"]["session_id"] or rescue["nudge"] != NUDGE
                or rescue["receipt"].get("task_name") != original["launch"]["receipt"]["task_name"]):
            raise ValueError("The rescue lacks an eligible same-worker nudge receipt.")
        directory = root / directory_name(rescue["directory"])
        if directory in {run["directory"] for run in (*runs.values(), *added.values())}:
            raise ValueError("A rescue attempts to reuse an archived workspace.")
        resumed, operations = None, []
        if (directory / "started.json").exists():
            resumed = pressure_run.replay(directory)
            if resumed["manifest"].get("recovery") != pressure_run.recovery_link(original["directory"], record["outcome"]):
                raise ValueError("The rescue does not link to its original terminal state.")
            operations = operation_groups(directory, resumed)
        added[key] = {**original, "record": resumed, "directory": directory, "operations": operations,
                      "before_nudge": original}
    return added


def blind_rescue(root, output):
    runs = study(root)
    first, _ = scored(root, runs, MANIFEST, LAUNCHES, GRADES)
    return blind_entries(root, output, rescue_runs(root, runs, first), RESCUE_MANIFEST, RESCUES)


def totals(group):
    graded = [row for row in group if row["grade"] is not None]
    arrival = [row["measures"]["first_useful_seconds"] for row in graded
               if row["measures"]["first_useful_seconds"] is not None]
    return {"planned": len(group), "outcomes": dict(Counter(row["outcome"] for row in group)),
            "delivery": dict(Counter(row["first_pass_delivery"] for row in group)),
            "side_actions": sum(len(row["grade"]["side_actions"]) for row in graded),
            "mixed_actions": sum(len(row["grade"]["mixed_actions"]) for row in graded),
            "repeated_no_progress_actions": sum(len(row["grade"]["repeated_no_progress_actions"]) for row in graded),
            "side_shell_seconds": round(sum(row["measures"]["side_shell_seconds"] for row in graded), 6),
            "first_useful_observations": len(arrival), "median_first_useful_seconds": median(arrival) if arrival else None,
            **{field: sum(row["grade"][field] for row in graded)
               for field in ("sustained_detour", "missed_dependency", "false_done", "unassisted_incomplete", "nudge_needed")}}


def replay(root):
    runs = study(root)
    summaries, judge = scored(root, runs, MANIFEST, LAUNCHES, GRADES)
    arms, pairs, by_model_and_case = {}, defaultdict(dict), defaultdict(dict)
    for arm in pressure_run.ARMS:
        group = [summary for summary in summaries.values() if summary["arm"] == arm]
        arms[arm] = totals(group)
        strata = defaultdict(list)
        for row in group:
            strata[(row["model"], row["case"])].append(row)
            pairs[row["pair"]][arm] = {"id": row["id"], "delivery": row["first_pass_delivery"],
                                        "first_useful_seconds": row["measures"]["first_useful_seconds"] if row["measures"] else None}
        for (model, case), stratum in strata.items():
            by_model_and_case[model].setdefault(case, {})[arm] = totals(stratum)
    result = {"schema": SCHEMA, "schedule_sha256": SCHEDULE_SHA256, "judge": judge, "arms": arms,
              "by_model_and_case": dict(by_model_and_case),
              "historical_operator_nudge_observed": 1, "replay_nudges_observed_in_first_pass": 0,
              "pairs": dict(pairs), "trials": summaries, "observed_post_pass_nudges": 0}
    if (root / RESCUES).exists():
        rescues = rescue_runs(root, runs, summaries)
        result["observed_post_pass_nudges"] = len(rescues)
        if (root / RESCUE_GRADES).exists():
            rescued, rescue_judge = scored(root, rescues, RESCUE_MANIFEST, RESCUES, RESCUE_GRADES)
            for row in rescued.values():
                row["post_nudge_delivery"] = row.pop("first_pass_delivery")
            result.update(rescues=rescued, rescue_judge=rescue_judge)
        else:
            result["rescues_pending_grade"] = sorted(rescues)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    export = commands.add_parser("blind")
    export.add_argument("root", type=Path)
    export.add_argument("output", type=Path)
    resume = commands.add_parser("blind-rescue")
    resume.add_argument("root", type=Path)
    resume.add_argument("output", type=Path)
    commands.add_parser("replay").add_argument("root", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "replay":
            result = replay(args.root.resolve())
        else:
            exporter = blind if args.action == "blind" else blind_rescue
            result = exporter(args.root.resolve(), args.output.resolve())
    except (KeyError, OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
