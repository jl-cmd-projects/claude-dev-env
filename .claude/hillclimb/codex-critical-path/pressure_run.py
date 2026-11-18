"""Record matched continuations of a preserved operator conversation."""

import argparse
import importlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from long_run import matching_inputs, run_lock, utc_now, workspace_tree
from proof import directory_name, json_digest, parse_trace, pinned_baseline, read_json, read_text
from trial import HERE, PIN, append_record, digest, write_json


BUDGET_SECONDS = 480
COMMAND_SECONDS = 20
CASES = ("native", "archive")
ARMS = ("baseline", "candidate")
EXPIRED = "Workspace time limit reached."
ACTIVE_NOTICE = "The replay workspace is available through the recorded console."
RECEIPTS = "receipts.jsonl"
MATCH_FIELDS = (
    "case", "pin", "budget_seconds", "command_seconds", "baseline_sha256", "prompt_sha256",
    "fixture_sha256", "runner_sha256", "initial_workspace_sha256",
)
INPUT_NAMES = ("baseline.md", "instructions.md", "task.txt", "intervention.txt")
LOG_NAMES = ("run.json", "started.json", "events.jsonl", RECEIPTS)


def fixture():
    return importlib.import_module("pressure_case")


def fixture_digest():
    return digest(Path(fixture().__file__).read_bytes())


def input_match_key(manifest):
    fields = {field: manifest[field] for field in MATCH_FIELDS}
    if "recovery" in manifest:
        fields["recovery"] = manifest["recovery"]
    return json_digest(fields)


def tree_digest(workspace):
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError("Workspace directory is unavailable.")
    return json_digest(workspace_tree(workspace))


def instructions_for(baseline, intervention):
    if intervention is None:
        return baseline
    anchor = b"\n# Personality\n"
    if baseline.count(anchor) != 1 or not intervention:
        raise ValueError("Candidate instructions or insertion point unavailable.")
    return baseline.replace(anchor, b"\n" + intervention + b"\n" + anchor)


def verify_inputs(directory, manifest):
    baseline = (directory / "baseline.md").read_bytes()
    intervention_path = directory / "intervention.txt"
    intervention = intervention_path.read_bytes() if intervention_path.exists() else None
    if (manifest["pin"] != PIN or manifest["arm"] not in ARMS or manifest["case"] not in CASES
            or manifest["budget_seconds"] != BUDGET_SECONDS or manifest["command_seconds"] != COMMAND_SECONDS
            or digest(baseline) != manifest["baseline_sha256"] or baseline != pinned_baseline(PIN).encode()
            or not matching_inputs(directory, manifest) or fixture_digest() != manifest["fixture_sha256"]
            or digest(Path(__file__).read_bytes()) != manifest["runner_sha256"]
            or (intervention is not None) != (manifest["arm"] == "candidate")
            or (digest(intervention) if intervention is not None else None) != manifest["intervention_sha256"]
            or (directory / "instructions.md").read_bytes() != instructions_for(baseline, intervention)
            or tree_digest(directory / "initial") != manifest["initial_workspace_sha256"]
            or input_match_key(manifest) != manifest["match_key"]):
        raise ValueError("The starting inputs differ from the manifest.")


def match(directory, reference):
    manifest = read_json(directory / "run.json")
    other = read_json(reference / "run.json")
    verify_inputs(directory, manifest)
    verify_inputs(reference, other)
    if manifest["match_key"] != other["match_key"]:
        raise ValueError("The session inputs do not match.")
    return manifest["match_key"]


def create(directory, case_id, arm, reference=None):
    directory_name(directory.name)
    if case_id not in CASES or arm not in ARMS:
        raise ValueError("Unknown workspace case or instructions.")
    baseline = pinned_baseline(PIN).encode()
    intervention = (HERE / "pressure_intervention.txt").read_bytes().strip() if arm == "candidate" else None
    instructions = instructions_for(baseline, intervention)
    prompt = (HERE / "pressure_prompt.txt").read_bytes()
    directory.mkdir(parents=True, exist_ok=False)
    try:
        workspace = directory / "work"
        fixture().prepare(workspace, case_id)
        shutil.copytree(workspace, directory / "initial", symlinks=True)
        (directory / "baseline.md").write_bytes(baseline)
        (directory / "instructions.md").write_bytes(instructions)
        (directory / "task.txt").write_bytes(prompt)
        if intervention is not None:
            (directory / "intervention.txt").write_bytes(intervention)
        (directory / "events.jsonl").touch()
        (directory / RECEIPTS).touch()
        manifest = {
            "case": case_id, "arm": arm, "pin": PIN,
            "budget_seconds": BUDGET_SECONDS, "command_seconds": COMMAND_SECONDS,
            "baseline_sha256": digest(baseline), "prompt_sha256": digest(prompt),
            "instructions_sha256": digest(instructions), "fixture_sha256": fixture_digest(),
            "runner_sha256": digest(Path(__file__).read_bytes()),
            "intervention_sha256": digest(intervention) if intervention is not None else None,
            "initial_workspace_sha256": tree_digest(directory / "initial"),
        }
        manifest["match_key"] = input_match_key(manifest)
        write_json(directory / "run.json", manifest)
        if reference is not None:
            match(directory, reference)
    except BaseException:
        shutil.rmtree(directory)
        raise


def recovery_link(source, outcome):
    return {
        "end_sha256": digest((source / "end.json").read_bytes()),
        "workspace_sha256": outcome["workspace_sha256"],
        "trace_sha256": outcome["sha256"]["events.jsonl"],
        "elapsed_seconds": outcome["clock"]["elapsed_seconds"],
    }


def recover(source, destination):
    directory_name(destination.name)
    if destination.is_relative_to(source):
        raise ValueError("The resumed workspace must be outside its source.")
    original = replay(source)
    outcome = original["outcome"]
    if outcome is None or "recovery" in original["manifest"]:
        raise ValueError("Only a finished original workspace can be copied for a resume.")
    destination.mkdir(parents=True, exist_ok=False)
    try:
        prefix = destination / "prefix"
        prefix.mkdir()
        for name in (*INPUT_NAMES, *LOG_NAMES, "end.json", "reply.txt"):
            path = source / name
            if not path.exists():
                continue
            shutil.copyfile(path, prefix / name)
            if name in INPUT_NAMES:
                shutil.copyfile(path, destination / name)
        for name in ("initial", "end", "work"):
            shutil.copytree(source / name, prefix / name, symlinks=True)
        shutil.copytree(prefix / "initial", destination / "initial", symlinks=True)
        shutil.copytree(prefix / "end", destination / "work", symlinks=True)
        (destination / "events.jsonl").touch()
        (destination / RECEIPTS).touch()
        manifest = {**original["manifest"], "recovery": recovery_link(source, outcome)}
        manifest["match_key"] = input_match_key(manifest)
        write_json(destination / "run.json", manifest)
    except BaseException:
        shutil.rmtree(destination)
        raise


def entry_state(directory, manifest):
    link = manifest.get("recovery")
    if link is None:
        return directory / "initial", manifest["initial_workspace_sha256"], 0
    prefix = directory / "prefix"
    original = replay(prefix)
    expected = {field: value for field, value in original["manifest"].items() if field != "match_key"}
    if (original["outcome"] is None or "recovery" in expected
            or recovery_link(prefix, original["outcome"]) != link
            or any(manifest[field] != value for field, value in expected.items())):
        raise ValueError("The resumed workspace differs from its archived source.")
    return prefix / "end", link["workspace_sha256"], link["elapsed_seconds"]


def start(directory, *, resume=False):
    manifest = read_json(directory / "run.json")
    if (directory / "started.json").exists():
        raise ValueError("The workspace session already started.")
    if resume != ("recovery" in manifest):
        raise ValueError("This workspace requires a different session entry command.")
    workspace = directory / "work"
    verify_inputs(directory, manifest)
    _, starting_tree, prior_seconds = entry_state(directory, manifest)
    if (tree_digest(workspace) != starting_tree
            or (directory / "events.jsonl").stat().st_size or (directory / RECEIPTS).stat().st_size):
        raise ValueError("The workspace differs from its recorded starting state.")
    observation = fixture().observe(workspace, prior_seconds)
    started = {
        "monotonic": time.monotonic(), "utc": utc_now(), "observation": observation,
        "manifest_sha256": json_digest(manifest), "workspace_sha256": starting_tree,
        "prior_seconds": prior_seconds,
    }
    write_json(directory / "started.json", started)
    if prior_seconds >= manifest["budget_seconds"]:
        record_end(directory, clock(manifest, started))
        raise ValueError(EXPIRED)
    if not resume:
        print(read_text(directory / "instructions.md"), end="\n\n")
        print(read_text(directory / "task.txt"), end="\n\n")
    print(ACTIVE_NOTICE)


def clock(manifest, started):
    active_seconds = time.monotonic() - started["monotonic"]
    if active_seconds < 0:
        raise ValueError("The trial clock is unavailable.")
    elapsed = started["prior_seconds"] + active_seconds
    return {
        "elapsed_seconds": elapsed,
        "within_budget": elapsed < manifest["budget_seconds"],
        "remaining_seconds": max(0, manifest["budget_seconds"] - elapsed),
    }


def active(directory):
    if (directory / "end.json").exists():
        raise ValueError("The workspace session ended.")
    if not (directory / "started.json").exists():
        raise ValueError("The workspace session has not started.")
    manifest = read_json(directory / "run.json")
    started = read_json(directory / "started.json")
    if json_digest(manifest) != started["manifest_sha256"]:
        raise ValueError("The session manifest changed after start.")
    return manifest, started


def trace(directory):
    return parse_trace((directory / "events.jsonl").read_text(encoding="utf-8"))


def record_end(directory, stop, reply=None):
    workspace = directory / "work"
    observation = fixture().observe(workspace, stop["elapsed_seconds"])
    end_workspace = directory / "end"
    shutil.copytree(workspace, end_workspace, symlinks=True)
    if reply is not None:
        (directory / "reply.txt").write_text(reply, encoding="utf-8")
    hashes = {name: digest((directory / name).read_bytes()) for name in LOG_NAMES}
    write_json(directory / "end.json", {
        "outcome": "finished" if stop["within_budget"] else "budget-expired",
        "finished_utc": utc_now(), "clock": stop, "observation": observation,
        "workspace_sha256": tree_digest(end_workspace), "sha256": hashes,
        "reply_sha256": digest(reply.encode()) if reply is not None else None,
    })


def receipt_prefix(data):
    return {"bytes": len(data), "sha256": digest(data)}


def shell(directory, shell_name, command):
    manifest, started = active(directory)
    workspace = directory / "work"
    receipts_path = directory / RECEIPTS
    previous_receipts = receipts_path.read_bytes()
    rows = trace(directory)
    expected_tree = rows[-1]["workspace_sha256"] if rows else started["workspace_sha256"]
    expected_receipts = rows[-1]["receipts"] if rows else receipt_prefix(b"")
    if tree_digest(workspace) != expected_tree or receipt_prefix(previous_receipts) != expected_receipts:
        raise ValueError("The workspace changed outside its recorded console.")
    begin = clock(manifest, started)
    if not begin["within_budget"]:
        record_end(directory, begin)
        raise ValueError(EXPIRED)
    start_utc = utc_now()
    execution_error = None
    try:
        code, stdout, stderr, timed_out = fixture().execute(
            workspace, manifest["case"], command, begin["elapsed_seconds"], receipt_path=receipts_path,
            timeout=min(manifest["command_seconds"], begin["remaining_seconds"]), shell=shell_name,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        execution_error = type(error).__name__
        code, stdout, stderr, timed_out = 125, "", f"Console command failed: {error}\n", False
    finish = clock(manifest, started)
    observation = fixture().observe(workspace, finish["elapsed_seconds"])
    tree = workspace_tree(workspace)
    receipt_data = receipts_path.read_bytes()
    if not receipt_data.startswith(previous_receipts):
        raise ValueError("Console receipts changed outside the append log.")
    append_record(directory, {
        "action": len(rows) + 1, "shell": shell_name, "command": command,
        "started_utc": start_utc, "finished_utc": utc_now(), "start_elapsed_seconds": begin["elapsed_seconds"],
        "command_elapsed_seconds": finish["elapsed_seconds"],
        "seconds": finish["elapsed_seconds"] - begin["elapsed_seconds"],
        "exit": code, "stdout": stdout, "stderr": stderr, "timed_out": timed_out,
        "execution_error": execution_error,
        "observation": observation, "workspace": tree, "workspace_sha256": json_digest(tree),
        "receipts": receipt_prefix(receipt_data),
    })
    stop = clock(manifest, started)
    if not stop["within_budget"]:
        record_end(directory, stop)
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    if not stop["within_budget"]:
        sys.stderr.write(f"\n{EXPIRED}\n")
    return code


def finish(directory, reply=None):
    manifest, started = active(directory)
    stop = clock(manifest, started)
    if reply is None and stop["within_budget"]:
        raise ValueError("The workspace session still has time available.")
    record_end(directory, stop, reply)


def verify_trace(rows, data, budget, stop_elapsed, prior_finish):
    prior_bytes = 0
    for index, row in enumerate(rows, 1):
        began = row["start_elapsed_seconds"]
        ended = row["command_elapsed_seconds"]
        size = row["receipts"]["bytes"]
        if (row["action"] != index or row["shell"] not in ("powershell", "bash")
                or not prior_finish <= began <= ended <= stop_elapsed or began >= budget
                or row["seconds"] != ended - began or not prior_bytes <= size <= len(data)
                or (size and data[size - 1:size] != b"\n")
                or receipt_prefix(data[:size]) != row["receipts"]
                or json_digest(row["workspace"]) != row["workspace_sha256"]):
            raise ValueError(f"Recorded evidence disagrees at command {index}.")
        prior_finish, prior_bytes = ended, size
    if prior_bytes != len(data):
        raise ValueError("The receipt log contains unrecorded entries.")


def replay(directory):
    manifest, started = (read_json(directory / path) for path in ("run.json", "started.json"))
    verify_inputs(directory, manifest)
    initial, starting_tree, prior_seconds = entry_state(directory, manifest)
    if (json_digest(manifest) != started["manifest_sha256"]
            or started["prior_seconds"] != prior_seconds or started["workspace_sha256"] != starting_tree
            or fixture().observe(initial, prior_seconds) != started["observation"]):
        raise ValueError("The initial observation differs from the archived state.")
    rows = trace(directory)
    end_path = directory / "end.json"
    ended = read_json(end_path) if end_path.exists() else None
    receipts_path = directory / RECEIPTS
    stop_elapsed = ended["clock"]["elapsed_seconds"] if ended else float("inf")
    verify_trace(rows, receipts_path.read_bytes(), manifest["budget_seconds"], stop_elapsed, prior_seconds)
    expected_workspace = rows[-1]["workspace_sha256"] if rows else starting_tree
    if tree_digest(directory / "work") != expected_workspace:
        raise ValueError("The workspace differs from the last recorded action.")
    reply = None
    if ended:
        for name in LOG_NAMES:
            if digest((directory / name).read_bytes()) != ended["sha256"][name]:
                raise ValueError("The archived trace differs from the recorded outcome.")
        reply_path = directory / "reply.txt"
        reply = read_text(reply_path) if reply_path.exists() else None
        workspace = directory / "end"
        within = stop_elapsed < manifest["budget_seconds"]
        if (stop_elapsed < prior_seconds or tree_digest(workspace) != expected_workspace
                or ended["workspace_sha256"] != expected_workspace
                or fixture().observe(workspace, stop_elapsed) != ended["observation"]
                or (digest(reply.encode()) if reply is not None else None) != ended["reply_sha256"]
                or ended["clock"]["within_budget"] != within
                or ended["clock"]["remaining_seconds"] != max(0, manifest["budget_seconds"] - stop_elapsed)
                or ended["outcome"] != ("finished" if within else "budget-expired")
                or (within and reply is None)):
            raise ValueError("The archived end state differs from the recorded outcome.")
    return {
        "manifest": manifest, "started": started, "action_count": len(rows), "events": rows,
        "receipts": fixture().receipts(receipts_path), "outcome": ended, "reply": reply,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    commands = parser.add_subparsers(dest="action", required=True)
    new = commands.add_parser("create")
    new.add_argument("case", choices=CASES)
    new.add_argument("arm", choices=ARMS)
    new.add_argument("--match", type=Path)
    commands.add_parser("match").add_argument("reference", type=Path)
    commands.add_parser("recover").add_argument("destination", type=Path)
    for action in ("start", "resume", "expire", "replay"):
        commands.add_parser(action)
    for action in ("ps", "sh"):
        commands.add_parser(action).add_argument("command")
    commands.add_parser("finish").add_argument("reply")
    args = parser.parse_args()
    directory = args.directory.resolve()
    try:
        if args.action == "create":
            create(directory, args.case, args.arm, args.match.resolve() if args.match else None)
            return 0
        with run_lock(directory):
            if args.action in ("ps", "sh"):
                return shell(directory, "powershell" if args.action == "ps" else "bash", args.command)
            if args.action == "match":
                print(match(directory, args.reference.resolve()))
            elif args.action in ("start", "resume"):
                start(directory, resume=args.action == "resume")
            elif args.action == "recover":
                recover(directory, args.destination.resolve())
            elif args.action == "replay":
                print(json.dumps(replay(directory), indent=2))
            else:
                finish(directory, args.reply if args.action == "finish" else None)
    except (KeyError, OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
