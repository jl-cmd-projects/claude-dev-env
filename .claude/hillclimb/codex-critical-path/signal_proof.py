"""Seal blinded pressure-handoff packets and replay delivery, time, and review cost."""

import argparse
import json
import secrets
import subprocess
import tarfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

import draft_proof
import pressure_proof
import pressure_run
import signal_run
from proof import directory_name, json_digest, read_json
from trial import HERE, digest, write_json


SCHEDULE = "signal_schedule.json"
SCHEDULE_SHA256 = "db1745e9fa581d141e8260eb64ae875401698d005b41c73a7f392ad82b8394c7"
ROLE_SHA256 = "975f9da9ce94fe89549a843bf10430a661b77a1332da5473e06c628d8b17f2dd"
MANIFEST = "signal_blind_manifest.json"
LAUNCHES = draft_proof.LAUNCHES
GRADES = draft_proof.GRADES
REVIEWER_MODEL = {"model": "gpt-6.2-sol", "reasoning_effort": "high"}


def schedule_for(root):
    path = root / SCHEDULE
    if not path.exists():
        path = HERE / SCHEDULE
    if digest(path.read_bytes()) != SCHEDULE_SHA256:
        raise ValueError("The schedule differs from the frozen intervention and order.")
    schedule = read_json(path)
    if (signal_run.hash_if_present(Path(signal_run.signal_rule.__file__)) != schedule["gate_sha256"]
            or signal_run.hash_if_present(signal_run.ROLE) != ROLE_SHA256):
        raise ValueError("The alert rule or reviewer prompt differs from the freeze.")
    return schedule


def validate_launch(key, row, launch):
    receipt = launch["receipt"]
    status = launch.get("status", "opened")
    fields = ("model", "reasoning_effort")
    if (any(launch[field] != row[field] for field in fields)
            or launch["fork_turns"] != "none" or status not in ("opened", "failed")
            or not isinstance(receipt, dict) or not receipt
            or any(field in receipt and receipt[field] != launch[field] for field in (*fields, "fork_turns"))
            or (status == "opened" and receipt.get("task_name") != "/root/" + key)):
        raise ValueError(f"The launch evidence differs from the matched inputs for {key}.")
    return status


def load_run(root, row, launch, source_hashes, expected_alert, reviewers):
    key = directory_name(row["id"])
    directory = root / key
    launch_status = validate_launch(key, row, launch)
    prefix = directory / "prefix"
    original = pressure_run.replay(prefix)
    inputs = signal_run.source_inputs(prefix)
    if any(inputs[name] != value for name, value in source_hashes.items()):
        raise ValueError(f"The copied checkpoint differs from the pinned archive for {key}.")
    review_dir = reviewers[row["reviewer"]]["directory"] if row["reviewer"] else None
    if signal_run.alert_for(prefix, original) != expected_alert.encode():
        raise ValueError(f"The alert result differs from the frozen screening for {key}.")
    content, overlay = signal_run.handoff(directory, row["source"], row["arm"], review_dir)
    if (read_json(directory / "overlay.json") != overlay
            or (directory / "presentation.md").read_bytes() != content):
        raise ValueError(f"The presentation differs from the recorded intervention for {key}.")
    record, operations = None, []
    if (directory / "started.json").exists():
        if launch_status != "opened":
            raise ValueError(f"The trial started without an opened launch receipt for {key}.")
        record = pressure_run.replay(directory)
        signal_run.verify_issued(directory, overlay, record["started"])
        operations = pressure_proof.operation_groups(directory, record)
    elif (directory / "issued.json").exists():
        raise ValueError(f"The handoff was issued without a recorded start for {key}.")
    return {
        "row": {**row, "case": original["manifest"]["case"]}, "directory": directory,
        "launch": launch, "launch_status": launch_status, "record": record, "operations": operations,
        "before_nudge": {"directory": prefix, "record": original,
                         "operations": pressure_proof.operation_groups(prefix, original)},
        "overlay": overlay, "alert_triggered": bool(expected_alert),
    }


def study(root):
    schedule = schedule_for(root)
    sources, source_root = draft_proof.frozen_sources(schedule)
    launches = read_json(root / LAUNCHES)
    rows = schedule["rows"]
    review_rows = [
        {"source": row["source"], "id": row["reviewer"], "arm": signal_run.REVIEWER,
         "reviewer": None, **REVIEWER_MODEL}
        for row in rows if row["reviewer"]
    ]
    ids = {row["id"] for row in (*rows, *review_rows)}
    if set(launches) != ids or len(ids) != len(rows) + len(review_rows):
        raise ValueError("Launch evidence must cover every frozen solver and triggered reviewer once.")
    for field in ("agent_id", "session_id"):
        opened_values = [
            launch["receipt"][field] for launch in launches.values()
            if launch.get("status", "opened") == "opened" and launch["receipt"].get(field)
        ]
        if len(set(opened_values)) != len(opened_values):
            raise ValueError("A worker receipt was reused across scheduled launches.")
    reviewers, runs = {}, {}
    for row in (*review_rows, *rows):
        key, source = row["id"], row["source"]
        alert = schedule["screened_historical_runs"][source]
        if row["arm"] == signal_run.REVIEWER:
            target = reviewers
        else:
            target = runs
            if bool(row["reviewer"]) != (row["arm"] == "review" and bool(alert)):
                raise ValueError(f"The reviewer assignment disagrees with the frozen gate for {key}.")
        target[key] = load_run(root, row, launches[key], sources[source], alert, reviewers)
    pairs = defaultdict(list)
    for run in runs.values():
        pairs[run["row"]["pair"]].append(run)
    for pair in pairs.values():
        matchup = {(run["row"]["source"], run["row"]["model"], run["row"]["rep"], run["row"]["reasoning_effort"],
                    run["overlay"]["input_match_key"], run["overlay"]["background_sha256"]) for run in pair}
        exposed = {run["overlay"]["presentation_sha256"] for run in pair}
        if (len(pair) != len(signal_run.ARMS) or {run["row"]["arm"] for run in pair} != set(signal_run.ARMS)
                or len(matchup) != 1 or (not pair[0]["alert_triggered"] and len(exposed) != 1)):
            raise ValueError("A matched triplet disagrees on its source, inputs, or gated presentation.")
    return runs, reviewers, Path(source_root)


def blind_scrub(root, runs, reviewers, source_root, capture_root):
    return draft_proof.blind_scrubber(root, {**runs, **reviewers}, source_root, capture_root)


def packet(run, scrub):
    visible, ground = draft_proof.packet(run, scrub)
    if run["launch_status"] == "failed":
        visible["status"] = "launch-failed"
    return visible, ground


def capture_digest(runs, reviewers):
    files = ("overlay.json", "issued.json", "started.json", "end.json", "events.jsonl",
             pressure_run.RECEIPTS, "reply.txt")
    return json_digest({
        key: {name: signal_run.hash_if_present(run["directory"] / name) for name in files}
        for key, run in {**runs, **reviewers}.items()
    })


def blind(root, panel):
    if panel.is_relative_to(root) or (root / MANIFEST).exists():
        raise ValueError("Write the blind panel outside the study and seal it only once.")
    runs, reviewers, source_root = study(root)
    scrub = blind_scrub(root, runs, reviewers, source_root, root)
    panel.mkdir(parents=True, exist_ok=False)
    entries = {}
    for opaque, key in sorted(("blind-" + secrets.token_hex(12), key) for key in runs):
        visible, ground = packet(runs[key], scrub)
        write_json(panel / f"{opaque}.json", visible)
        write_json(panel / f"{opaque}.ground.json", ground)
        entries[opaque] = {"id": key, "sha256": json_digest(visible), "ground_sha256": json_digest(ground)}
    write_json(panel / "checksums.json", {
        key: {field: entry[field] for field in ("sha256", "ground_sha256")} for key, entry in entries.items()
    })
    write_json(root / MANIFEST, {
        "capture_root": str(root), "entries": entries, "schedule_sha256": SCHEDULE_SHA256,
        "trials_sha256": capture_digest(runs, reviewers),
        "launches_sha256": digest((root / LAUNCHES).read_bytes()),
    })
    return {"packets": len(entries), "reviewer_attempts": len(reviewers)}


def wall_seconds(start, end):
    seconds = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    if seconds < 0:
        raise ValueError("The review was issued after the solver started.")
    return seconds


def review_cost(run, reviewer):
    review_record = reviewer["record"] if reviewer is not None else None
    elapsed, gross, shell = 0, None, 0
    if not review_record:
        return elapsed, shell, gross
    record = run["record"]
    review_started = review_record["started"]["utc"]
    outcome = review_record["outcome"]
    if record and record["outcome"]:
        gross = wall_seconds(review_started, record["outcome"]["finished_utc"])
    if outcome:
        if record:
            wall_seconds(outcome["finished_utc"], record["started"]["utc"])
        elapsed = outcome["clock"]["elapsed_seconds"] - review_record["started"]["prior_seconds"]
    elif record:
        elapsed = wall_seconds(review_started, record["started"]["utc"])
    elif review_record["events"]:
        elapsed = review_record["events"][-1]["command_elapsed_seconds"] - review_record["started"]["prior_seconds"]
    shell = sum(event["seconds"] for event in review_record["events"])
    return round(elapsed, 6), round(shell, 6), gross


def trial_measures(run, reviewer, grade, visible):
    result = draft_proof.measures(grade, visible)
    reviewer_elapsed, reviewer_shell, gross = review_cost(run, reviewer)
    reviewer_actions = len(reviewer["operations"]) if reviewer is not None else 0
    solver_elapsed = result["elapsed_seconds_after_checkpoint"]
    lower_bound = result["last_recorded_action_seconds_after_checkpoint"] or 0
    spent = solver_elapsed if solver_elapsed is not None else lower_bound
    charged = round(spent + reviewer_elapsed, 6)
    budget = run["before_nudge"]["record"]["manifest"]["budget_seconds"]
    cutoff = run["before_nudge"]["record"]["outcome"]["clock"]["elapsed_seconds"]
    first = result["first_meaningful_seconds"]
    return {
        **result, "reviewer_actions": reviewer_actions, "reviewer_elapsed_seconds": reviewer_elapsed,
        "reviewer_shell_seconds": reviewer_shell, "review_start_to_solver_finish_seconds": gross,
        "charged_actions": result["post_checkpoint_actions"] + reviewer_actions,
        "charged_shell_seconds": round(result["shell_seconds"] + reviewer_shell, 6),
        "charged_elapsed_seconds": charged if solver_elapsed is not None else None,
        "charged_elapsed_lower_bound_seconds": charged,
        "charged_first_meaningful_seconds": round(first + reviewer_elapsed, 6) if first is not None else None,
        "remaining_at_checkpoint_seconds": round(budget - cutoff, 6),
        "combined_budget_exceeded": spent + reviewer_elapsed >= budget - cutoff,
    }


def arm_summary(records):
    summary = draft_proof.arm_summary(records)
    result = {
        **summary,
        "blind_delivered": summary["delivered"],
        "delivered": sum(record["verified_delivery"] for record in records),
        "command_validation_excluded": sum(record["command_validation_excluded"] for record in records),
        "reviewer_attempts": sum(record["reviewer"] is not None for record in records),
        "advice_issued": sum(record["advice_issued"] for record in records),
        "combined_budget_exceeded": sum(record["measures"]["combined_budget_exceeded"] for record in records),
    }
    for field in ("reviewer_actions", "reviewer_elapsed_seconds", "reviewer_shell_seconds",
                  "charged_actions", "charged_shell_seconds"):
        result[field] = round(sum(record["measures"][field] for record in records), 6)
    for field in ("first_meaningful_seconds", "charged_first_meaningful_seconds", "charged_elapsed_seconds"):
        samples = [record["measures"][field] for record in records if record["measures"][field] is not None]
        result["observed_" + field] = len(samples)
        result["median_" + field] = median(samples) if samples else None
    return result


def breakdown(grouped):
    return {name: {arm: arm_summary(rows) for arm, rows in arms.items()} for name, arms in grouped.items()}


def replay(root):
    runs, reviewers, source_root = study(root)
    manifest, grades = read_json(root / MANIFEST), read_json(root / GRADES)
    entries = manifest["entries"]
    if (manifest["schedule_sha256"] != SCHEDULE_SHA256
            or manifest["launches_sha256"] != digest((root / LAUNCHES).read_bytes())
            or manifest["trials_sha256"] != capture_digest(runs, reviewers)
            or len(entries) != len(runs) or {entry["id"] for entry in entries.values()} != set(runs)
            or set(entries) != set(grades) or any(not pressure_proof.OPAQUE.fullmatch(key) for key in entries)):
        raise ValueError("The sealed panel or blind grades differ from the scheduled checkpoints.")
    scrub = blind_scrub(root, runs, reviewers, source_root, Path(manifest["capture_root"]))
    records, pairs = {}, defaultdict(dict)
    by_model, by_source, by_gate = (defaultdict(lambda: defaultdict(list)) for _ in range(3))
    for opaque, entry in entries.items():
        key, grade = entry["id"], grades[opaque]
        run = runs[key]
        visible, ground = packet(run, scrub)
        if (entry["sha256"] != json_digest(visible) or grade["sha256"] != entry["sha256"]
                or entry["ground_sha256"] != json_digest(ground)):
            raise ValueError(f"The grade or panel no longer matches the checkpoint for {key}.")
        row = run["row"]
        reviewer = reviewers.get(row["reviewer"])
        measures = trial_measures(run, reviewer, grade, visible)
        review = run["overlay"]["review"]
        syntax = measures["command_syntax"]
        command_excluded = grade["delivered"] and (syntax is None or syntax["status"] != "parsed")
        result = {
            **row, "status": visible["status"], "grade": grade, "measures": measures,
            "alert_triggered": run["alert_triggered"],
            "advice_issued": bool(run["record"] and review and review["advice_sha256"]),
            "verified_delivery": grade["delivered"] and not command_excluded and not measures["combined_budget_exceeded"],
            "command_validation_excluded": command_excluded,
            "telemetry_oracle": pressure_proof.telemetry(run),
        }
        records[key] = result
        pairs[row["pair"]][row["arm"]] = key
        by_model[row["model"]][row["arm"]].append(result)
        by_source[row["source"]][row["arm"]].append(result)
        by_gate["triggered" if run["alert_triggered"] else "not-triggered"][row["arm"]].append(result)
    return {
        "schedule_sha256": SCHEDULE_SHA256, "pairs": dict(pairs), "trials": records,
        "arms": {arm: arm_summary([row for row in records.values() if row["arm"] == arm]) for arm in signal_run.ARMS},
        "by_model": breakdown(by_model), "by_source": breakdown(by_source), "by_gate": breakdown(by_gate),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    export = commands.add_parser("blind")
    export.add_argument("root", type=Path)
    export.add_argument("panel", type=Path)
    commands.add_parser("replay").add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        result = blind(root, args.panel.resolve()) if args.action == "blind" else replay(root)
    except (KeyError, OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
