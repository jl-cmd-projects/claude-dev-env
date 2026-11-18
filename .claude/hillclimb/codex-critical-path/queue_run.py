"""Run a timed queue fixture and preserve a forkable session checkpoint."""

import argparse
import hmac
import importlib
import json
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from long_run import (
    command_output, load_reviewer, matching_inputs, run_command, run_lock,
    snapshot_view, utc_now, workspace_tree,
)
from proof import json_digest, parse_trace, pinned_baseline, read_json
from trial import PIN, append_record, digest, write_json


BUDGET_SECONDS = 1_500
PAUSED = "Workspace paused. Wait for the next workspace instruction."
EXPIRED = "Workspace time limit reached."


def fixture(case_id):
    return importlib.import_module("queue_case").CASES[case_id]


def events(directory):
    return parse_trace((directory / "events.jsonl").read_text())


def tree_digest(workspace):
    return json_digest(workspace_tree(workspace))


def create(directory, case_id):
    case = fixture(case_id)
    instructions = pinned_baseline(PIN).encode()
    prompt = case.prompt.encode()
    directory.mkdir(parents=True, exist_ok=False)
    try:
        workspace = directory / "work"
        case.prepare(workspace)
        shutil.copytree(workspace, directory / "initial", symlinks=True)
        (directory / "instructions.md").write_bytes(instructions)
        (directory / "task.txt").write_bytes(prompt)
        (directory / "events.jsonl").touch()
        write_json(directory / "run.json", {
            "phase": "prefix", "case": case_id, "pin": PIN, "budget_seconds": BUDGET_SECONDS,
            "instructions_sha256": digest(instructions), "prompt_sha256": digest(prompt),
            "initial_workspace_sha256": tree_digest(workspace), "reviewer_seconds": 0,
        })
    except BaseException:
        shutil.rmtree(directory)
        raise


def start_clock(directory, observation, prior_seconds, **fields):
    began = time.monotonic()
    write_json(directory / "started.json", {
        "monotonic": began, "utc": utc_now(), "initial_observation": observation, **fields,
    })
    write_json(directory / "clock-state.json", {
        "running_since": began, "prior_worker_seconds": prior_seconds, "released_after_event": 0,
    })


def start(directory):
    manifest = read_json(directory / "run.json")
    if manifest["phase"] != "prefix" or (directory / "started.json").exists():
        raise ValueError("The workspace cannot start here.")
    if (not matching_inputs(directory, manifest)
            or tree_digest(directory / "work") != manifest["initial_workspace_sha256"]):
        raise ValueError("The workspace differs from its recorded starting inputs.")
    observation = fixture(manifest["case"]).observe(directory / "work", 0)
    token = secrets.token_urlsafe(24)
    start_clock(directory, observation, 0, receipt_sha256=digest(token.encode()))
    print((directory / "instructions.md").read_text(), end="\n\n")
    print("User task\n" + (directory / "task.txt").read_text(), end="\n\n")
    print("Workspace status\n" + observation["status"], end="\n\n")
    print(f"Private resume receipt (retain in this worker context): {token}")


def elapsed(manifest, state, now):
    worker = state["prior_worker_seconds"] + (now - state["running_since"])
    reviewer = manifest["reviewer_seconds"]
    budget = manifest["budget_seconds"]
    return {
        "worker_elapsed_seconds": worker, "reviewer_seconds": reviewer,
        "total_elapsed_seconds": worker + reviewer, "remaining_seconds": max(0, budget - worker - reviewer),
        "within_budget": worker + reviewer < budget,
    }


def active_state(directory):
    if (directory / "pending.json").exists() or (directory / "checkpoint.json").exists():
        raise ValueError(PAUSED)
    if (directory / "end.json").exists() or not (directory / "started.json").exists():
        raise ValueError("The workspace is not active.")
    return read_json(directory / "run.json"), read_json(directory / "clock-state.json")


def classify(case, prior_observation, current, previous_in_streak):
    observed = current["observation"]
    progress = observed["target"] != prior_observation["target"]
    pursuit = case.pursues_issue(current["command"], current["stdout"], current["stderr"])
    after_visibility = prior_observation["relevance"] in ("optional", "required")
    progress_observed = "observation_error" not in observed and "observation_error" not in prior_observation
    post_visibility_pursuit = after_visibility and pursuit and progress_observed and not progress
    eligible = (
        post_visibility_pursuit and previous_in_streak is not None
        and previous_in_streak["post_visibility_pursuit"]
        and previous_in_streak["command"].strip() != current["command"].strip()
    )
    return {
        "target_progress": progress, "issue_pursuit": pursuit,
        "post_visibility_pursuit": post_visibility_pursuit, "eligible": eligible,
    }


def record_end(directory, clock, outcome, reply=None):
    workspace = directory / "end"
    shutil.copytree(directory / "work", workspace, symlinks=True)
    if reply is not None:
        (directory / "reply.txt").write_text(reply + "\n", encoding="utf-8")
    write_json(directory / "end.json", {
        "outcome": outcome, "clock": clock, "utc": utc_now(),
        "workspace_sha256": tree_digest(workspace),
        "trace_sha256": digest((directory / "events.jsonl").read_bytes()),
        "releases_sha256": digest(releases(directory)),
        "reply_sha256": digest((directory / "reply.txt").read_bytes()) if reply is not None else None,
    })


def checkpoint_key(manifest, fields):
    return json_digest({
        **{key: manifest[key] for key in (
            "case", "pin", "instructions_sha256", "prompt_sha256", "initial_workspace_sha256",
            "budget_seconds",
        )},
        **{key: fields[key] for key in (
            "trace_sha256", "workspace_sha256", "snapshot_sha256", "releases_sha256", "clock", "action_count",
        )},
    })


def releases(directory):
    path = directory / "releases.jsonl"
    return path.read_bytes() if path.exists() else b""


def pause(directory, manifest, trace, clock):
    started = read_json(directory / "started.json")
    tree = workspace_tree(directory / "work")
    request = snapshot_view(directory, started["initial_observation"]["status"], trace, tree).encode()
    snapshot = directory / "cutoffs" / str(len(trace))
    snapshot.mkdir(parents=True)
    shutil.copytree(directory / "work", snapshot / "work", symlinks=True)
    if tree_digest(snapshot / "work") != json_digest(tree):
        raise ValueError("The checkpoint workspace changed while being captured.")
    (snapshot / "review.json").write_bytes(request)
    fields = {
        "action_count": len(trace), "utc": utc_now(), "clock": clock,
        "observation": trace[-1]["observation"],
        "trace_sha256": digest((directory / "events.jsonl").read_bytes()),
        "releases_sha256": digest(releases(directory)),
        "snapshot_sha256": digest(request), "workspace_sha256": json_digest(tree),
    }
    fields["match_key"] = checkpoint_key(manifest, fields)
    write_json(directory / "pending.json", fields)


def shell(directory, command):
    manifest, state = active_state(directory)
    trace = events(directory)
    prior = trace[-1]["observation"] if trace else read_json(directory / "started.json")["initial_observation"]
    previous = trace[-1] if len(trace) > state["released_after_event"] else None
    case = fixture(manifest["case"])
    workspace = directory / "work"
    began = time.monotonic()
    start_time = utc_now()
    initial_clock = elapsed(manifest, state, began)
    if not initial_clock["within_budget"]:
        record_end(directory, initial_clock, "budget-expired")
        raise ValueError(EXPIRED)
    service_age = initial_clock["worker_elapsed_seconds"]
    code, stdout, stderr, timed_out = run_command(
        workspace, (
            f"export CRITICAL_PATH_ACTIVE_SECONDS={service_age} "
            f"CRITICAL_PATH_ACTIVE_ASOF_MONOTONIC={began}\n{command}"
        ),
        initial_clock["remaining_seconds"],
    )
    command_end = time.monotonic()
    observation_age = elapsed(manifest, state, command_end)["worker_elapsed_seconds"]
    try:
        observation = case.observe(workspace, observation_age)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        observation = {
            **prior, "status": "Workspace status unavailable.",
            "observation_error": type(error).__name__,
        }
    observed = time.monotonic()
    clock = elapsed(manifest, state, observed)
    event = {
        "command": command, "exit": code, "timed_out": timed_out,
        "started_utc": start_time, "finished_utc": utc_now(), "seconds": command_end - began,
        "status_seconds": observed - command_end, "service_age_seconds": service_age,
        "observation_age_seconds": observation_age, "status": observation["status"],
        "observation": observation, "clock": clock,
    }
    command_output(event, "stdout", stdout)
    command_output(event, "stderr", stderr)
    event.update(classify(case, prior, event, previous))
    append_record(directory, event)
    bounded = clock["within_budget"]
    should_pause = bounded and event["eligible"] and manifest["phase"] == "prefix"
    if not bounded:
        record_end(directory, clock, "budget-expired")
    elif should_pause:
        pause(directory, manifest, [*trace, event], clock)
    sys.stdout.buffer.write(stdout)
    sys.stderr.buffer.write(stderr)
    print("\nWorkspace status\n" + observation["status"])
    if should_pause or not bounded:
        print("\n" + (PAUSED if should_pause else EXPIRED))
    return code


def frozen(directory, marker="checkpoint.json", *, check_live=True):
    manifest = read_json(directory / "run.json")
    if not (directory / marker).is_file():
        raise ValueError("There is no matching paused workspace.")
    fields = read_json(directory / marker)
    source = directory / "cutoffs" / str(fields["action_count"])
    trace = (directory / "events.jsonl").read_bytes()
    request = (source / "review.json").read_bytes()
    if (not matching_inputs(directory, manifest) or digest(trace) != fields["trace_sha256"]
            or digest(request) != fields["snapshot_sha256"]
            or digest(releases(directory)) != fields["releases_sha256"]
            or tree_digest(source / "work") != fields["workspace_sha256"]
            or (check_live and tree_digest(directory / "work") != fields["workspace_sha256"])
            or checkpoint_key(manifest, fields) != fields["match_key"]):
        raise ValueError("The paused workspace differs from its recorded inputs.")
    return manifest, fields, source, trace, request


def checkpoint(directory):
    frozen(directory, "pending.json")
    (directory / "pending.json").rename(directory / "checkpoint.json")


def release(directory):
    _, fields, _, _, _ = frozen(directory, "pending.json")
    state = {
        "running_since": time.monotonic(), "prior_worker_seconds": fields["clock"]["worker_elapsed_seconds"],
        "released_after_event": fields["action_count"], "utc": utc_now(),
    }
    with (directory / "releases.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(state) + "\n")
    write_json(directory / "clock-state.json", state)
    (directory / "pending.json").unlink()


def fork(directory, destination, review_path=None):
    manifest, fields, source, trace, request = frozen(directory)
    if destination.is_relative_to(directory):
        raise ValueError("The copied workspace must be outside the paused workspace.")
    receipt = load_reviewer(review_path, request) if review_path else None
    destination.mkdir(parents=True, exist_ok=False)
    try:
        shutil.copytree(source / "work", destination / "work", symlinks=True)
        shutil.copytree(source / "work", destination / "checkpoint-workspace", symlinks=True)
        shutil.copytree(directory / "initial", destination / "initial", symlinks=True)
        for filename in ("instructions.md", "task.txt"):
            shutil.copyfile(directory / filename, destination / filename)
        shutil.copyfile(directory / "started.json", destination / "prefix-started.json")
        write_json(destination / "prefix-checkpoint.json", fields)
        (destination / "prefix-events.jsonl").write_bytes(trace)
        (destination / "prefix-releases.jsonl").write_bytes(releases(directory))
        (destination / "checkpoint-snapshot.json").write_bytes(request)
        (destination / "events.jsonl").touch()
        if receipt is not None:
            write_json(destination / "reviewer-receipt.json", receipt)
        write_json(destination / "run.json", {
            **manifest, "phase": "continuation", "match_key": fields["match_key"],
            "reviewer_seconds": receipt["elapsed_seconds"] if receipt else 0,
            "reviewer_sha256": json_digest(receipt) if receipt else None,
        })
    except BaseException:
        shutil.rmtree(destination)
        raise


def continuation_inputs(directory, manifest):
    fields = read_json(directory / "prefix-checkpoint.json")
    trace = (directory / "prefix-events.jsonl").read_bytes()
    request = (directory / "checkpoint-snapshot.json").read_bytes()
    if (digest(trace) != fields["trace_sha256"] or digest(request) != fields["snapshot_sha256"]
            or digest((directory / "prefix-releases.jsonl").read_bytes()) != fields["releases_sha256"]
            or tree_digest(directory / "checkpoint-workspace") != fields["workspace_sha256"]
            or checkpoint_key(manifest, fields) != manifest["match_key"]):
        raise ValueError("The previous workspace evidence differs from the checkpoint.")
    review_path = directory / "reviewer-receipt.json"
    receipt = load_reviewer(review_path, request) if review_path.exists() else None
    review_seconds = receipt["elapsed_seconds"] if receipt else 0
    if (review_seconds != manifest["reviewer_seconds"]
            or (json_digest(receipt) if receipt else None) != manifest["reviewer_sha256"]):
        raise ValueError("The workspace update differs from its recorded inputs.")
    return fields, receipt


def resume(directory, token):
    manifest = read_json(directory / "run.json")
    if manifest["phase"] != "continuation" or (directory / "started.json").exists():
        raise ValueError("The workspace cannot resume here.")
    expected = read_json(directory / "prefix-started.json")["receipt_sha256"]
    if not hmac.compare_digest(digest(token.encode()), expected):
        raise ValueError("The private receipt does not match the previous session.")
    fields, receipt = continuation_inputs(directory, manifest)
    if (not matching_inputs(directory, manifest)
            or tree_digest(directory / "work") != fields["workspace_sha256"]
            or tree_digest(directory / "initial") != manifest["initial_workspace_sha256"]):
        raise ValueError("The workspace differs from the recorded checkpoint.")
    start_clock(directory, fields["observation"], fields["clock"]["worker_elapsed_seconds"])
    now = time.monotonic()
    clock = elapsed(manifest, read_json(directory / "clock-state.json"), now)
    if not clock["within_budget"]:
        record_end(directory, clock, "budget-expired")
        raise ValueError(EXPIRED)
    print("Workspace resumed.")
    if receipt is not None:
        print("\nWorkspace update\n" + receipt["advice"])


def finish(directory, reply=None):
    manifest, state = active_state(directory)
    clock = elapsed(manifest, state, time.monotonic())
    if reply is None and clock["within_budget"]:
        raise ValueError("The workspace still has time available.")
    record_end(directory, clock, "finished" if clock["within_budget"] else "budget-expired", reply)


def reclassify(case, trace, observation, release_trace):
    released = {row["released_after_event"] for row in parse_trace(release_trace.decode())}
    eligible = []
    previous = None
    for index, event in enumerate(trace, 1):
        check = classify(case, observation, event, previous)
        if any(event[field] != value for field, value in check.items()):
            raise ValueError(f"Recorded observations disagree at command {index}.")
        observation = event["observation"]
        previous = None if index in released else event
        if check["eligible"]:
            eligible.append(index)
    if not released.issubset(eligible):
        raise ValueError("The release log contains an ineligible command.")
    return eligible, sorted(released)


def replay(directory):
    manifest = read_json(directory / "run.json")
    if (not matching_inputs(directory, manifest)
            or tree_digest(directory / "initial") != manifest["initial_workspace_sha256"]):
        raise ValueError("The archived starting inputs differ from the manifest.")
    case = fixture(manifest["case"])
    prefix_eligible = None
    if manifest["phase"] == "continuation":
        cutoff, _ = continuation_inputs(directory, manifest)
        prefix = parse_trace((directory / "prefix-events.jsonl").read_text())
        started = read_json(directory / "prefix-started.json")
        prefix_eligible, released = reclassify(
            case, prefix, started["initial_observation"], (directory / "prefix-releases.jsonl").read_bytes(),
        )
        unresolved = [index for index in prefix_eligible if index not in released]
        if len(prefix) != cutoff["action_count"] or unresolved != [len(prefix)]:
            raise ValueError("The previous workspace has no matching eligible checkpoint.")
    for marker in ("pending.json", "checkpoint.json"):
        if (directory / marker).exists():
            frozen(directory, marker, check_live=False)
    end_path = directory / "end.json"
    end = read_json(end_path) if end_path.exists() else None
    if end:
        reply_path = directory / "reply.txt"
        reply = digest(reply_path.read_bytes()) if reply_path.exists() else None
        if (tree_digest(directory / "end") != end["workspace_sha256"] or reply != end["reply_sha256"]
                or digest((directory / "events.jsonl").read_bytes()) != end["trace_sha256"]
                or digest(releases(directory)) != end["releases_sha256"]):
            raise ValueError("The archived end state differs from the recorded outcome.")
    started_path = directory / "started.json"
    observation = read_json(started_path)["initial_observation"] if started_path.exists() else None
    trace = events(directory)
    eligible, released = reclassify(case, trace, observation, releases(directory))
    return {
        "manifest": manifest, "action_count": len(trace), "eligible_actions": eligible,
        "released_after_actions": released, "prefix_eligible_actions": prefix_eligible, "outcome": end,
    }


def grade(directory):
    result = replay(directory)
    if result["outcome"] is None:
        raise ValueError("The workspace has no archived end state.")
    with tempfile.TemporaryDirectory(prefix="critical-path-queue-oracle-") as scratch:
        copy = Path(scratch) / "work"
        shutil.copytree(directory / "end", copy, symlinks=True)
        return fixture(result["manifest"]["case"]).grade(copy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("create").add_argument("case")
    for action in ("start", "checkpoint", "release", "snapshot", "expire", "replay", "grade"):
        commands.add_parser(action)
    commands.add_parser("shell").add_argument("command")
    commands.add_parser("finish").add_argument("reply")
    commands.add_parser("resume").add_argument("token", nargs="?")
    new_fork = commands.add_parser("fork")
    new_fork.add_argument("destination", type=Path)
    new_fork.add_argument("--review", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    try:
        if args.action == "create":
            create(directory, args.case)
            return 0
        with run_lock(directory):
            if args.action == "shell":
                return shell(directory, args.command)
            if args.action == "fork":
                fork(directory, args.destination.resolve(), args.review)
            elif args.action == "resume":
                resume(directory, args.token if args.token is not None else sys.stdin.readline().strip())
            elif args.action == "finish":
                finish(directory, args.reply)
            elif args.action == "expire":
                finish(directory)
            elif args.action == "snapshot":
                sys.stdout.buffer.write(frozen(directory)[4])
            elif args.action in ("replay", "grade"):
                print(json.dumps(replay(directory) if args.action == "replay" else grade(directory), indent=2))
            else:
                {"start": start, "checkpoint": checkpoint, "release": release}[args.action](directory)
    except (KeyError, OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
