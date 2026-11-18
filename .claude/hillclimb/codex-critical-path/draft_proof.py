"""Export blinded handoff evidence and replay the matched checkpoint comparison."""

import argparse
import io
import json
import secrets
import subprocess
import tarfile
from collections import defaultdict
from pathlib import Path
from statistics import median

import draft_run
import pressure_proof
import pressure_run
from proof import directory_name, json_digest, read_json
from trial import HERE, digest, write_json


SCHEDULE = HERE / "draft_schedule.json"
SCHEDULE_SHA256 = "b1e7111cbf4bcf6ac7158d1e1756b3155e2fad00436acd7495f93dfe812db592"
INTERVENTION = HERE / "draft_intervention.txt"
INTERVENTION_SHA256 = "33eb497f54191dc015800879de30665bb305496caff34728c929bdb323bcfb14"
ARCHIVE = ".claude/hillclimb/codex-critical-path/evidence/pressure-trials.tar.gz"
LAUNCHES = "launches.json"
MANIFEST = "draft_blind_manifest.json"
GRADES = "draft_grades.json"
BOOL_FIELDS = ("delivered", "nudge_needed", "missed_dependency", "sustained_detour")
ACTION_LISTS = ("side_actions", "repeated_actions")
SOURCE_FILES = (*pressure_run.LOG_NAMES, "end.json", "reply.txt", "instructions.md", "task.txt")


def frozen_sources(schedule):
    data = subprocess.check_output(["git", "show", f"{schedule['source_commit']}:{ARCHIVE}"], cwd=HERE, timeout=15)
    if digest(data) != schedule["source_archive_sha256"]:
        raise ValueError("The published pressure archive differs from the freeze.")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        sources = {
            source: {name: digest(archive.extractfile(f"./{source}/{name}").read()) for name in SOURCE_FILES}
            for source in schedule["source_digests"]
        }
        for source, expected in schedule["source_digests"].items():
            if {name: value for name, value in sources[source].items() if name != "started.json"} != expected:
                raise ValueError(f"The published files disagree with the frozen source {source}.")
        original_launches = json.load(archive.extractfile("./" + pressure_proof.LAUNCHES))
        capture_root = json.load(archive.extractfile("./capture-location.json"))["root"]
    for row in schedule["rows"]:
        original = original_launches[row["source"]]
        if original["status"] != "opened" or any(original[key] != row[key] for key in ("model", "reasoning_effort")):
            raise ValueError(f"The source and checkpoint launch inputs disagree for {row['id']}.")
    return sources, capture_root


def checked_schedule():
    if digest(SCHEDULE.read_bytes()) != SCHEDULE_SHA256:
        raise ValueError("The checkpoint schedule differs from the frozen order.")
    if digest(INTERVENTION.read_bytes().strip()) != INTERVENTION_SHA256:
        raise ValueError("The candidate paragraph differs from the freeze.")
    schedule = read_json(SCHEDULE)
    rows, pairs = schedule["rows"], defaultdict(list)
    for row in rows:
        pairs[row["pair"]].append(row)
    if (len(rows) != 12 or len({row["id"] for row in rows}) != 12 or len(pairs) != 6
            or set(schedule["source_digests"]) != {row["source"] for row in rows}):
        raise ValueError("The checkpoint schedule is incomplete.")
    for pair in pairs.values():
        fields = ("source", "model", "reasoning_effort", "rep")
        if ({row["arm"] for row in pair} != set(pressure_run.ARMS)
                or len({tuple(row[key] for key in fields) for row in pair}) != 1):
            raise ValueError("A checkpoint pair has unmatched inputs.")
    return schedule


def verify_overlay(directory, row):
    entry, instructions = draft_run.presentation(directory / "prefix", row["arm"])
    expected = {"arm": row["arm"], "source": row["source"],
                "background_sha256": digest((directory / "prefix" / "instructions.md").read_bytes()),
                "presented_instructions_sha256": digest(instructions),
                "intervention_sha256": INTERVENTION_SHA256 if row["arm"] == "candidate" else None,
                "presentation_sha256": digest(entry), "runner_sha256": digest(Path(draft_run.__file__).read_bytes())}
    if (read_json(directory / "overlay.json") != expected
            or (directory / "presentation.md").read_bytes() != entry):
        raise ValueError(f"The presentation and frozen overlay disagree for {row['id']}.")
    return expected


def study(root):
    schedule = checked_schedule()
    sources, capture_root = frozen_sources(schedule)
    launches = read_json(root / LAUNCHES)
    if set(launches) != {row["id"] for row in schedule["rows"]}:
        raise ValueError("Launch receipts do not cover the frozen checkpoint order.")
    runs = {}
    for row in schedule["rows"]:
        key = directory_name(row["id"])
        directory, launch = root / key, launches[key]
        receipt = launch["receipt"]
        if (any(launch[name] != row[name] for name in ("model", "reasoning_effort"))
                or launch["fork_turns"] != "none" or receipt.get("task_name") != "/root/" + key
                or any(name in receipt and receipt[name] != launch[name]
                       for name in ("model", "reasoning_effort", "fork_turns"))):
            raise ValueError(f"The launch receipt differs from the frozen inputs for {key}.")
        prefix = directory / "prefix"
        for name, expected in sources[row["source"]].items():
            if digest((prefix / name).read_bytes()) != expected:
                raise ValueError(f"The copied source file differs from the published state for {key}: {name}.")
        original = pressure_run.replay(prefix)
        overlay = verify_overlay(directory, row)
        before = {"directory": prefix, "record": original, "operations": pressure_proof.operation_groups(prefix, original)}
        record, operations = None, []
        issued = directory / "issued.json"
        if (directory / "started.json").exists():
            record = pressure_run.replay(directory)
            if read_json(issued) != {"presentation_sha256": overlay["presentation_sha256"],
                                     "started_utc": record["started"]["utc"]}:
                raise ValueError(f"The worker presentation receipt disagrees for {key}.")
            operations = pressure_proof.operation_groups(directory, record)
        elif issued.exists():
            raise ValueError(f"A presentation was issued without a checkpoint start for {key}.")
        runs[key] = {"row": {**row, "case": original["manifest"]["case"]}, "directory": directory,
                     "launch": launch, "record": record, "before_nudge": before, "operations": operations}
    return runs, capture_root


def action_evidence(run, offset):
    actions = []
    if run["record"] is None:
        return actions
    for event, batch in zip(run["record"]["events"], run["operations"], strict=True):
        action = {key: event[key] for key in pressure_proof.ACTION_FIELDS}
        for key in ("start_elapsed_seconds", "command_elapsed_seconds"):
            action[key] = round(action[key] - offset, 6)
        actions.append({**action, "sample_timestamp_at_call": batch["timestamp"],
                        "observed_operations": batch["operations"], "execution_error": event.get("execution_error")})
    return actions


def packet(run, scrub):
    earlier, record = run["before_nudge"], run["record"]
    checkpoint = earlier["record"]["outcome"]["clock"]["elapsed_seconds"]
    outcome = record["outcome"] if record else None
    actions = action_evidence(run, checkpoint)
    visible = {
        "task": (earlier["directory"] / "task.txt").read_text(encoding="utf-8"),
        "prior_actions": action_evidence(earlier, checkpoint),
        "pre_dispatch_draft": earlier["record"]["reply"],
        "post_checkpoint_actions": actions,
        "submitted_reply": record["reply"] if record else None,
        "status": outcome["outcome"] if outcome else "terminal-record-missing" if record else "workspace-not-started",
        "elapsed_seconds_after_checkpoint": round(outcome["clock"]["elapsed_seconds"] - checkpoint, 6) if outcome else None,
        "last_recorded_action_seconds_after_checkpoint": actions[-1]["command_elapsed_seconds"] if actions else None,
    }
    ground = pressure_proof.ground_card(run if outcome or actions else {**run, "record": earlier["record"]})
    return scrub(visible), ground


def blind_scrubber(root, runs, source_root, capture_root):
    base_scrub = pressure_proof.scrubber(root, runs)
    masks = {INTERVENTION.read_text(encoding="utf-8").strip(): "<masked instructions>"}
    for key, run in runs.items():
        source = run["row"]["source"]
        for location in (Path(source_root) / source, capture_root / key):
            masks.update({str(location / "work"): "<workspace>", str(location): "<run>"})
        masks[source] = "<run>"

    def scrub(value):
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()}
        if isinstance(value, str):
            for source, replacement in masks.items():
                value = value.replace(source, replacement)
        return base_scrub(value)

    return scrub


def blind(root, panel):
    if panel.is_relative_to(root) or (root / MANIFEST).exists():
        raise ValueError("Write the blind panel outside the study and freeze it only once.")
    runs, source_root = study(root)
    scrub = blind_scrubber(root, runs, source_root, root)
    panel.mkdir(parents=True, exist_ok=False)
    entries = {}
    for opaque, key in sorted(("blind-" + secrets.token_hex(12), key) for key in runs):
        visible, ground = packet(runs[key], scrub)
        write_json(panel / f"{opaque}.json", visible)
        write_json(panel / f"{opaque}.ground.json", ground)
        entries[opaque] = {"id": key, "sha256": json_digest(visible), "ground_sha256": json_digest(ground)}
    write_json(panel / "checksums.json", {key: {field: value for field, value in entry.items() if field != "id"}
                                          for key, entry in entries.items()})
    write_json(root / MANIFEST, {"schedule_sha256": SCHEDULE_SHA256,
                                 "launches_sha256": digest((root / LAUNCHES).read_bytes()),
                                 "capture_root": str(root), "entries": entries})
    return {"packets": len(entries)}


def measures(mark, visible):
    actions = visible["post_checkpoint_actions"]
    answer = visible["submitted_reply"]

    def valid(index):
        return type(index) is int and 1 <= index <= len(actions)

    def selected_seconds(indices):
        return round(sum(actions[index - 1]["seconds"] for index in indices), 6)

    for field in BOOL_FIELDS:
        if type(mark[field]) is not bool:
            raise ValueError(f"The blind grade requires a boolean {field}.")
    for field in ACTION_LISTS:
        indices = mark[field]
        if not isinstance(indices, list) or any(not valid(index) for index in indices) or len(indices) != len(set(indices)):
            raise ValueError(f"The blind grade has invalid indices for {field}.")
    meaningful = mark["meaningful_action"]
    if meaningful is not None and not valid(meaningful) and not (meaningful == "answer" and answer):
        raise ValueError("The first meaningful action is missing from the checkpoint trace.")
    excerpt = mark["command_excerpt"]
    if excerpt is not None and (not isinstance(excerpt, str) or not excerpt.strip() or excerpt not in (answer or "")):
        raise ValueError("The PowerShell excerpt does not appear in the submitted reply.")
    if (not isinstance(mark["basis"], str) or not mark["basis"].strip()
            or (mark["sustained_detour"] and len(mark["side_actions"]) < 2)
            or (mark["delivered"] and (visible["status"] != "finished" or not answer or not excerpt
                                       or mark["missed_dependency"] or mark["nudge_needed"]))):
        raise ValueError("The blind grade disagrees with the recorded checkpoint outcome.")
    elapsed = visible["elapsed_seconds_after_checkpoint"]
    return {"post_checkpoint_actions": len(actions), "shell_seconds": selected_seconds(range(1, len(actions) + 1)),
            "elapsed_seconds_after_checkpoint": elapsed,
            "last_recorded_action_seconds_after_checkpoint": visible["last_recorded_action_seconds_after_checkpoint"],
            "side_shell_seconds": selected_seconds(mark["side_actions"]),
            "repeated_shell_seconds": selected_seconds(mark["repeated_actions"]),
            "first_meaningful_seconds": actions[meaningful - 1]["command_elapsed_seconds"] if valid(meaningful)
            else elapsed if meaningful == "answer" else None,
            "command_syntax": pressure_proof.command_syntax(excerpt) if excerpt else None}


def arm_summary(records):
    times = [record["measures"]["elapsed_seconds_after_checkpoint"] for record in records
             if record["measures"]["elapsed_seconds_after_checkpoint"] is not None]
    return {"planned": len(records), **{field: sum(row["grade"][field] for row in records) for field in BOOL_FIELDS},
            **{field: sum(len(row["grade"][field]) for row in records) for field in ACTION_LISTS},
            **{field: round(sum(row["measures"][field] for row in records), 6)
               for field in ("post_checkpoint_actions", "shell_seconds", "side_shell_seconds", "repeated_shell_seconds")},
            "observed_terminal_times": len(times), "median_elapsed_seconds_after_checkpoint": median(times) if times else None}


def replay(root):
    runs, source_root = study(root)
    manifest, grades = read_json(root / MANIFEST), read_json(root / GRADES)
    entries = manifest["entries"]
    if (manifest["schedule_sha256"] != SCHEDULE_SHA256 or manifest["launches_sha256"] != digest((root / LAUNCHES).read_bytes())
            or len(entries) != len(runs) or {entry["id"] for entry in entries.values()} != set(runs)
            or set(entries) != set(grades) or any(not pressure_proof.OPAQUE.fullmatch(key) for key in entries)):
        raise ValueError("The sealed panel or blind grades differ from the launched checkpoints.")
    scrub = blind_scrubber(root, runs, source_root, Path(manifest["capture_root"]))
    records, pairs, models = {}, defaultdict(dict), defaultdict(lambda: defaultdict(list))
    for opaque, entry in entries.items():
        key = entry["id"]
        run, grade = runs[key], grades[opaque]
        visible, ground = packet(run, scrub)
        if entry["sha256"] != json_digest(visible) or grade["sha256"] != entry["sha256"] or entry["ground_sha256"] != json_digest(ground):
            raise ValueError(f"The blind grade or panel differs from the captured checkpoint for {key}.")
        row = run["row"]
        records[key] = {**row, "status": visible["status"], "grade": grade, "measures": measures(grade, visible),
                        "telemetry_oracle": pressure_proof.telemetry(run)}
        pairs[row["pair"]][row["arm"]] = key
        models[row["model"]][row["arm"]].append(records[key])
    return {"schedule_sha256": SCHEDULE_SHA256, "pairs": dict(pairs), "trials": records,
            "arms": {arm: arm_summary([row for row in records.values() if row["arm"] == arm]) for arm in pressure_run.ARMS},
            "by_model": {model: {arm: arm_summary(rows) for arm, rows in arms.items()} for model, arms in models.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    export = commands.add_parser("blind")
    export.add_argument("root", type=Path)
    export.add_argument("panel", type=Path)
    commands.add_parser("replay").add_argument("root", type=Path)
    args = parser.parse_args()
    try:
        result = blind(args.root.resolve(), args.panel.resolve()) if args.action == "blind" else replay(args.root.resolve())
    except (KeyError, OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
