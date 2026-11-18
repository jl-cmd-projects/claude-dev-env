"""Replay recorded opening actions up to, and excluding, a proposed shell call."""

import argparse
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import design_slice_run
import pivot_run
from long_run import run_command, run_lock, utc_now, workspace_tree
from proof import json_digest, parse_trace, pinned_baseline, read_json
from trial import HERE, digest, write_json


PIN = pivot_run.PIN
BUDGET_SECONDS = pivot_run.BUDGET_SECONDS
CONDITIONS = ("unchanged", "instruction", "review")
INPUT_FILES = ("instructions.md", "task.txt", "operator-update.txt", "history.json", "pending.txt",
               "checkpoint-workspace.json", "review-input.json")
REVIEW_FILES = ("review-request.txt", "review-receipt.json", "review-route.json")
REVIEW_ROLE = (
    "Read the original user request, observed actions and outputs, proposed next command, and visible checkout. "
    "Determine whether the proposed command advances what remains owed or resolves a necessary dependency. "
    "Allow useful verification, completed work, and appropriate escalation of blockers. "
    "If the next action should change, give one short recommendation grounded in the observed evidence. "
    "Otherwise return PASS.\n"
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def artifact_grade(directory, case):
    with patch.object(pivot_run, "module", design_slice_run.fixture):
        return pivot_run.artifact_grade(directory, case)


def source_cutoff(source, action, events_path):
    trace = source / "events.jsonl"
    source_manifest = read_json(source / "run.json")
    prefix = parse_trace(trace.read_text(encoding="utf-8"))
    source_files = tuple(source / name for name in (*pivot_run.INPUT_FILES, "run.json", "events.jsonl"))
    pivot_run.verify_inputs(source, source_manifest)
    if events_path is None:
        require(2 <= action <= len(prefix), "A pending action and its recorded predecessors are required.")
        observed, pending = prefix[:action - 1], prefix[action - 1]
        require(pending["action"] == action, "The pending source action is out of sequence.")
        events_path = trace
    else:
        branch = events_path.parent
        matches = ("run.json", "events.jsonl", "checkpoint.json", "started.json")
        source_files += tuple(source / name for name in ("checkpoint.json", "started.json", "checkpoint-workspace.json"))
        source_files += tuple(branch / ("prefix-" + name) for name in matches)
        source_files += tuple(branch / name for name in (*pivot_run.INPUT_FILES, "run.json", "checkpoint-workspace.json"))
        source_files += (events_path,)
        for name in matches:
            require((source / name).read_bytes() == (branch / ("prefix-" + name)).read_bytes(),
                    f"Continuation has a different archived prefix: {name}")
        for name in (*pivot_run.INPUT_FILES, "checkpoint-workspace.json"):
            require((source / name).read_bytes() == (branch / name).read_bytes(),
                    f"Continuation has a different opening input: {name}")
        branch_manifest = read_json(branch / "run.json")
        frozen = read_json(source / "checkpoint.json")
        require(branch_manifest["phase"] == "continuation"
                and branch_manifest["prefix_checkpoint_sha256"] == digest((source / "checkpoint.json").read_bytes())
                and frozen["trace_sha256"] == digest(trace.read_bytes())
                and frozen["action_count"] == len(prefix)
                and action == len(prefix) + 1,
                "The proposed command must be the first at the frozen continuation boundary.")
        observed = prefix
        pending, *_ = parse_trace(events_path.read_text(encoding="utf-8"))
        require(pending["action"] == 1 and pending["before_sha256"] == frozen["workspace_sha256"],
                "Continuation did not open on the recorded checkpoint.")
    require(source_manifest["pin"] == PIN and source_manifest["phase"] == "prefix"
            and (source / "instructions.md").read_bytes() == pinned_baseline(PIN).encode()
            and not (source / "operator-update.txt").read_bytes(),
            "Use an unchanged task and the pinned Codex instructions.")
    previous = json_digest(read_json(source / "initial-workspace.json"))
    for index, event in enumerate(observed, 1):
        require(event["before_sha256"] == previous and event["action"] == index,
                "The archived prefix does not have a continuous workspace history.")
        previous = event["after_sha256"]
    require(pending["before_sha256"] == previous, "The proposed action starts on a different workspace.")
    return source_manifest, observed, pending, {
        "prefix_run": source.name, "pending_run": events_path.parent.name,
        "pending_action": action, "pending_event_action": pending["action"],
        "observed_finished_utc": observed[-1]["finished_utc"], "observed_clock": observed[-1]["clock"],
        "source_sha256": {f"{path.parent.name}/{path.name}": digest(path.read_bytes()) for path in source_files},
    }


def opening_tree(source, destination, case, observed, expected, workspace):
    if workspace is None and all(not event["changes"] and event["before_sha256"] == event["after_sha256"]
                                 for event in observed):
        destination.mkdir()
        design_slice_run.fixture(case).prepare(destination, case)
        tree = workspace_tree(destination)
        require(json_digest(tree) == expected, "The reconstructed fixture differs from the trace opening.")
        for event in observed:
            code, _, _, timed_out = run_command(destination, event["command"], 10)
            require(not timed_out and code == event["exit"] and workspace_tree(destination) == tree,
                    f"Archived read action {event['action']} changed the reconstructed fixture or exit status.")
        return tree, "read-replay"
    archived = workspace or source / "work"
    shutil.copytree(archived, destination, symlinks=True)
    tree = workspace_tree(destination)
    require(json_digest(tree) == expected, "Archived pre-command checkout differs from the recorded opening tree.")
    return tree, "archived-workspace"


def freeze(source, action, directory, events_path=None, workspace=None):
    manifest, observed, pending, provenance = source_cutoff(source, action, events_path)
    case = manifest["case"]
    directory.mkdir(parents=True, exist_ok=False)
    try:
        tree, restore = opening_tree(source, directory / "work", case, observed, pending["before_sha256"], workspace)
        for name in ("instructions.md", "task.txt", "operator-update.txt"):
            shutil.copyfile(source / name, directory / name)
        visible = [{key: event[key] for key in ("action", "command", "exit", "stdout", "stderr", "changes")}
                   for event in observed]
        write_json(directory / "history.json", visible)
        (directory / "pending.txt").write_text(pending["command"], encoding="utf-8")
        write_json(directory / "checkpoint-workspace.json", tree)
        snapshot = pivot_run.review_input(directory, observed, tree, None)
        snapshot.pop("pending_reply")
        snapshot.update(observed_actions=visible, proposed_command=pending["command"],
                        opening_workspace_sha256=pending["before_sha256"])
        write_json(directory / "review-input.json", snapshot)
        write_json(directory / "checkpoint.json", {
            "case": case, "pin": PIN, "budget_seconds": BUDGET_SECONDS,
            "workspace_sha256": pending["before_sha256"], "source": {**provenance, "restore": restore},
            "input_sha256": pivot_run.hash_files(directory, INPUT_FILES),
        })
    except BaseException:
        shutil.rmtree(directory)
        raise


def verify_checkpoint(directory):
    checkpoint = read_json(checkpoint_file(directory))
    tree = workspace_tree(directory / "work")
    require(checkpoint["input_sha256"] == pivot_run.hash_files(directory, INPUT_FILES)
            and tree == read_json(directory / "checkpoint-workspace.json")
            and json_digest(tree) == checkpoint["workspace_sha256"],
            "The frozen input files or opening checkout changed.")
    return checkpoint


def checkpoint_file(directory):
    prefix = directory / "prefix-checkpoint.json"
    return prefix if prefix.is_file() else directory / "checkpoint.json"


def reviewer_request(checkpoint):
    return REVIEW_ROLE.encode() + b"\n" + (checkpoint / "review-input.json").read_bytes()


def prepare_reviewer(checkpoint, reviewer):
    verify_checkpoint(checkpoint)
    request = reviewer_request(checkpoint)
    reviewer.mkdir(parents=True, exist_ok=False)
    (reviewer / "request.txt").write_bytes(request)
    write_json(reviewer / "issued.json", {
        "session": reviewer.name, "monotonic": time.monotonic(), "utc": utc_now(),
        "checkpoint_sha256": digest(checkpoint_file(checkpoint).read_bytes()),
        "request_sha256": digest(request),
    })


def review_details(checkpoint, request, receipt, route):
    expected = reviewer_request(checkpoint)
    require(request == expected and route.get("request_sha256") == digest(expected)
            and receipt.get("request_sha256") == digest(expected)
            and route.get("checkpoint_sha256") == digest(checkpoint_file(checkpoint).read_bytes())
            and isinstance(route.get("session"), str) and route["session"] == receipt.get("session"),
            "Advice lacks a matching request and checkpoint digest.")
    issued, started, duration = route.get("monotonic"), route.get("review_started_monotonic"), receipt.get("elapsed_seconds")
    require(all(type(value) in (int, float) and math.isfinite(value) and value >= 0
                for value in (issued, started, duration)) and started >= issued
            and math.isfinite(started - issued + duration), "Invalid review timing.")
    advice = receipt.get("advice")
    require(isinstance(advice, str), "The review receipt has no advice response.")
    return design_slice_run.review_advice(advice), duration


def instructions_for(source, instruction):
    if instruction is None:
        return source
    anchor = b"\n# Personality\n"
    paragraph = instruction.strip()
    require(source.count(anchor) == 1 and paragraph and b"\n" not in paragraph,
            "Expected one intervention paragraph and one insertion point.")
    return source.replace(anchor, b"\n" + paragraph + b"\n" + anchor)


def opening_text(directory, advice):
    sections = [(directory / "effective-instructions.md").read_bytes(),
                b"[Original user request]\n" + (directory / "task.txt").read_bytes(),
                b"[Observed shell history]\n" + (directory / "history.json").read_bytes(),
                b"[Proposed next shell command, not yet run]\n" + (directory / "pending.txt").read_bytes()]
    if advice:
        sections.append(b"[Independent review]\n" + advice.encode())
    return b"\n\n".join(sections) + b"\n"


def opening_hashes(directory):
    names = ("effective-instructions.md", "opening.txt", "prefix-checkpoint.json",
             *(name for name in ("instruction.txt", *REVIEW_FILES) if (directory / name).exists()))
    return pivot_run.hash_files(directory, names)


def prepare(checkpoint, directory, condition, reviewer=None):
    frozen = verify_checkpoint(checkpoint)
    require(condition in CONDITIONS and (condition == "review") == (reviewer is not None),
            "A reviewer receipt is required only for the review condition.")
    directory.mkdir(parents=True, exist_ok=False)
    try:
        shutil.copytree(checkpoint / "work", directory / "work", symlinks=True)
        for name in INPUT_FILES:
            shutil.copyfile(checkpoint / name, directory / name)
        shutil.copyfile(checkpoint_file(checkpoint), directory / "prefix-checkpoint.json")
        intervention = (HERE / "pending_instruction.txt").read_bytes() if condition == "instruction" else None
        if intervention is not None:
            (directory / "instruction.txt").write_bytes(intervention)
        instructions = instructions_for((directory / "instructions.md").read_bytes(), intervention)
        (directory / "effective-instructions.md").write_bytes(instructions)
        advice = ""
        if reviewer is not None:
            route = read_json(reviewer / "issued.json")
            require(route.get("session") == reviewer.name, "The review receipt uses a different reviewer directory.")
            route["review_started_monotonic"] = float((reviewer / "started").read_text(encoding="utf-8"))
            for original, copy in (("request.txt", "review-request.txt"), ("receipt.json", "review-receipt.json")):
                shutil.copyfile(reviewer / original, directory / copy)
            write_json(directory / "review-route.json", route)
            advice, _ = reviewer_evidence(directory)
        (directory / "opening.txt").write_bytes(opening_text(directory, advice))
        (directory / "events.jsonl").touch()
        write_json(directory / "run.json", {
            "phase": "continuation", "mode": "steady", "case": frozen["case"], "pin": PIN,
            "budget_seconds": BUDGET_SECONDS, "prefix_elapsed_seconds": 0,
            "prefix_checkpoint_sha256": digest(checkpoint_file(directory).read_bytes()),
            "opening_sha256": opening_hashes(directory),
        })
    except BaseException:
        shutil.rmtree(directory)
        raise


def reviewer_evidence(directory):
    request, receipt, route = (directory / name for name in REVIEW_FILES)
    if not any(path.exists() for path in (request, receipt, route)):
        return "", 0
    return review_details(directory, request.read_bytes(), read_json(receipt), read_json(route))


def start(directory, manifest):
    require(not (directory / "started.json").exists(), "This continuation already started.")
    verify_checkpoint(directory)
    require(manifest["opening_sha256"] == opening_hashes(directory),
            "The prepared solver opening changed.")
    advice, review_seconds = reviewer_evidence(directory)
    opening = opening_text(directory, advice)
    require(opening == (directory / "opening.txt").read_bytes(), "The solver opening differs from the frozen inputs.")
    stamp = time.monotonic()
    receipt = directory / "review-receipt.json"
    route = read_json(directory / "review-route.json") if receipt.exists() else None
    issued = route["monotonic"] if route else stamp
    reviewer_started = route["review_started_monotonic"] if route else stamp
    require(stamp >= reviewer_started + review_seconds, "The solver opened before review ended.")
    write_json(directory / "started.json", {
        "monotonic": stamp, "utc": utc_now(), "reviewer_seconds": review_seconds,
        "review_dispatch_seconds": reviewer_started - issued,
        "review_return_to_solver_seconds": stamp - reviewer_started - review_seconds,
        "receipt_sha256": digest(receipt.read_bytes()) if receipt.exists() else None,
        "advice_sha256": digest(advice.encode()) if advice else None,
    })
    if review_seconds >= manifest["budget_seconds"]:
        record_expiry(directory, manifest)
        raise ValueError("The review exhausted the continuation budget.")
    sys.stdout.buffer.write(opening)


def record_expiry(directory, manifest):
    timing = pivot_run.clock(directory, manifest, time.monotonic())
    write_json(directory / "budget-expired.json", timing)
    pivot_run.record_end(directory, manifest, timing, workspace_tree(directory / "work"), "budget-expired")


def shell(directory, manifest, command):
    with patch.object(pivot_run, "artifact_paths", design_slice_run.artifact_paths):
        try:
            return pivot_run.shell(directory, manifest, command)
        finally:
            if (directory / "budget-expired.json").is_file() and not (directory / "end.json").exists():
                record_expiry(directory, manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    actions = parser.add_subparsers(dest="action", required=True)
    frozen = actions.add_parser("freeze")
    frozen.add_argument("pending_action", type=int)
    frozen.add_argument("destination", type=Path)
    frozen.add_argument("--events", type=Path)
    frozen.add_argument("--workspace", type=Path)
    reviewer = actions.add_parser("reviewer")
    reviewer.add_argument("destination", type=Path)
    run = actions.add_parser("prepare")
    run.add_argument("destination", type=Path)
    run.add_argument("condition", choices=CONDITIONS)
    run.add_argument("--reviewer", type=Path)
    actions.add_parser("start")
    actions.add_parser("sh").add_argument("command")
    actions.add_parser("finish").add_argument("reply")
    args = parser.parse_args()
    directory = args.directory.resolve()
    try:
        if args.action == "freeze":
            freeze(directory, args.pending_action, args.destination.resolve(),
                   args.events.resolve() if args.events else None, args.workspace.resolve() if args.workspace else None)
        elif args.action == "reviewer":
            prepare_reviewer(directory, args.destination.resolve())
        elif args.action == "prepare":
            prepare(directory, args.destination.resolve(), args.condition, args.reviewer.resolve() if args.reviewer else None)
        else:
            with run_lock(directory):
                manifest = read_json(directory / "run.json")
                if args.action == "start":
                    start(directory, manifest)
                elif args.action == "sh":
                    return shell(directory, manifest, args.command)
                else:
                    pivot_run.finish(directory, manifest, args.reply)
    except (ImportError, KeyError, OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
