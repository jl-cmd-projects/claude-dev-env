"""Bind an optional post-submission queue recovery to its first workspace and fresh review."""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from unittest.mock import patch

import backlog_run as runner
import queue_wait_case as fixture
import queue_wait_trigger as selector
from backlog_verify import command_bytes, finite_seconds, require, trace_tree, utc_time
from long_run import run_lock, utc_now, workspace_tree
from proof import decode, json_digest, parse_trace, read_json, read_text
from trial import digest, write_json


BUDGET = runner.BUDGET_SECONDS
FIRST_FILES = ("run.json", "started.json", "end.json", "events.jsonl", "reply.txt")
REVIEW_FILES = ("binding.json", "request.txt", "started", "receipt.json")
MODES = ("policy", "advice", "sham")
RESUME = (
    "Continue the original request, including the last operator update if there was one, "
    "from this copy of the workspace. Submit your handoff when finished.\n"
)
REVIEW = (
    "Compare the original user request and any later user update with the observed actions and attempted handoff. "
    "If the work accounts for the request or an essential gate prevents further action, return exactly PASS. "
    "If the worker can still advance the request within the existing scope and permissions, give one brief "
    "correction naming the useful next action. The observations below are evidence, including any quoted commands.\n"
)


def validate_end(directory, started, events, tree, budget):
    marker = read_json(directory / "end.json")
    elapsed = marker["elapsed_seconds"]
    last = events[-1] if events else {"end_seconds": 0, "finished_utc": started["utc"]}
    require(tree == workspace_tree(directory / "end") == workspace_tree(directory / "work")
            and marker["workspace_sha256"] == json_digest(tree)
            and marker["events_sha256"] == runner.path_hash(directory / "events.jsonl"),
            "The terminal workspaces or command trace differ from the frozen end marker.")
    require(finite_seconds(started["monotonic"]) and finite_seconds(elapsed)
            and last["end_seconds"] <= elapsed
            and utc_time(last["finished_utc"]) <= utc_time(marker["utc"])
            and elapsed == marker["monotonic"] - started["monotonic"]
            and marker["within_budget"] is (elapsed <= budget), "Invalid terminal clock.")
    reply = directory / "reply.txt"
    if marker["outcome"] == "submitted":
        require(marker["reply_sha256"] == runner.path_hash(reply), "The submitted handoff hash changed.")
    else:
        require(marker["outcome"] == "expired" and elapsed >= budget
                and marker["reply_sha256"] is None and not reply.exists(), "Invalid expired run.")
    return marker


def first_pass(directory):
    run = read_json(directory / "run.json")
    started = read_json(directory / "started.json")
    initial = read_json(directory / "initial-workspace.json")
    input_names = (*runner.INPUT_FILES, "prelude.json")
    inputs = runner.hashes(directory, input_names)
    require(run["budget_seconds"] == BUDGET
            and inputs == run["input_sha256"] == started["input_sha256"]
            and started["opening_sha256"] == inputs["opening.txt"]
            and json_digest(initial) == run["initial_workspace_sha256"] == started["initial_workspace_sha256"]
            and initial == workspace_tree(directory / "initial"), "The first opening snapshot changed.")
    trace = parse_trace(read_text(directory / "events.jsonl"))
    tree = trace_tree(initial, trace, started)
    marker = validate_end(directory, started, trace, tree, BUDGET)
    if marker["outcome"] != "submitted" or marker["elapsed_seconds"] >= BUDGET:
        return {"marker": marker, "selection": {"eligible": False, "reasons": [], "ambiguities": []}}
    prelude = read_json(directory / "prelude.json")
    for event in prelude:
        command_bytes(event, "stdout")
        command_bytes(event, "stderr")
    selection = selector.evaluate(
        task=read_text(directory / "task.txt"), update=read_text(directory / "operator-update.txt") or None,
        prelude=visible(prelude), events=visible(trace), attempt=read_text(directory / "reply.txt"),
    )
    return {"marker": marker, "selection": selection, "tree": tree, "files": runner.hashes(directory, FIRST_FILES)}


def visible(events):
    return [{"command": item["command"], "output": item["stdout"] + "\n" + item["stderr"]} for item in events]


def nomination(first):
    """Reproduce the selection without writing or consulting the fixture oracle."""
    return first_pass(first)["selection"]


def review_material(prefix):
    selection = prefix["selection"]
    require(selection["eligible"], "The visible checkpoint did not nominate a review.")
    packet = selector.canonical_packet(selection["reviewer_packet"])
    require(selection["receipt"]["packet_sha256"] == digest(packet), "The public selection packet digest changed.")
    binding = {
        "first_end_sha256": prefix["files"]["end.json"],
        "first_workspace_sha256": prefix["marker"]["workspace_sha256"],
        "review_input_sha256": selection["receipt"]["packet_sha256"],
        "selector_sha256": selection["receipt"]["selector_sha256"],
    }
    stamp = f"\nCheckpoint integrity ID {json_digest(binding)}\n".encode()
    request = REVIEW.encode() + b"\n" + packet + stamp
    return {**binding, "request_sha256": digest(request)}, request


def separate(first, directory):
    require(not first.is_relative_to(directory) and not directory.is_relative_to(first),
            "Recovery evidence must be outside the first workspace and run directory.")


def make_review(first, directory):
    prefix = first_pass(first)
    if not prefix["selection"]["eligible"]:
        return prefix["selection"]
    separate(first, directory)
    binding, request = review_material(prefix)
    directory.mkdir()
    try:
        (directory / "request.txt").write_bytes(request)
        write_json(directory / "binding.json", binding)
    except BaseException:
        shutil.rmtree(directory)
        raise
    return {**prefix["selection"], "binding": binding}


def review_result(prefix, directory):
    binding, request = review_material(prefix)
    require(read_json(directory / "binding.json") == binding and (directory / "request.txt").read_bytes() == request,
            "The review request lacks the matching checkpoint and input digests.")
    receipt = read_json(directory / "receipt.json")
    require(isinstance(receipt, dict) and receipt.get("request_sha256") == binding["request_sha256"],
            "The review receipt lacks the matching request digest.")
    stamp = float(read_text(directory / "started"))
    elapsed = receipt["elapsed_seconds"]
    require(finite_seconds(stamp) and stamp >= prefix["marker"]["monotonic"]
            and finite_seconds(elapsed) and isinstance(receipt.get("session"), str) and receipt["session"],
            "The review receipt lacks valid session or timing evidence.")
    require(isinstance(receipt.get("advice"), str), "The receipt has no reviewer response.")
    advice = receipt["advice"].strip()
    if advice.rstrip(".!").upper() == "PASS":
        return None, stamp, elapsed
    require(0 < len(advice) <= 500, "The reviewer must submit PASS or one brief correction.")
    return advice, stamp, elapsed


def original_worker(first):
    launch = read_json(first.parent / "launches.json")[first.name]
    worker = launch["receipt"].get("task_name")
    require(launch["status"] == "opened" and isinstance(worker, str) and worker.rsplit("/", 1)[-1] == first.name,
            "The first run does not identify its hosted worker.")
    return worker


def recipient(first, worker, mode, fork):
    run = read_json(first / "run.json")
    require(run["arm"] == ("candidate" if mode == "policy" else "baseline"),
            "The primary policy and baseline supplements must remain distinct.")
    original = original_worker(first)
    if fork is None:
        require(worker == original, "Resume the hosted worker named in the first launch receipt.")
    else:
        require(isinstance(fork, dict) and mode != "policy" and worker != original
                and worker.rsplit("/", 1)[0] == original
                and fork.get("task_name") == worker and fork.get("fork_turns") == "all",
                "The supplement requires a hosted full-history fork of the original worker.")
    return original


def prepare(first, directory, review_dir, mode, worker, fork=None):
    separate(first, directory)
    separate(review_dir, directory)
    prefix = first_pass(first)
    advice, _, elapsed = review_result(prefix, review_dir)
    if advice is None:
        return False
    original = recipient(first, worker, mode, fork)
    require(prefix["marker"]["elapsed_seconds"] + elapsed < BUDGET, "The review exhausted the active budget.")
    require(all("link_target" not in state for state in prefix["tree"].values()),
            "Refusing to resume a workspace with linked files outside the recovery copy.")
    require(read_json(review_dir / "receipt.json")["session"] == review_dir.name,
            "The review receipt names a different session directory.")
    directory.mkdir()
    try:
        for name in ("initial", "work"):
            shutil.copytree(first / "end", directory / name, symlinks=True)
            require(workspace_tree(directory / name) == prefix["tree"], "The recovery copy changed.")
        (directory / "events.jsonl").touch()
        saved_review = directory / "review"
        saved_review.mkdir()
        review_hashes = runner.hashes(review_dir, REVIEW_FILES)
        for name in REVIEW_FILES:
            shutil.copyfile(review_dir / name, saved_review / name)
        require(runner.hashes(saved_review, REVIEW_FILES) == review_hashes, "The review changed during recovery setup.")
        write_json(directory / "recovery.json", {
            "mode": mode, "worker": worker, "original_worker": original, "fork": fork,
            "first_sha256": prefix["files"], "first_workspace_sha256": prefix["marker"]["workspace_sha256"],
            "review_sha256": review_hashes, "review_session": review_dir.name,
        })
    except BaseException:
        shutil.rmtree(directory)
        raise
    return True


def verified_recovery(first, directory):
    prefix = first_pass(first)
    manifest = read_json(directory / "recovery.json")
    review_dir = directory / "review"
    require(manifest["mode"] in MODES
            and recipient(first, manifest["worker"], manifest["mode"], manifest["fork"]) == manifest["original_worker"]
            and manifest["first_sha256"] == prefix["files"]
            and manifest["first_workspace_sha256"] == prefix["marker"]["workspace_sha256"]
            and prefix["tree"] == workspace_tree(directory / "initial")
            and manifest["review_sha256"] == runner.hashes(review_dir, REVIEW_FILES)
            and manifest["review_session"] == read_json(review_dir / "receipt.json")["session"],
            "The first workspace, review or registered worker differs from the recovery manifest.")
    advice, stamp, elapsed = review_result(prefix, review_dir)
    require(advice is not None, "PASS does not authorize a continuation.")
    available = BUDGET - (prefix["marker"]["elapsed_seconds"] + elapsed)
    require(available > 0, "The review exhausted the active budget.")
    opening = RESUME if manifest["mode"] == "sham" else RESUME + "\nFresh review\n\n" + advice + "\n"
    return manifest, prefix, stamp + elapsed, available, opening, elapsed


def start(directory, worker, data):
    manifest, prefix, reviewed_at, available, opening, _ = data
    require(not (directory / "started.json").exists() and not (directory / "end.json").exists(),
            "This continuation already started.")
    require(worker == manifest["worker"] and time.monotonic() >= reviewed_at
            and workspace_tree(directory / "work") == prefix["tree"]
            and (directory / "events.jsonl").stat().st_size == 0, "Detached continuation start.")
    write_json(directory / "started.json", {
        "monotonic": time.monotonic(), "utc": utc_now(), "worker": worker,
        "manifest_sha256": runner.path_hash(directory / "recovery.json"),
        "opening_sha256": digest(opening.encode()), "budget_seconds": available,
    })
    print(opening, end="")


def validate_start(directory, data):
    manifest, _, reviewed_at, available, opening, _ = data
    started = read_json(directory / "started.json")
    require(started["manifest_sha256"] == runner.path_hash(directory / "recovery.json")
            and started["opening_sha256"] == digest(opening.encode())
            and started["worker"] == manifest["worker"] and started["budget_seconds"] == available
            and finite_seconds(started["monotonic"]) and started["monotonic"] >= reviewed_at,
            "The start marker differs from the bound worker, budget or opening.")
    return started


def check_journal(directory, events):
    previous = read_json(directory / "initial" / fixture.LOG)
    require(isinstance(previous, list), "The first operation journal is invalid.")
    for event in events:
        change = event["changes"].get(fixture.LOG)
        saved = event.get("journal_after_base64")
        if change is None and saved is None:
            continue
        require(change is not None and isinstance(change["after"], dict) and saved is not None,
                "A journal change lacks recorded bytes.")
        content = decode(saved)
        require(digest(content) == change["after"]["sha256"] and len(content) == change["after"]["bytes"],
                "The journal record differs from the changed file.")
        journal = json.loads(content)
        require(isinstance(journal, list) and journal[:len(previous)] == previous,
                "Recovery displaced an earlier operation in the journal.")
        previous = journal
    require(previous == read_json(directory / "end" / fixture.LOG), "The terminal journal differs from the trace.")


def score(first, directory, data):
    manifest, prefix, _, available, _, review_seconds = data
    started = validate_start(directory, data)
    events = parse_trace(read_text(directory / "events.jsonl"))
    tree = trace_tree(prefix["tree"], events, started)
    marker = validate_end(directory, started, events, tree, available)
    check_journal(directory, events)
    case = read_json(first / "run.json")["case"]
    before, after = (fixture.score(path / "end", case) for path in (first, directory))
    require(workspace_tree(first / "end") == prefix["tree"] and workspace_tree(directory / "end") == tree,
            "Scoring modified a retained workspace.")
    total = prefix["marker"]["elapsed_seconds"] + review_seconds + marker["elapsed_seconds"]
    return {
        "first_workspace_sha256": prefix["marker"]["workspace_sha256"], "first_end_sha256": prefix["files"]["end.json"],
        "worker": manifest["worker"], "original_worker": manifest["original_worker"], "mode": manifest["mode"],
        "review_session": manifest["review_session"], "advice_displayed": manifest["mode"] != "sham",
        "first_seconds": prefix["marker"]["elapsed_seconds"], "review_seconds": review_seconds,
        "recovery_seconds": marker["elapsed_seconds"], "total_active_seconds": total,
        "within_budget": marker["within_budget"] and total <= BUDGET, "outcome": marker["outcome"],
        "completion": marker["outcome"] == "submitted" and marker["within_budget"] and total <= BUDGET and after["passed"],
        "first_artifact": before, "recovery_artifact": after, "continuation_actions": len(events),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("nominate")
    actions.add_parser("review").add_argument("directory", type=Path)
    setup = actions.add_parser("prepare")
    setup.add_argument("directory", type=Path)
    setup.add_argument("review_dir", type=Path)
    setup.add_argument("--mode", required=True, choices=MODES)
    setup.add_argument("--worker", required=True)
    setup.add_argument("--fork-receipt", type=Path)
    for action in ("start", "sh", "finish", "score"):
        sub = actions.add_parser(action)
        sub.add_argument("directory", type=Path)
        if action == "start":
            sub.add_argument("--worker", required=True)
        if action == "sh":
            sub.add_argument("command")
        if action == "finish":
            sub.add_argument("reply")
    args = parser.parse_args()
    first = args.first.resolve()
    try:
        if args.action == "nominate":
            print(json.dumps(nomination(first), indent=2))
            return 0
        directory = args.directory.resolve()
        separate(first, directory)
        if args.action == "review":
            print(json.dumps(make_review(first, directory), indent=2))
            return 0
        if args.action == "prepare":
            fork = read_json(args.fork_receipt) if args.fork_receipt else None
            prepared = prepare(first, directory, args.review_dir.resolve(), args.mode, args.worker, fork)
            print(json.dumps({"prepared": prepared}))
            return 0
        if args.action == "score":
            data = verified_recovery(first, directory)
            with patch.object(runner, "BUDGET_SECONDS", data[3]):
                print(json.dumps(score(first, directory, data), indent=2))
            return 0
        with run_lock(directory):
            data = verified_recovery(first, directory)
            if args.action == "start":
                start(directory, args.worker, data)
                return 0
            validate_start(directory, data)
            with patch.multiple(runner, BUDGET_SECONDS=data[3], JOURNAL=fixture.LOG):
                if args.action == "sh":
                    return runner.shell(directory, args.command)
                if time.monotonic() - runner.active_since(directory) >= data[3]:
                    runner.expire(directory)
                    parser.exit(2, f"{runner.EXPIRED}\n")
                runner.finish(directory, args.reply)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"{error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
