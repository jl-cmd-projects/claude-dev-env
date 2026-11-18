"""Freeze blinded portable-handoff evidence and replay the matched comparisons."""

import argparse
import json
import secrets
import subprocess
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path
from statistics import median

import dispatch_prepare
import draft_proof
import draft_run
import pressure_proof
import pressure_run
from proof import directory_name, json_digest, parse_trace, pinned_baseline, read_json, read_text
from trial import HERE, digest, write_json


SCHEDULE = HERE / "dispatch_schedule.json"
SCHEDULE_SHA256 = "1aa1dcafb9c46ca6aa5db8521f15cdbfe113f4155aec7d7872909be3a34b909e"
CANDIDATE = HERE / "dispatch_candidate.txt"
PRESSURE_SOURCES = HERE / "signal_schedule.json"
PRESSURE_SOURCES_SHA256 = "db1745e9fa581d141e8260eb64ae875401698d005b41c73a7f392ad82b8394c7"
MANIFEST = "dispatch_blind_manifest.json"
LAUNCHES = "launches.json"
GRADES = "grades.json"
ARMS = ("baseline", "candidate")


def checked_schedule(suite):
    if digest(SCHEDULE.read_bytes()) != SCHEDULE_SHA256:
        raise ValueError("The allocation differs from the frozen schedule.")
    schedule = read_json(SCHEDULE)
    if digest(CANDIDATE.read_bytes()) != schedule["candidate_sha256"]:
        raise ValueError("The candidate differs from the frozen instruction.")
    rows = schedule["development" if suite == "pressure" else "holdout"]
    suite_label = "pressure" if suite == "pressure" else "independent"
    planned = 8 if suite == "pressure" else 12
    groups = defaultdict(list)
    for row in rows:
        groups[row["pair"]].append(row)
    if (len(rows) != planned or len({row["id"] for row in rows}) != planned
            or len(groups) != planned // 2 or any(row["suite"] != suite_label for row in rows)):
        raise ValueError("The schedule does not cover every allocation once.")
    for pair in groups.values():
        fields = ("case", "model", "reasoning_effort")
        if {row["arm"] for row in pair} != set(ARMS) or len({tuple(row[field] for field in fields) for row in pair}) != 1:
            raise ValueError("The allocation has an unmatched pair.")
    return schedule, rows


def verify_launches(rows, launches):
    if set(launches) != {row["id"] for row in rows}:
        raise ValueError("Launch evidence must cover every scheduled trial once.")
    sessions = {field: set() for field in ("task_name", "agent_id", "session_id")}
    for row in rows:
        key = row["id"]
        launch = launches[key]
        receipt = launch["receipt"]
        status = launch.get("status", "opened")
        fields = ("model", "reasoning_effort", "fork_turns")
        if (any(launch[field] != row[field] for field in fields[:2]) or launch["fork_turns"] != "none"
                or status not in ("opened", "failed") or not isinstance(receipt, dict) or not receipt
                or any(field in receipt and receipt[field] != launch[field] for field in fields)
                or (status == "opened" and receipt.get("task_name") != "/root/" + key)):
            raise ValueError(f"The launch receipt disagrees with the frozen allocation for {key}.")
        if status == "opened":
            for field, identifiers in sessions.items():
                value = receipt.get(field)
                if value:
                    if value in identifiers:
                        raise ValueError(f"The worker receipt reuses {field} for {key}.")
                    identifiers.add(value)


def pressure_sources():
    if digest(PRESSURE_SOURCES.read_bytes()) != PRESSURE_SOURCES_SHA256:
        raise ValueError("The historical pressure source list differs from the freeze.")
    source_schedule = read_json(PRESSURE_SOURCES)
    return draft_proof.frozen_sources({**source_schedule, "rows": []})


def pressure_trial(directory, row, launch, pin, sources):
    prefix = directory / "prefix"
    for name, expected in sources[row["case"]].items():
        if digest((prefix / name).read_bytes()) != expected:
            raise ValueError(f"The copied pressure source differs from the frozen archive for {row['id']}/{name}.")
    original = pressure_run.replay(prefix)
    entry, instructions = dispatch_prepare.pressure_presentation(prefix, row["arm"])
    overlay = {"arm": row["arm"], "source": row["case"], "source_pin": pin,
               "presentation_sha256": digest(entry), "presented_instructions_sha256": digest(instructions),
               "runner_sha256": digest(Path(draft_run.__file__).read_bytes())}
    if read_json(directory / "overlay.json") != overlay or (directory / "presentation.md").read_bytes() != entry:
        raise ValueError(f"The presented pressure instructions differ from the frozen inputs for {row['id']}.")
    manifest = read_json(directory / "run.json")
    pressure_run.verify_inputs(directory, manifest)
    if "recovery" not in manifest:
        raise ValueError(f"The trial does not resume the archived pressure checkpoint for {row['id']}.")
    _, starting_tree, _ = pressure_run.entry_state(directory, manifest)
    record, operations = None, []
    issued = directory / "issued.json"
    if (directory / "started.json").exists():
        record = pressure_run.replay(directory)
        if launch.get("status", "opened") != "opened" or read_json(issued) != {
            "presentation_sha256": overlay["presentation_sha256"], "started_utc": record["started"]["utc"],
        }:
            raise ValueError(f"The issued pressure presentation disagrees with its launch for {row['id']}.")
        operations = pressure_proof.operation_groups(directory, record)
    elif (any((directory / name).exists() for name in ("issued.json", "end.json", "reply.txt"))
          or any((directory / name).stat().st_size for name in ("events.jsonl", pressure_run.RECEIPTS))
          or pressure_run.tree_digest(directory / "work") != starting_tree):
        raise ValueError(f"Pressure trial evidence exists without a start for {row['id']}.")
    return {
        "row": {**row, "case": original["manifest"]["case"], "source": row["case"]},
        "directory": directory, "launch": launch, "record": record, "operations": operations,
        "before_nudge": {"directory": prefix, "record": original,
                         "operations": pressure_proof.operation_groups(prefix, original)},
        "pair_inputs": (manifest["match_key"], digest(entry[len(instructions):])),
        "source_checks": {"archive_checkpoint_sha256": original["outcome"]["workspace_sha256"],
                          "match_key": manifest["match_key"], "issued": bool(record), **overlay},
    }


def ci_source(runner, case, baseline):
    with tempfile.TemporaryDirectory(prefix="ci-queue-verify-") as scratch:
        tree = Path(scratch) / "checkout"
        handoff = runner.stage(tree, case)
        files = {"baseline.md": baseline, "task.txt": runner.TASK.encode(),
                 "handoff.txt": handoff.encode(), "draft.txt": runner.DRAFTS[case].encode()}
        shared = {"case": case, "pin": runner.PIN, "budget_seconds": runner.BUDGET_SECONDS,
                  "command_seconds": runner.COMMAND_SECONDS, "runner_sha256": digest(Path(runner.__file__).read_bytes()),
                  "workspace_sha256": json_digest(runner.tree(tree)), "starting_head": runner.git(tree, "rev-parse", "HEAD"),
                  "inputs": {name: digest(data) for name, data in files.items()}}
    return shared, files


def ci_trace(directory, started, budget):
    events = parse_trace(read_text(directory / "events.jsonl"))
    end_path, reply_path = directory / "end.json", directory / "reply.txt"
    end = read_json(end_path) if end_path.exists() else None
    if not started and (end or events or reply_path.exists()):
        raise ValueError(f"CI trial evidence exists without a start for {directory.name}.")
    if end:
        terminal = {name: value for name, value in end.items() if name != "events_sha256"}
        elapsed = end["elapsed_seconds"]
        if (not events or events.pop() != terminal or end["action"] not in ("finish", "send-draft", "expired")
                or end["within_budget"] != (0 <= elapsed <= budget) or elapsed < 0
                or (end["action"] == "expired" and elapsed < budget)):
            raise ValueError(f"The CI terminal event disagrees with its receipt for {directory.name}.")
        if end["action"] == "send-draft" and reply_path.read_bytes() != (directory / "draft.txt").read_bytes():
            raise ValueError(f"The queued reply was changed for {directory.name}.")
    elif reply_path.exists():
        raise ValueError(f"The CI reply has no terminal receipt for {directory.name}.")
    last = 0
    for event in events:
        begin, stop = event["start_elapsed_seconds"], event["end_elapsed_seconds"]
        if (event["action"] != "sh" or not last <= begin <= stop or begin >= budget
                or (end and stop > end["elapsed_seconds"])):
            raise ValueError(f"The CI action is outside the recorded timing for {directory.name}.")
        last = stop
    return events, end


def ci_trial(runner, directory, row, launch, source):
    shared, files = source
    extra = CANDIDATE.read_bytes().strip() if row["arm"] == "candidate" else None
    instructions = pressure_run.instructions_for(files["baseline.md"], extra)
    expected = {**shared, "match_key": json_digest(shared), "arm": row["arm"],
                "instructions_sha256": digest(instructions), "intervention_sha256": digest(extra) if extra else None}
    path = directory / "intervention.txt"
    manifest = read_json(directory / "run.json")
    initial, work = directory / "initial", directory / "work"
    if (manifest != expected or any((directory / name).read_bytes() != data for name, data in files.items())
            or (directory / "instructions.md").read_bytes() != instructions
            or (path.read_bytes() if path.exists() else None) != extra
            or json_digest(runner.tree(initial)) != shared["workspace_sha256"]
            or runner.git(initial, "rev-parse", "HEAD") != shared["starting_head"]):
        raise ValueError(f"The captured CI inputs differ from the regenerated fixture for {row['id']}.")
    presented = b"\n\n".join((instructions, files["task.txt"], files["handoff.txt"], b""))
    started_path = directory / "started.json"
    started = read_json(started_path) if started_path.exists() else None
    if started and (launch.get("status", "opened") != "opened" or started["presentation_sha256"] != digest(presented)
                    or started["manifest_sha256"] != digest((directory / "run.json").read_bytes())):
        raise ValueError(f"The issued CI presentation disagrees with its launch for {row['id']}.")
    events, end = ci_trace(directory, started, shared["budget_seconds"])
    expected_tree = end["workspace_sha256"] if end else shared["workspace_sha256"] if not events else None
    if not work.is_dir() or (expected_tree and json_digest(runner.tree(work)) != expected_tree):
        raise ValueError(f"The CI working copy differs from its recorded state for {row['id']}.")
    if end and runner.git(work, "rev-parse", "HEAD") != runner.git(directory / "end", "rev-parse", "HEAD"):
        raise ValueError(f"The CI checkout moved after the terminal receipt for {row['id']}.")
    return {
        "row": row, "directory": directory, "launch": launch, "started": started, "events": events, "end": end,
        "oracle": runner.grade(directory) if end else None, "pair_inputs": manifest["match_key"],
        "source_checks": {**shared, "instructions_sha256": expected["instructions_sha256"],
                          "presentation_sha256": digest(presented), "issued": bool(started)},
    }


def study(suite, root):
    schedule, rows = checked_schedule(suite)
    launches = read_json(root / LAUNCHES)
    verify_launches(rows, launches)
    baseline = pinned_baseline(schedule["pin"]).encode()
    source_root, runs, pair_inputs = None, {}, {}
    if suite == "pressure":
        sources, source_root = pressure_sources()
    else:
        import handoff_holdout

        if handoff_holdout.PIN != schedule["pin"]:
            raise ValueError("The CI runner baseline differs from the frozen pin.")
        sources = {case: ci_source(handoff_holdout, case, baseline) for case in sorted({row["case"] for row in rows})}
    for row in rows:
        key = directory_name(row["id"])
        directory, launch = root / key, launches[key]
        if suite == "pressure":
            run = pressure_trial(directory, row, launch, schedule["pin"], sources)
        else:
            run = ci_trial(handoff_holdout, directory, row, launch, sources[row["case"]])
        if pair_inputs.setdefault(row["pair"], run["pair_inputs"]) != run["pair_inputs"]:
            raise ValueError(f"The checkpoint pair has different starting inputs for {key}.")
        runs[key] = run
    return schedule, runs, source_root


def blind_scrubber(suite, root, runs, source_root, capture_root, pin):
    if suite == "pressure":
        base = draft_proof.blind_scrubber(root, runs, source_root, capture_root)
    else:
        base = pressure_proof.scrubber(root, runs)
    masks = {CANDIDATE.read_text().strip(): "<masked instructions>",
             pinned_baseline(pin).strip(): "<masked instructions>"}
    for location in {capture_root, root}:
        masks[str(location)] = "<run-root>"
        for key in runs:
            directory = location / key
            for name in ("work", "initial", "end"):
                masks[str(directory / name)] = "<workspace>"
            masks[str(directory)] = "<run>"
    replacements = sorted(masks.items(), key=lambda item: -len(item[0]))

    def redact(value):
        if isinstance(value, str):
            for before, after in replacements:
                value = value.replace(before, after)
        elif isinstance(value, dict):
            value = {key: redact(item) for key, item in value.items()}
        elif isinstance(value, list):
            value = [redact(item) for item in value]
        return value

    return lambda value: base(redact(value))


def packet(suite, run, scrub):
    if suite == "pressure":
        visible, ground = draft_proof.packet(run, scrub)
    else:
        visible, ground = ci_packet(run, scrub)
    if run["launch"].get("status") == "failed":
        visible["status"] = "launch-failed"
    return visible, ground


def ci_packet(run, scrub):
    directory, end = run["directory"], run["end"]
    draft = read_text(directory / "draft.txt")
    history = read_text(directory / "handoff.txt").removesuffix(draft).removesuffix("Pending reply (unsent)\n\n").strip()
    actions = []
    for index, event in enumerate(run["events"], 1):
        fields = ("command", "start_elapsed_seconds", "end_elapsed_seconds", "exit", "stdout", "stderr", "timed_out")
        actions.append({"action": index, **{field: event[field] for field in fields},
                        "seconds": event["end_elapsed_seconds"] - event["start_elapsed_seconds"]})
    status = "terminal-record-missing" if run["started"] else "workspace-not-started"
    if end:
        status = "finished" if end["within_budget"] else "budget-expired"
    visible = {"task": read_text(directory / "task.txt"), "prior_console_history": history,
               "pre_dispatch_draft": draft, "post_checkpoint_actions": actions,
               "submitted_reply": run["oracle"]["reply"] if end else None, "status": status,
               "elapsed_seconds_after_checkpoint": end["elapsed_seconds"] if end else None,
               "last_recorded_action_seconds_after_checkpoint": actions[-1]["end_elapsed_seconds"] if actions else None}
    independent_fields = ("checkout_preserved", "command_replay", "runnable_handback", "verdict_facts",
                          "expected_verdict", "observed_verdict_signals", "first_check_seconds", "finish_action")
    ground = {field: run["oracle"][field] for field in independent_fields} if end else {}
    ground["limits"] = ("The command replay recognizes direct checkout-query invocations. The prose checks use patterns "
                        "and provide clues for the judge. Scope and substantive verdict require independent reading.")
    return scrub(visible), scrub(ground)


def ci_measures(grade, visible, ground):
    actions, answer = visible["post_checkpoint_actions"], visible["submitted_reply"]

    def valid(index):
        return type(index) is int and 1 <= index <= len(actions)

    def seconds(indices):
        return round(sum(actions[index - 1]["seconds"] for index in indices), 6)

    for field in draft_proof.BOOL_FIELDS:
        if type(grade[field]) is not bool:
            raise ValueError(f"The blind CI grade requires a boolean {field}.")
    for field in draft_proof.ACTION_LISTS:
        indices = grade[field] if field == "side_actions" else grade.get(field, [])
        if not isinstance(indices, list) or any(not valid(index) for index in indices) or len(indices) != len(set(indices)):
            raise ValueError(f"The blind CI grade has invalid indices for {field}.")
    first = grade.get("meaningful_action")
    if first is not None and not valid(first) and not (first == "answer" and answer):
        raise ValueError("The first meaningful action is missing from the CI trace.")
    if (not isinstance(grade["basis"], str) or not grade["basis"].strip()
            or (grade["sustained_detour"] and len(grade["side_actions"]) < 2)
            or (grade["delivered"] and (visible["status"] != "finished" or not answer or grade["nudge_needed"]
                                       or grade["missed_dependency"] or not ground["checkout_preserved"]))):
        raise ValueError("The blind CI grade disagrees with the recorded outcome.")
    elapsed = visible["elapsed_seconds_after_checkpoint"]
    return {"post_checkpoint_actions": len(actions), "shell_seconds": seconds(range(1, len(actions) + 1)),
            "elapsed_seconds_after_checkpoint": elapsed,
            "last_recorded_action_seconds_after_checkpoint": visible["last_recorded_action_seconds_after_checkpoint"],
            "side_shell_seconds": seconds(grade["side_actions"]),
            "repeated_shell_seconds": seconds(grade.get("repeated_actions", [])),
            "first_meaningful_seconds": actions[first - 1]["end_elapsed_seconds"] if valid(first)
            else elapsed if first == "answer" else None}


def panel_checksums(entries):
    return {key: {name: entry[name] for name in ("sha256", "ground_sha256")} for key, entry in entries.items()}


def blind(suite, root, panel):
    if panel.is_relative_to(root) or (root / MANIFEST).exists():
        raise ValueError("Freeze one panel outside the study root.")
    schedule, runs, source_root = study(suite, root)
    scrub = blind_scrubber(suite, root, runs, source_root, root, schedule["pin"])
    panel.mkdir(parents=True, exist_ok=False)
    entries = {}
    for opaque, key in sorted(("blind-" + secrets.token_hex(12), key) for key in runs):
        visible, ground = packet(suite, runs[key], scrub)
        write_json(panel / f"{opaque}.json", visible)
        write_json(panel / f"{opaque}.ground.json", ground)
        entries[opaque] = {"id": key, "sha256": json_digest(visible), "ground_sha256": json_digest(ground)}
    checksums = panel_checksums(entries)
    panel_digest = json_digest(checksums)
    write_json(panel / "checksums.json", checksums)
    write_json(root / MANIFEST, {"suite": suite, "schedule_sha256": SCHEDULE_SHA256,
                                 "launches_sha256": digest((root / LAUNCHES).read_bytes()),
                                 "capture_root": str(root), "panel_sha256": panel_digest, "entries": entries})
    return {"packets": len(entries), "panel_sha256": panel_digest}


def arm_summary(rows):
    def timings(field):
        return [row["measures"][field] for row in rows if row["measures"][field] is not None]

    times = timings("elapsed_seconds_after_checkpoint")
    first = timings("first_meaningful_seconds")
    judgment_fields = dict.fromkeys(draft_proof.BOOL_FIELDS, 0)
    for row in rows:
        for field in judgment_fields:
            judgment_fields[field] += row["grade"][field]
    return {
        "planned": len(rows), "observed_terminal_times": len(times),
        "median_elapsed_seconds_after_checkpoint": median(times) if times else None,
        "observed_first_meaningful_times": len(first),
        "median_first_meaningful_seconds": median(first) if first else None,
        "judgments": {**judgment_fields, "side_actions": sum(len(row["grade"]["side_actions"]) for row in rows),
                      "repeated_actions": sum(len(row["grade"].get("repeated_actions", [])) for row in rows)},
        "post_checkpoint_actions": sum(row["measures"]["post_checkpoint_actions"] for row in rows),
        "side_shell_seconds": round(sum(row["measures"]["side_shell_seconds"] for row in rows), 6),
    }


def replay(suite, root, panel=None):
    schedule, runs, source_root = study(suite, root)
    manifest, grades = read_json(root / MANIFEST), read_json(root / GRADES)
    entries = manifest["entries"]
    checksums = panel_checksums(entries)
    if (manifest["suite"] != suite or manifest["schedule_sha256"] != SCHEDULE_SHA256
            or manifest["launches_sha256"] != digest((root / LAUNCHES).read_bytes())
            or manifest["panel_sha256"] != json_digest(checksums)
            or len(entries) != len(runs) or {entry["id"] for entry in entries.values()} != set(runs)
            or set(entries) != set(grades) or any(not pressure_proof.OPAQUE.fullmatch(opaque) for opaque in entries)
            or (panel is not None and read_json(panel / "checksums.json") != checksums)):
        raise ValueError("The sealed panel or grades differ from the frozen launches.")
    scrub = blind_scrubber(suite, root, runs, source_root, Path(manifest["capture_root"]), schedule["pin"])
    trials, pairs, models = {}, defaultdict(dict), defaultdict(lambda: defaultdict(list))
    for opaque, entry in entries.items():
        key, grade = entry["id"], grades[opaque]
        run, row = runs[key], runs[key]["row"]
        visible, ground = packet(suite, run, scrub)
        if (entry["sha256"] != json_digest(visible) or entry["ground_sha256"] != json_digest(ground)
                or grade["sha256"] != entry["sha256"] or (panel is not None and (
                    read_json(panel / f"{opaque}.json") != visible
                    or read_json(panel / f"{opaque}.ground.json") != ground))):
            raise ValueError(f"The blind grade or exported evidence differs from the captured trial for {key}.")
        if suite == "pressure":
            measures = draft_proof.measures(grade, visible)
            oracle = {"command_syntax": measures.pop("command_syntax"), "telemetry": pressure_proof.telemetry(run),
                      "workspace_sha256": run["record"]["outcome"]["workspace_sha256"]
                      if run["record"] and run["record"]["outcome"] else None}
        else:
            measures = ci_measures(grade, visible, ground)
            oracle = ground
        receipt = run["launch"]["receipt"]
        launch_checks = {"status": run["launch"].get("status", "opened"),
                         "task_name": receipt.get("task_name"), "receipt_model_attested": "model" in receipt,
                         "receipt_effort_attested": "reasoning_effort" in receipt}
        trials[key] = {**row, "status": visible["status"], "grade": grade, "measures": measures,
                       "launch_checks": launch_checks, "source_checks": run["source_checks"], "end_state_oracle": oracle}
        pairs[row["pair"]][row["arm"]] = key
        models[row["model"]][row["arm"]].append(trials[key])
    return {"suite": suite, "schedule_sha256": SCHEDULE_SHA256, "panel_sha256": manifest["panel_sha256"],
            "pin": schedule["pin"], "candidate_sha256": schedule["candidate_sha256"],
            "pairs": dict(pairs), "trials": trials,
            "arms": {arm: arm_summary([row for row in trials.values() if row["arm"] == arm]) for arm in ARMS},
            "by_model": {model: {arm: arm_summary(group) for arm, group in arms.items()} for model, arms in models.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("blind", "replay"))
    parser.add_argument("suite", choices=("pressure", "ci"))
    parser.add_argument("root", type=Path)
    parser.add_argument("panel", type=Path, nargs="?")
    args = parser.parse_args()
    root = args.root.resolve()
    panel = args.panel.resolve() if args.panel else None
    if args.command == "blind" and panel is None:
        parser.error("blind requires a panel directory")
    try:
        result = blind(args.suite, root, panel) if args.command == "blind" else replay(args.suite, root, panel)
    except (KeyError, OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
