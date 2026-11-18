"""Verify backlog trial evidence and export anonymous review packets."""

import argparse
import json
import math
import secrets
import tempfile
from datetime import datetime
from pathlib import Path

import backlog_run as runner
from long_run import workspace_tree
from proof import decode, json_digest, parse_trace, read_json, read_text
from trial import HERE, digest, write_json

LAUNCHES = "launches.json"
DISPATCH = "dispatch-template.txt"
WRITE_ACTIONS = ("resolve", "route", "merge", "submit")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite_seconds(number):
    return type(number) in (float, int) and math.isfinite(number) and number >= 0


def utc_time(text):
    timestamp = datetime.fromisoformat(text)
    require(timestamp.utcoffset() is not None and timestamp.utcoffset().total_seconds() == 0,
            "The recorded timestamp must be in UTC.")
    return timestamp


def command_bytes(event, field):
    text = event[field]
    data = decode(event[f"{field}_base64"]) if f"{field}_base64" in event else text.encode()
    require(data.decode(errors="replace") == text and digest(data) == event[f"{field}_sha256"],
            f"The recorded command {field} differs from its hash.")
    return data


def apply_changes(tree, event):
    for path, delta in event["changes"].items():
        relative = Path(path)
        require(not relative.is_absolute() and all(part != ".." for part in relative.parts)
                and relative.as_posix() == path and path not in ("", "."),
                f"Invalid changed workspace path {path!r}.")
        require(set(delta) == {"before", "after"} and tree.get(path) == delta["before"]
                and delta["before"] != delta["after"], f"Detached or unchanged action record for {path}.")
        if delta["after"] is None:
            tree.pop(path)
        else:
            tree[path] = delta["after"]


def trace_tree(initial, events, started):
    tree = dict(initial)
    prior = 0
    previous_utc = utc_time(started["utc"]) if started else None
    require(not events or started is not None, "Unstarted worker has command records.")
    for event in events:
        start, end, duration = (event[key] for key in ("start_seconds", "end_seconds", "seconds"))
        start_utc, end_utc = (utc_time(event[key]) for key in ("started_utc", "finished_utc"))
        require(all(finite_seconds(value) for value in (start, end, duration)) and prior <= start <= end
                and start < runner.BUDGET_SECONDS and math.isclose(end - start, duration, abs_tol=1e-6)
                and previous_utc <= start_utc <= end_utc, "The recorded action times are inconsistent.")
        require(type(event["exit"]) is int and type(event["timed_out"]) is bool
                and (not event["timed_out"] or event["exit"] == 124), "The recorded command exit is invalid.")
        require(digest(event["command"].encode()) == event["command_sha256"], "The recorded command hash changed.")
        for key in ("stdout", "stderr"):
            command_bytes(event, key)
        require(json_digest(tree) == event["before_workspace_sha256"], "Detached command starting workspace.")
        apply_changes(tree, event)
        require(json_digest(tree) == event["after_workspace_sha256"], "Detached command ending workspace.")
        prior, previous_utc = end, end_utc
    return tree


def journal_steps(directory, events):
    observed = read_json(directory / "initial" / runner.JOURNAL)
    steps = []
    intact = True
    for index, event in enumerate(events, 1):
        delta = event["changes"].get(runner.JOURNAL)
        encoded = event.get("journal_after_base64")
        if delta is None or not delta["after"] or "sha256" not in delta["after"]:
            require(encoded is None, "Unexpected journal bytes without a regular file change.")
            intact = intact and delta is None
            continue
        require(encoded is not None, "Missing operation journal after an observed file change.")
        data = decode(encoded)
        require(digest(data) == delta["after"]["sha256"] and len(data) == delta["after"]["bytes"],
                "Recorded operation bytes differ from the changed file.")
        try:
            updated = json.loads(data)
        except (UnicodeError, ValueError):
            intact = False
            continue
        if (not isinstance(updated, list) or updated[:len(observed)] != observed or
                not all(isinstance(entry, dict) and isinstance(entry.get("action"), str) for entry in updated)):
            intact = False
            continue
        steps.extend({**entry, "command_index": index, "seconds": event["end_seconds"]}
                     for entry in updated[len(observed):])
        observed = updated
    return steps, intact


def selectors(root, path, rows):
    launches_path = path if path is not None else root / LAUNCHES
    dispatch_path = root / DISPATCH
    launches = read_json(launches_path) if launches_path.is_file() else {}
    dispatch = read_text(dispatch_path) if dispatch_path.is_file() else None
    if path is not None:
        require(launches_path.is_file(), f"Missing launch registry {launches_path}.")
    if dispatch is not None:
        require(dispatch.count("{id}") == 1, "The common dispatch template needs one opaque identifier slot.")
    accepted = {row[arm] for row in rows for arm in runner.ARMS}
    require(set(launches) <= accepted, "Launch records contain out-of-allocation workers.")
    result = {}
    identities = set()
    for row in rows:
        for arm in runner.ARMS:
            ident = row[arm]
            expected = {"model": row["model"], "reasoning_effort": row.get("reasoning_effort", "high"),
                        "fork_turns": "none"}
            launch = launches.get(ident)
            if launch is None:
                result[ident] = {"status": "not-recorded", **expected}
                continue
            status, receipt = launch["status"], launch["receipt"]
            require(status in ("opened", "failed") and isinstance(receipt, dict)
                    and all(launch[key] == value for key, value in expected.items()), f"Conflicting launch for {ident}.")
            attested = [key for key in expected if key in receipt]
            require(all(receipt[key] == expected[key] for key in attested), f"Conflicting platform receipt for {ident}.")
            worker = receipt.get("task_name")
            if status == "opened":
                require(isinstance(worker, str) and worker.rsplit("/", 1)[-1] == ident,
                        f"Missing or different hosted worker for {ident}.")
            for field in ("task_name", "agent_id", "session_id", "thread_id"):
                value = receipt.get(field)
                if value is not None and status == "opened":
                    require(isinstance(value, str) and (field, value) not in identities,
                            f"Duplicate hosted worker identity for {ident}.")
                    identities.add((field, value))
            submitted_hash = launch.get("submitted_message_sha256")
            if status == "opened" or submitted_hash is not None:
                require(dispatch is not None and submitted_hash == digest(dispatch.replace("{id}", ident).encode()),
                        f"The launch message for {ident} differs from the common dispatch template.")
            nudges = launch.get("follow_up_nudges", [])
            require(isinstance(nudges, list), "Follow-up nudges must be logged as a list.")
            result[ident] = {
                **expected, "status": status, "attested_fields": attested, "worker": worker,
                "submitted_message_sha256": submitted_hash, "follow_up_nudges_observed": len(nudges),
            }
    return result


def production_files(directory, material, run, baseline):
    require(run["baseline_sha256"] == digest(baseline), "The trial differs from the pinned Codex baseline.")
    require(runner.hashes(HERE, runner.SOURCE_FILES) == run["source_sha256"], "Frozen study source changed.")
    require(runner.hashes(directory, runner.INPUT_FILES) == run["input_sha256"],
            "Recorded task, instruction or opening hashes changed.")
    require(all((directory / name).read_bytes() == data for name, data in material.items()),
            "Recorded opening differs from the allocated instruction or task.")


def read_terminal(directory, started, events, tree, case):
    import backlog_case

    end_path = directory / "end.json"
    if not end_path.exists():
        require(not (directory / "end").exists() and not (directory / "reply.txt").exists(),
                "The terminal snapshot is incomplete.")
        return {
            "status": "unfinished" if started else "prepared",
            "artifact": None, "workspace": directory / "work", "reply": None,
        }

    marker = read_json(end_path)
    workspace = directory / "end"
    observed = workspace_tree(workspace)
    require(started and observed == tree and marker["workspace_sha256"] == json_digest(observed),
            "The terminal workspace differs from the reconstructed action history.")
    require(marker["events_sha256"] == runner.path_hash(directory / "events.jsonl"), "The terminal trace hash changed.")
    elapsed = marker["elapsed_seconds"]
    previous = events[-1]["end_seconds"] if events else 0
    previous_utc = utc_time(events[-1]["finished_utc"]) if events else utc_time(started["utc"])
    require(finite_seconds(elapsed) and previous <= elapsed and previous_utc <= utc_time(marker["utc"])
            and elapsed == marker["monotonic"] - started["monotonic"]
            and marker["within_budget"] is (elapsed <= runner.BUDGET_SECONDS), "Invalid terminal clock.")
    reply_file = directory / "reply.txt"
    if marker["outcome"] == "submitted":
        require(marker["reply_sha256"] == runner.path_hash(reply_file), "The submitted reply hash changed.")
        reply = read_text(reply_file)
        status = "submitted" if marker["within_budget"] else "late"
    else:
        require(marker["outcome"] == "expired" and not marker["within_budget"]
                and marker["reply_sha256"] is None and not reply_file.exists(), "Invalid expired run state.")
        reply = None
        status = "expired"
    artifact = backlog_case.score(workspace, case)
    require(type(artifact.get("passed")) is bool and workspace_tree(workspace) == observed,
            "The fixture oracle failed to supply a read-only boolean verdict.")
    return {"status": status, "artifact": artifact, "workspace": workspace, "reply": reply,
            "elapsed_seconds": elapsed, "within_budget": marker["within_budget"]}


def reconstruct_fixture(case, expected):
    import backlog_case

    with tempfile.TemporaryDirectory(prefix="backlog-fixture-check-") as temp:
        directory = Path(temp)
        backlog_case.setup(directory, case)
        require(workspace_tree(directory) == expected, "The archived fixture differs from fresh setup.")


def read_run(directory, row, arm):
    run = read_json(directory / "run.json")
    required = {
        "case": row["case"], "arm": arm, "pin": runner.PIN, "budget_seconds": runner.BUDGET_SECONDS,
        "model": row["model"], "reasoning_effort": row.get("reasoning_effort", "high"), "fork_turns": "none",
    }
    require(all(run[key] == value for key, value in required.items()),
            f"Trial {directory.name} configuration differs from allocation.")
    origin = Path(run["original_directory"])
    require(origin.is_absolute() and origin.name == directory.name, "Invalid opening directory provenance.")
    baseline, material = runner.expected_material(row["case"], arm)
    production_files(directory, material, run, baseline)
    initial = read_json(directory / "initial-workspace.json")
    initial_hash = json_digest(initial)
    require(run["initial_workspace_sha256"] == initial_hash and workspace_tree(directory / "initial") == initial,
            "The first workspace snapshot changed.")
    reconstruct_fixture(row["case"], initial)
    started = read_json(directory / "started.json") if (directory / "started.json").exists() else None
    if started is not None:
        require(started["input_sha256"] == run["input_sha256"] and started["initial_workspace_sha256"] == initial_hash
                and started["opening_sha256"] == run["input_sha256"]["opening.txt"]
                and finite_seconds(started["monotonic"]), "The start receipt differs from the frozen opening.")
    events = parse_trace(read_text(directory / "events.jsonl"))
    tree = trace_tree(initial, events, started)
    require(workspace_tree(directory / "work") == tree, "Live files contain changes outside the recorded commands.")
    operations, append_only = journal_steps(directory, events)
    terminal = read_terminal(directory, started, events, tree, row["case"])
    terminal.pop("workspace")
    reply = terminal.pop("reply")
    changed = [i + 1 for i, event in enumerate(events) if event["changes"]]
    writes = [entry for entry in operations if entry["action"] in WRITE_ACTIONS]
    first_write = writes[0] if writes and append_only else None
    result = {
        "run_id": directory.name, **required, **terminal,
        "completion": terminal["status"] == "submitted" and terminal["artifact"]["passed"] and append_only,
        "action_count": len(events), "action_seconds": sum(event["seconds"] for event in events),
        "first_workspace_change_action": changed[0] if changed else None,
        "first_workspace_change_seconds": events[changed[0] - 1]["end_seconds"] if changed else None,
        "journal_append_only": append_only, "journal_entry_count": len(operations),
        "operation_counts": {action: sum(entry["action"] == action for entry in writes) for action in WRITE_ACTIONS},
        "first_durable_operation": first_write and {
            field: first_write.get(field) for field in ("action", "pr", "command_index", "seconds")
        },
        "initial_inputs": {
            **{key: run[key] for key in ("baseline_sha256", "initial_workspace_sha256", "source_sha256")},
            **{key: run["input_sha256"][key] for key in ("task.txt", "operator-update.txt")},
        },
    }
    details = {
        "user_task": material["task.txt"].decode(),
        "user_update": material["operator-update.txt"].decode() or None,
        "actions": events, "journal": operations, "reply": reply, "status": terminal["status"],
        "elapsed_seconds": terminal.get("elapsed_seconds"), "original_directory": str(origin), "end_tree": tree,
    }
    return result, details


def blind_packet(ident, details):
    packet = dict(details)
    origin = Path(packet.pop("original_directory"))

    def scrub(value):
        return value.replace(str(origin), "<trial>").replace(str(origin.parent), "<study>").replace(ident, "<trial>")

    packet["actions"] = [{
        **{field: event[field] for field in ("exit", "timed_out", "start_seconds", "end_seconds", "seconds", "changes")},
        **{field: scrub(event[field]) for field in ("command", "stdout", "stderr")},
    } for event in packet["actions"]]
    if packet["reply"] is not None:
        packet["reply"] = scrub(packet["reply"])
    packet["journal"] = [
        {field: scrub(value) if isinstance(value, str) else value for field, value in entry.items()}
        for entry in packet["journal"]
    ]
    return packet


def export_blind(destination, results):
    destination.mkdir(parents=True)
    order = list(results)
    secrets.SystemRandom().shuffle(order)
    key = {}
    for ident, details in order:
        label = secrets.token_hex(12)
        key[label] = ident
        write_json(destination / f"{label}.json", blind_packet(ident, details))
    write_json(destination.with_name(destination.name + ".key.json"), key)


def replay(root, receipt_path=None, blind=None):
    rows = runner.launch_rows(root)
    launches = selectors(root, receipt_path, rows)
    expected = set(launches)
    unexpected = [path.name for path in root.iterdir()
                  if path.is_dir() and (path / "run.json").exists() and path.name not in expected]
    require(not unexpected, f"Unexpected trial directories: {unexpected}.")
    pairs = []
    packets = []
    for row in rows:
        arms = {}
        for arm in runner.ARMS:
            ident = row[arm]
            directory = root / ident
            launch = launches[ident]
            if directory.exists():
                result, details = read_run(directory, row, arm)
                require(launch["status"] != "failed" or result["status"] == "prepared",
                        f"A failed hosted launch unexpectedly has a worker start for {ident}.")
                packets.append((ident, details))
            else:
                result = {"run_id": ident, "status": "missing", "completion": False}
            arms[arm] = {**result, "launch": launch}
        first, second = (arms[arm].get("initial_inputs") for arm in runner.ARMS)
        require(first is None or second is None or first == second, "A pair does not have matched opening inputs.")
        pairs.append({"case": row["case"], "model": row["model"], "cohort": row.get("cohort"),
                      "launch_order": row["order"], "matched_inputs": first is not None and second is not None, **arms})
    if blind is not None:
        export_blind(blind, packets)
    return {
        "pin": runner.PIN, "budget_seconds": runner.BUDGET_SECONDS, "allocated_workers": len(expected),
        "limits": [
            "Replay reconstructs workspace changes, validates the operation journal by command, and reruns the fixture oracle without executing archived shell text.",
            "Platform receipts attest served selector fields only when present. Other selector values are the requested launch configuration.",
            "The evidence records workspace changes and durable operations separately from blind judgments of consequence, verification and whether a nudge was needed.",
            "The source-informed queue and its operations are isolated fixture behavior.",
        ],
        "pairs": pairs,
    }


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--selectors", type=Path)
    parser.add_argument("--blind", type=Path)
    args = parser.parse_args(arguments)
    try:
        result = replay(args.root.resolve(), args.selectors, args.blind)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
