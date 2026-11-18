"""Record an operator update checkpoint and run matched continuations."""

import argparse
import importlib
import json
import math
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pivot_capture
import pivot_case
from long_run import command_output, preview, run_command, run_lock, utc_now, workspace_tree
from proof import json_digest, parse_trace, pinned_baseline, read_json
from trial import append_record, digest, write_json


PIN = "a300d6e78f78568b24b869210cb9595a3b8dc524"
BUDGET_SECONDS = 360
CASES = (*pivot_case.CASES, "capture")
UPDATE = "\n[Operator update]\n"
CHECKPOINT = "CHECKPOINT: pause for operator update"
STEADY_CHECKPOINT = "CHECKPOINT: pause for continuation"
REVIEW_POLICY = "checkpoint-visible-v1"
UNRESOLVED = re.compile(
    r"\b(?:pending|in[ -]progress|running|time[ -]?out|timed out|unavailable|detached|"
    r"(?:a)?waiting|collecting|unknown|failed|unresolved)\b",
    re.IGNORECASE,
)
INPUT_FILES = ("instructions.md", "task.txt", "operator-update.txt", "initial-workspace.json")
DELIVERABLES = tuple(pivot_case.TURNS[turn]["product"] for turn in pivot_case.OUTSTANDING)
DESK_ARTIFACTS = (*DELIVERABLES, *[f".desk/receipts/{turn}.json" for turn in pivot_case.OUTSTANDING])
CAPTURE_ARTIFACTS = ("capture_next.py", "capture-preview.json", "RUNBOOK.md")


def module(case):
    return pivot_capture if case == "capture" else pivot_case


def artifact_paths(case):
    return CAPTURE_ARTIFACTS if case == "capture" else DESK_ARTIFACTS


def hash_files(directory, names):
    return {name: digest((directory / name).read_bytes()) for name in names}


def prepare(directory, case, steady=False):
    instructions = pinned_baseline(PIN)
    if steady:
        original, update = importlib.import_module("pivot_steady").history(case), ""
    else:
        original, update = module(case).history(case).split(UPDATE)
    if not original.strip() or (steady and UPDATE in original) or (not steady and not update.strip()):
        raise ValueError("the fixture dialogue does not match its update mode")
    directory.mkdir(parents=True, exist_ok=False)
    try:
        work = directory / "work"
        work.mkdir()
        module(case).prepare(work, case)
        (directory / "instructions.md").write_text(instructions, encoding="utf-8")
        (directory / "task.txt").write_text(original.rstrip() + "\n", encoding="utf-8")
        (directory / "operator-update.txt").write_text(update, encoding="utf-8")
        (directory / "events.jsonl").touch()
        write_json(directory / "initial-workspace.json", workspace_tree(work))
        write_json(directory / "run.json", {
            "case": case, "phase": "prefix", "pin": PIN, "budget_seconds": BUDGET_SECONDS,
            "mode": "steady" if steady else "operator-update",
            "input_sha256": hash_files(directory, INPUT_FILES),
        })
    except BaseException:
        shutil.rmtree(directory)
        raise


def verify_inputs(directory, manifest):
    if hash_files(directory, INPUT_FILES) != manifest["input_sha256"]:
        raise ValueError("recorded session instructions or task inputs changed")


def require_fresh(directory, manifest, phase):
    if manifest["phase"] != phase or (directory / "started.json").exists():
        raise ValueError(f"a fresh {phase} workspace is required")
    verify_inputs(directory, manifest)


def start(directory, manifest):
    require_fresh(directory, manifest, "prefix")
    if workspace_tree(directory / "work") != read_json(directory / "initial-workspace.json"):
        raise ValueError("the opening workspace changed")
    write_json(directory / "started.json", {
        "monotonic": time.monotonic(), "utc": utc_now(), "reviewer_seconds": 0,
    })
    print((directory / "instructions.md").read_text(encoding="utf-8"))
    print("Opening dialogue\n")
    print((directory / "task.txt").read_text(encoding="utf-8"), end="")


def clock(directory, manifest, now):
    started = read_json(directory / "started.json")
    phase = now - started["monotonic"]
    prefix = manifest.get("prefix_elapsed_seconds", 0)
    reviewer = started["reviewer_seconds"]
    total = prefix + reviewer + phase
    return {
        "phase_elapsed_seconds": phase,
        "prefix_elapsed_seconds": phase if manifest["phase"] == "prefix" else prefix,
        "worker_elapsed_seconds": prefix + phase, "reviewer_seconds": reviewer,
        "total_elapsed_seconds": total, "within_budget": total <= manifest["budget_seconds"],
    }


def require_active(directory, manifest):
    if (directory / "checkpoint.json").exists():
        raise ValueError(STEADY_CHECKPOINT if manifest["mode"] == "steady" else CHECKPOINT)
    if not (directory / "started.json").is_file():
        raise ValueError("the session has not started")
    if (directory / "end.json").exists():
        raise ValueError("the session already ended")


def action_changes(before, after):
    return {
        path: {"before": before.get(path), "after": after.get(path)}
        for path in sorted(before.keys() | after.keys()) if before.get(path) != after.get(path)
    }


def shell_segments(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    segments = [[]]
    try:
        for token in lexer:
            if token in {"|", "||", "&&", ";", "&"}:
                segments.append([])
            else:
                segments[-1].append(token)
    except ValueError:
        return []
    return list(filter(None, segments))


def listing_only(segments):
    found_listing = False
    for segment in segments:
        command_name = Path(segment[0]).name
        if command_name in {"ls", "pwd", "tree", "find"} or (
            command_name == "rg" and "--files" in segment[1:]
        ) or segment[:2] == ["git", "ls-files"]:
            found_listing = True
        elif command_name not in {"head", "tail", "sed", "sort", "grep", "rg", "wc", "cut", "uniq", "cd"}:
            return False
    return found_listing


def inspection_evidence(event, known_logs):
    matches = []
    for source in ("stdout", "stderr"):
        for line in event[source].splitlines():
            if UNRESOLVED.search(line):
                matches.append({"stream": source, "line": preview(line, 512)})
    changes = set(event["changes"])
    logs = sorted(changes & known_logs)
    segments = shell_segments(event["command"])
    listing = listing_only(segments)
    output_only = all(Path(segment[0]).name in {"cd", "echo", "false", "printf", "sleep", "true"}
                      for segment in segments)
    substantive = (bool(event["stdout"].strip() or event["stderr"].strip()) and not listing
                   and not output_only and changes <= known_logs)
    return {
        "action": event["action"], "eligible": substantive and bool(matches),
        "substantive_inquiry": substantive, "listing_only": listing, "output_only": output_only,
        "read_only_by_workspace_diff": not changes, "mixed_with_diagnostic_logs": bool(logs),
        "diagnostic_log_changes": logs, "other_workspace_changes": sorted(changes - known_logs),
        "unresolved_output": matches[:16],
        "unresolved_output_count": len(matches),
    }


def artifact_grade(directory, case):
    with tempfile.TemporaryDirectory(prefix="codex-pivot-oracle-") as scratch:
        work = Path(scratch) / "work"
        shutil.copytree(directory / "work", work, symlinks=True)
        return module(case).grade(work, case)


def review_trigger(directory, manifest, events, _tree):
    opening = read_json(directory / "initial-workspace.json")
    known_logs = {path for path, record in opening.items() if path.endswith(".log") and "sha256" in record}
    inspections = [inspection_evidence(event, known_logs) for event in events]
    changed_before = max((event["action"] for event in events if event["changes"]), default=0)
    current_inquiries = [row for row in inspections
                         if row["action"] > changed_before and row["substantive_inquiry"]]
    update = bool((directory / "operator-update.txt").read_text(encoding="utf-8").strip())
    update_mode = manifest["mode"] == "operator-update"
    observation_gate = (update and any(row["eligible"] for row in inspections)) if update_mode else (
        len(current_inquiries) >= 2 and any(row["eligible"] for row in current_inquiries)
    )
    return {
        "eligible": observation_gate,
        "user_update_present": update, "user_goal_unchanged": not update_mode,
        "observations": inspections, "last_workspace_change_action": changed_before,
        "inquiries_since_workspace_change": [row["action"] for row in current_inquiries],
    }


def review_input(directory, events, tree, pending_reply):
    workspace = directory / "work"
    files = {}
    remaining = 16_384
    for relative, record in tree.items():
        path = Path(relative)
        if ".git" in path.parts or "directory" in record:
            continue
        entry = files[relative] = dict(record)
        if 0 < record.get("bytes", 0) <= min(3072, remaining):
            try:
                entry["content"] = (workspace / path).read_text(encoding="utf-8")
            except UnicodeError:
                continue
            remaining -= record["bytes"]
    return {
        "opening_dialogue": (directory / "task.txt").read_text(encoding="utf-8"),
        "latest_user_update": (directory / "operator-update.txt").read_text(encoding="utf-8"),
        "observed_actions": [
            {**{key: event[key] for key in ("action", "command", "exit", "changes")},
             **{stream: preview(event[stream], 4096) for stream in ("stdout", "stderr")}}
            for event in events
        ],
        "pending_reply": pending_reply,
        "workspace_files": files,
    }


def freeze(directory, manifest, reason, stamp, pending_reply=None, trigger=None):
    tree = workspace_tree(directory / "work")
    trace = (directory / "events.jsonl").read_bytes()
    events = parse_trace(trace.decode())
    write_json(directory / "checkpoint-workspace.json", tree)
    write_json(directory / "review-input.json", review_input(directory, events, tree, pending_reply))
    fields = {
        "reason": reason, "action_count": len(events), "clock": clock(directory, manifest, stamp),
        "workspace_sha256": json_digest(tree), "trace_sha256": digest(trace),
        "review_input_sha256": digest((directory / "review-input.json").read_bytes()),
        "review_policy": REVIEW_POLICY,
        "review_trigger": trigger if trigger is not None else review_trigger(directory, manifest, events, tree),
    }
    write_json(directory / "checkpoint.json", fields)


def shell(directory, manifest, command):
    require_active(directory, manifest)
    workspace = directory / "work"
    before = workspace_tree(workspace)
    events = parse_trace((directory / "events.jsonl").read_text(encoding="utf-8"))
    began = time.monotonic()
    began_utc = utc_now()
    remaining = manifest["budget_seconds"] - clock(directory, manifest, began)["total_elapsed_seconds"]
    steady_prefix = manifest["phase"] == "prefix" and manifest["mode"] == "steady"
    if remaining <= 0:
        timing = clock(directory, manifest, began)
        write_json(directory / "budget-expired.json", timing)
        if steady_prefix:
            record_end(directory, manifest, timing, before, "budget-expired")
        raise ValueError("the session budget has expired")
    code, stdout, stderr, timed_out = run_command(workspace, command, remaining)
    command_ended = time.monotonic()
    after = workspace_tree(workspace)
    changes = action_changes(before, after)
    ended = time.monotonic()
    timing = clock(directory, manifest, ended)
    record = {
        "action": len(events) + 1, "phase": manifest["phase"], "command": command,
        "started_utc": began_utc, "finished_utc": utc_now(), "seconds": command_ended - began,
        "snapshot_seconds": ended - command_ended, "clock": timing, "exit": code, "timed_out": timed_out,
        "before_sha256": json_digest(before), "after_sha256": json_digest(after), "changes": changes,
        "artifact_changes": sorted(set(changes) & set(artifact_paths(manifest["case"]))),
    }
    command_output(record, "stdout", stdout)
    command_output(record, "stderr", stderr)
    append_record(directory, record)
    if not timing["within_budget"]:
        write_json(directory / "budget-expired.json", timing)
    reason, trigger = None, None
    if steady_prefix and (timed_out or not timing["within_budget"]):
        record_end(directory, manifest, timing, after, "budget-expired")
    elif steady_prefix and len(events) >= 1:
        trigger = review_trigger(directory, manifest, [*events, record], after)
        if trigger["eligible"]:
            reason = "independent-inquiry-trigger"
        elif len(events) >= 5:
            reason = "six-shell-action-fallback"
    elif manifest["phase"] == "prefix" and len(events) == 1:
        reason = "two-shell-actions"
    if reason:
        freeze(directory, manifest, reason, ended, trigger=trigger)
    sys.stdout.buffer.write(stdout)
    sys.stdout.flush()
    sys.stderr.buffer.write(stderr)
    sys.stderr.flush()
    if reason:
        print("\n" + (STEADY_CHECKPOINT if steady_prefix else CHECKPOINT))
    return code


def verify_checkpoint(directory, manifest, fields, trace_path):
    verify_inputs(directory, manifest)
    tree = workspace_tree(directory / "work")
    if (tree != read_json(directory / "checkpoint-workspace.json")
            or json_digest(tree) != fields["workspace_sha256"]
            or digest(trace_path.read_bytes()) != fields["trace_sha256"]
            or digest((directory / "review-input.json").read_bytes()) != fields["review_input_sha256"]):
        raise ValueError("the workspace or trace differs from the frozen checkpoint")


def branch(directory, manifest, destination):
    if manifest["phase"] != "prefix" or not (directory / "checkpoint.json").is_file():
        raise ValueError("the prefix has no frozen checkpoint")
    if destination.is_relative_to(directory):
        raise ValueError("the branch destination must be outside the prefix directory")
    fields = read_json(directory / "checkpoint.json")
    verify_checkpoint(directory, manifest, fields, directory / "events.jsonl")
    destination.mkdir(parents=True, exist_ok=False)
    try:
        shutil.copytree(directory / "work", destination / "work", symlinks=True)
        for name in (*INPUT_FILES, "checkpoint-workspace.json", "review-input.json"):
            shutil.copy2(directory / name, destination / name)
        for name in ("run.json", "checkpoint.json", "started.json", "events.jsonl"):
            shutil.copy2(directory / name, destination / f"prefix-{name}")
        (destination / "events.jsonl").touch()
        write_json(destination / "run.json", {
            **manifest, "phase": "continuation",
            "prefix_elapsed_seconds": fields["clock"]["prefix_elapsed_seconds"],
            "prefix_checkpoint_sha256": digest((destination / "prefix-checkpoint.json").read_bytes()),
        })
        verify_checkpoint(destination, manifest, fields, destination / "prefix-events.jsonl")
    except BaseException:
        shutil.rmtree(destination)
        raise


def resume(directory, manifest):
    require_fresh(directory, manifest, "continuation")
    saved = directory / "prefix-checkpoint.json"
    if digest(saved.read_bytes()) != manifest["prefix_checkpoint_sha256"]:
        raise ValueError("the checkpoint metadata changed")
    fields = read_json(saved)
    verify_checkpoint(directory, manifest, fields, directory / "prefix-events.jsonl")
    review_path = directory / "review.json"
    advice_path = directory / "advice.txt"
    seconds, advice, receipt_sha256, advice_sha256 = 0, "", None, None
    if review_path.exists() or advice_path.exists():
        if fields.get("review_policy") != REVIEW_POLICY:
            raise ValueError("the checkpoint does not use the visible review policy")
        if not fields["review_trigger"]["eligible"]:
            raise ValueError("the checkpoint did not trigger independent review")
        if not review_path.is_file():
            raise ValueError("advice requires a review receipt")
        review_bytes = review_path.read_bytes()
        receipt = json.loads(review_bytes)
        if not isinstance(receipt, dict) or receipt.get("request_sha256") != fields["review_input_sha256"]:
            raise ValueError("the review receipt lacks the matching checkpoint digest")
        seconds = receipt.get("elapsed_seconds")
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("the review receipt elapsed time is invalid")
        receipt_sha256 = digest(review_bytes)
        if advice_path.exists():
            advice_bytes = advice_path.read_bytes()
            advice = advice_bytes.decode("utf-8")
            advice_sha256 = digest(advice_bytes)
    began = time.monotonic()
    write_json(directory / "started.json", {
        "monotonic": began, "utc": utc_now(), "reviewer_seconds": seconds,
        "receipt_sha256": receipt_sha256, "advice_sha256": advice_sha256,
    })
    if manifest["mode"] == "steady":
        print("Continuation accepted.")
    else:
        print("[Operator update]\n" + (directory / "operator-update.txt").read_text(encoding="utf-8"), end="")
    timing = clock(directory, manifest, began)
    if timing["total_elapsed_seconds"] >= manifest["budget_seconds"]:
        write_json(directory / "budget-expired.json", timing)
        raise ValueError("the session budget has expired")
    if advice.strip():
        print("\n[Independent review]\n" + advice.rstrip())


def record_end(directory, manifest, timing, tree, reason, reply=None):
    reply_bytes = (reply + "\n").encode() if reply is not None else None
    if reply_bytes is not None:
        with (directory / "reply.txt").open("xb") as stream:
            stream.write(reply_bytes)
    write_json(directory / "clock.json", timing)
    write_json(directory / "end-workspace.json", tree)
    write_json(directory / "end.json", {
        "clock": timing, "workspace_sha256": json_digest(tree), "finished_utc": utc_now(), "reason": reason,
        "trace_sha256": digest((directory / "events.jsonl").read_bytes()),
        "reply_sha256": digest(reply_bytes) if reply_bytes is not None else None,
        "prefix_checkpoint_sha256": manifest.get("prefix_checkpoint_sha256"),
    })


def finish(directory, manifest, reply):
    require_active(directory, manifest)
    stamp = time.monotonic()
    if manifest["phase"] == "prefix" and manifest["mode"] == "operator-update":
        freeze(directory, manifest, "attempted-finish", stamp, pending_reply=reply)
        print(CHECKPOINT)
        return
    tree = workspace_tree(directory / "work")
    record_end(directory, manifest, clock(directory, manifest, stamp), tree, "reply", reply)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("prepare")
    create.add_argument("case", choices=CASES)
    create.add_argument("--steady", action="store_true")
    actions.add_parser("branch").add_argument("destination", type=Path)
    actions.add_parser("sh").add_argument("command")
    actions.add_parser("finish").add_argument("reply")
    for action in ("start", "resume", "snapshot", "grade"):
        actions.add_parser(action)
    args = parser.parse_args()
    directory = args.directory.resolve()
    try:
        if args.action == "prepare":
            prepare(directory, args.case, steady=args.steady)
            return 0
        with run_lock(directory):
            manifest = read_json(directory / "run.json")
            if args.action == "start":
                start(directory, manifest)
            elif args.action == "branch":
                branch(directory, manifest, args.destination.resolve())
            elif args.action == "resume":
                resume(directory, manifest)
            elif args.action == "sh":
                return shell(directory, manifest, args.command)
            elif args.action == "finish":
                finish(directory, manifest, args.reply)
            elif args.action == "grade":
                print(json.dumps(artifact_grade(directory, manifest["case"]), indent=2))
            elif args.action == "snapshot":
                sys.stdout.buffer.write((directory / "review-input.json").read_bytes())
    except (ImportError, KeyError, OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
