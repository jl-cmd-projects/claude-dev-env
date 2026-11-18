"""Record a live checkpoint and prepare matched continuations of its workspace."""

import argparse
import fcntl
import hmac
import importlib
import json
import math
import os
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from proof import encode, json_digest, parse_trace, pinned_baseline, read_json
from trial import CASES, PIN, append_record, digest, grade, prepare, write_json


BUDGET_SECONDS = 720
CHECKPOINT_SENTINEL = "CHECKPOINT: stop and await the orchestrator"
FIXTURES = {
    "dev-a": ("long_dev", "LONG_DEV"),
    "dev-b": ("long_dev", "LONG_DEV_REQUIRED"),
    "hold-a": ("long_holdout", "LONG_HOLDOUT"),
    "hold-b": ("long_holdout", "LONG_HOLDOUT_REQUIRED"),
}


def fixture(case_id):
    module_name, case_name = FIXTURES[case_id]
    module = importlib.import_module(module_name)
    CASES[case_id] = getattr(module, case_name)
    return module


def utc_now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def run_lock(directory):
    with (directory / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def file_contents(path):
    if path.is_symlink():
        return {"link_target": os.readlink(path)}
    if path.is_file():
        contents = path.read_bytes()
        return {"bytes": len(contents), "sha256": digest(contents)}
    if path.is_dir():
        return {"directory": True}
    raise ValueError("workspace contains an unsupported file type")


def workspace_tree(workspace):
    return {
        path.relative_to(workspace).as_posix(): {
            **file_contents(path), "mode": stat.S_IMODE(path.lstat().st_mode),
        }
        for path in sorted(workspace.rglob("*"))
    }


def allowed_contents(workspace, case):
    result = {}
    for relative in case.allowed_paths:
        path = Path(relative)
        if any((workspace / parent).is_symlink() for parent in path.parents if parent != Path(".")):
            result[relative] = {"under_symlink": True}
        else:
            path = workspace / path
            result[relative] = file_contents(path) if path.exists() or path.is_symlink() else None
    return result


def create(directory, case_id, diagnostic_terms=None):
    module = fixture(case_id)
    terms = diagnostic_terms if diagnostic_terms is not None else module.DIAGNOSTIC_TERMS
    if not terms or any(not isinstance(term, str) or not term.strip() for term in terms):
        raise ValueError("at least one nonempty diagnostic marker is required")
    instructions = pinned_baseline(PIN).encode()
    prompt = CASES[case_id].prompt.encode()
    directory.mkdir(parents=True, exist_ok=False)
    workspace = directory / "work"
    prepare(case_id, workspace)
    (directory / "instructions.md").write_bytes(instructions)
    (directory / "task.txt").write_bytes(prompt)
    (directory / "events.jsonl").touch()
    initial_tree = workspace_tree(workspace)
    write_json(directory / "initial-workspace.json", initial_tree)
    write_json(directory / "run.json", {
        "phase": "prefix", "case": case_id, "pin": PIN, "budget_seconds": BUDGET_SECONDS,
        "diagnostic_terms": sorted(set(terms)), "instructions_sha256": digest(instructions),
        "baseline_sha256": digest(instructions), "prompt_sha256": digest(prompt),
        "initial_workspace_sha256": json_digest(initial_tree),
    })


def require_fresh(directory):
    if (directory / "started.json").exists():
        raise ValueError("the session has already started")


def observe_status(module, workspace):
    try:
        return module.workspace_status(workspace)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return f"Status command unavailable ({type(error).__name__})."


def matching_inputs(directory, manifest):
    return all(digest((directory / path).read_bytes()) == manifest[key] for path, key in (
        ("task.txt", "prompt_sha256"), ("instructions.md", "instructions_sha256"),
    ))


def start(directory):
    manifest = read_json(directory / "run.json")
    if manifest["phase"] != "prefix":
        raise ValueError("only the original session can start the task")
    require_fresh(directory)
    if not matching_inputs(directory, manifest):
        raise ValueError("the session instructions or task differ from the manifest")
    began = time.monotonic()
    began_utc = utc_now()
    status = observe_status(fixture(manifest["case"]), directory / "work")
    token = secrets.token_urlsafe(24)
    write_json(directory / "started.json", {
        "monotonic": began, "utc": began_utc, "initial_status": status,
        "resume_receipt_sha256": digest(token.encode()),
    })
    print((directory / "instructions.md").read_text(), end="\n\n")
    print("User task\n" + (directory / "task.txt").read_text(), end="\n\n")
    print("Workspace status\n" + status, end="\n\n")
    print(f"Private resume receipt (retain in this worker context): {token}")


def elapsed(directory, manifest, stamp=None):
    began = read_json(directory / "started.json")["monotonic"]
    active = (time.monotonic() if stamp is None else stamp) - began
    prefix = manifest.get("prefix_elapsed_seconds", 0)
    review = manifest.get("reviewer_seconds", 0)
    total = prefix + review + active
    return {
        "phase_elapsed_seconds": active,
        "prefix_elapsed_seconds": active if manifest["phase"] == "prefix" else prefix,
        "reviewer_seconds": review, "worker_elapsed_seconds": active + prefix,
        "total_elapsed_seconds": total, "within_budget": total <= manifest["budget_seconds"],
    }


def require_active(directory):
    if (directory / "checkpoint.json").exists():
        raise ValueError(CHECKPOINT_SENTINEL)
    if (directory / "reply.txt").exists():
        raise ValueError("the session already submitted its reply")
    if not (directory / "started.json").is_file():
        raise ValueError("the session has not started")


def run_command(workspace, command, timeout):
    with subprocess.Popen(
        ["bash", "-c", command], cwd=workspace, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
            return 124, stdout, stderr, True
        return process.returncode, stdout, stderr, False


def command_output(record, key, data):
    decoded = data.decode(errors="replace")
    record[key] = decoded
    if decoded.encode() != data:
        record[f"{key}_base64"] = encode(data)


def checkpoint_reason(events):
    if not events:
        return None
    last = events[-1]
    if last["changed_allowed_paths"]:
        return "allowed-artifact-change"
    if sum(bool(event["diagnostic_terms"]) for event in events) >= 2:
        return "two-diagnostic-actions"
    if len(events) >= 6:
        return "sixth-shell-action"
    return None


def frozen_key(manifest, fields):
    return json_digest({
        "case": manifest["case"], "pin": manifest["pin"],
        "instructions_sha256": manifest["instructions_sha256"],
        "prompt_sha256": manifest["prompt_sha256"],
        "initial_workspace_sha256": manifest["initial_workspace_sha256"],
        "budget_seconds": manifest["budget_seconds"],
        **{key: fields[key] for key in ("trace_sha256", "workspace_sha256", "snapshot_sha256")},
    })


def preview(value, limit):
    if len(value) <= limit:
        return value
    return {
        "preview": value[:limit], "characters": len(value), "sha256": digest(value.encode()),
    }


def snapshot_view(directory, initial_status, events, tree):
    workspace = directory / "work"
    artifacts = {}
    remaining_preview = 16_384
    visible_paths = [path for path in tree if ".git" not in Path(path).parts]
    for relative in visible_paths[:192]:
        record = tree[relative]
        if "directory" in record:
            continue
        artifacts[relative] = dict(record)
        if not 0 < record.get("bytes", 0) <= min(2048, remaining_preview):
            continue
        try:
            contents = (workspace / relative).read_bytes().decode()
        except UnicodeError:
            continue
        artifacts[relative]["content"] = contents
        remaining_preview -= record["bytes"]
    return json.dumps({
        "original_user_task": preview((directory / "task.txt").read_text(), 8192),
        "status_before_first_command": preview(initial_status, 2048),
        "observed_shell_actions": [
            {key: preview(event[key], 2048) if isinstance(event[key], str) else event[key]
             for key in ("command", "exit", "stdout", "stderr", "status")}
            for event in events
        ],
        "workspace_files_at_checkpoint": artifacts,
        "workspace_paths_omitted": max(0, len(visible_paths) - 192),
    }, indent=2) + "\n"


def freeze(directory, manifest, events, reason, completed):
    stamp = read_json(directory / "started.json")
    tree = workspace_tree(directory / "work")
    request = snapshot_view(directory, stamp["initial_status"], events, tree).encode()
    fields = {
        "reason": reason, "action_count": len(events), "status_observations": len(events) + 1,
        "diagnostic_actions": [index for index, row in enumerate(events, 1) if row["diagnostic_terms"]],
        "changed_allowed_paths": events[-1]["changed_allowed_paths"],
        "status_at_cutoff": events[-1]["status"],
        "trace_sha256": digest((directory / "events.jsonl").read_bytes()),
        "workspace_sha256": json_digest(tree), "snapshot_sha256": digest(request),
        "clock": elapsed(directory, manifest, completed),
    }
    fields["match_key"] = frozen_key(manifest, fields)
    (directory / "checkpoint-snapshot.json").write_bytes(request)
    write_json(directory / "checkpoint-workspace.json", tree)
    write_json(directory / "checkpoint.json", fields)


def shell(directory, command):
    require_active(directory)
    manifest = read_json(directory / "run.json")
    module = fixture(manifest["case"])
    case = CASES[manifest["case"]]
    workspace = directory / "work"
    before = allowed_contents(workspace, case)
    began = time.monotonic()
    remaining = manifest["budget_seconds"] - elapsed(directory, manifest, began)["total_elapsed_seconds"]
    if remaining <= 0:
        write_json(directory / "budget-expired.json", elapsed(directory, manifest, began))
        raise ValueError("the session budget has expired")
    began_utc = utc_now()
    code, stdout, stderr, timed_out = run_command(workspace, command, remaining)
    command_end = time.monotonic()
    after = allowed_contents(workspace, case)
    status = observe_status(module, workspace)
    completed = time.monotonic()
    record = {
        "command": command, "start": began, "started_utc": began_utc, "finished_utc": utc_now(),
        "seconds": command_end - began, "status_seconds": completed - command_end,
        "exit": code, "timed_out": timed_out, "status": status,
        "diagnostic_terms": [term for term in manifest["diagnostic_terms"] if term in command],
        "changed_allowed_paths": [path for path in case.allowed_paths if before[path] != after[path]],
        "allowed_before": before, "allowed_after": after,
        "clock": elapsed(directory, manifest, completed),
    }
    command_output(record, "stdout", stdout)
    command_output(record, "stderr", stderr)
    append_record(directory, record)
    if not record["clock"]["within_budget"]:
        write_json(directory / "budget-expired.json", record["clock"])
    reason = None
    if manifest["phase"] == "prefix":
        events = parse_trace((directory / "events.jsonl").read_text())
        reason = checkpoint_reason(events)
        if reason:
            freeze(directory, manifest, events, reason, completed)
    sys.stdout.buffer.write(stdout)
    sys.stderr.buffer.write(stderr)
    print("\nWorkspace status\n" + status)
    if reason:
        print("\n" + CHECKPOINT_SENTINEL)
    return code


def frozen_checkpoint(directory):
    manifest = read_json(directory / "run.json")
    if manifest["phase"] != "prefix" or not (directory / "checkpoint.json").is_file():
        raise ValueError("the original session has no frozen checkpoint")
    fields = read_json(directory / "checkpoint.json")
    tree = read_json(directory / "checkpoint-workspace.json")
    trace = (directory / "events.jsonl").read_bytes()
    request = (directory / "checkpoint-snapshot.json").read_bytes()
    if (not matching_inputs(directory, manifest)
            or workspace_tree(directory / "work") != tree
            or json_digest(tree) != fields["workspace_sha256"]
            or digest(trace) != fields["trace_sha256"]
            or digest(request) != fields["snapshot_sha256"]
            or frozen_key(manifest, fields) != fields["match_key"]):
        raise ValueError("the frozen checkpoint differs from the recorded inputs")
    return manifest, fields, trace, request


def load_reviewer(receipt_path, request):
    receipt = read_json(receipt_path)
    if receipt["request_sha256"] != digest(request):
        raise ValueError("the reviewer receipt is for a different checkpoint")
    seconds = receipt["elapsed_seconds"]
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError("the reviewer receipt has an invalid elapsed time")
    if not isinstance(receipt["advice"], str) or not receipt["advice"].strip():
        raise ValueError("the reviewer receipt has no advice")
    return receipt


def branch(prefix, destination, review=None):
    manifest, fields, trace, request = frozen_checkpoint(prefix)
    if destination.is_relative_to(prefix):
        raise ValueError("the branch destination must be outside the original session")
    receipt = load_reviewer(review, request) if review else None
    destination.mkdir(parents=True, exist_ok=False)
    try:
        shutil.copytree(prefix / "work", destination / "work", symlinks=True)
        if json_digest(workspace_tree(destination / "work")) != fields["workspace_sha256"]:
            raise ValueError("the branch workspace differs from the frozen checkpoint")
        for name in ("instructions.md", "task.txt", "initial-workspace.json", "checkpoint-workspace.json"):
            shutil.copyfile(prefix / name, destination / name)
        write_json(destination / "prefix-run.json", manifest)
        write_json(destination / "prefix-checkpoint.json", fields)
        write_json(destination / "prefix-started.json", read_json(prefix / "started.json"))
        (destination / "prefix-events.jsonl").write_bytes(trace)
        (destination / "checkpoint-snapshot.json").write_bytes(request)
        (destination / "events.jsonl").touch()
        if receipt is not None:
            write_json(destination / "reviewer-receipt.json", receipt)
        write_json(destination / "run.json", {
            **manifest, "phase": "continuation", "match_key": fields["match_key"],
            "prefix_trace_sha256": fields["trace_sha256"],
            "prefix_workspace_sha256": fields["workspace_sha256"],
            "snapshot_sha256": fields["snapshot_sha256"],
            "prefix_elapsed_seconds": fields["clock"]["prefix_elapsed_seconds"],
            "reviewer_seconds": receipt["elapsed_seconds"] if receipt is not None else 0,
        })
    except BaseException:
        shutil.rmtree(destination)
        raise


def resume(directory, token):
    manifest = read_json(directory / "run.json")
    if manifest["phase"] != "continuation":
        raise ValueError("only a checkpoint branch can resume")
    require_fresh(directory)
    expected = read_json(directory / "prefix-started.json")["resume_receipt_sha256"]
    if not hmac.compare_digest(digest(token.encode()), expected):
        raise ValueError("the resume receipt does not match the original session")
    request = (directory / "checkpoint-snapshot.json").read_bytes()
    trace = (directory / "prefix-events.jsonl").read_bytes()
    if (not matching_inputs(directory, manifest)
            or digest(request) != manifest["snapshot_sha256"]
            or digest(trace) != manifest["prefix_trace_sha256"]
            or json_digest(workspace_tree(directory / "work")) != manifest["prefix_workspace_sha256"]):
        raise ValueError("the branch differs from the frozen checkpoint")
    receipt_path = directory / "reviewer-receipt.json"
    if receipt_path.exists():
        receipt = load_reviewer(receipt_path, request)
        if receipt["elapsed_seconds"] != manifest["reviewer_seconds"]:
            raise ValueError("the reviewer elapsed time differs from the branch manifest")
    else:
        receipt = None
        if manifest["reviewer_seconds"] != 0:
            raise ValueError("the branch is missing its reviewer receipt")
    started = time.monotonic()
    write_json(directory / "started.json", {"monotonic": started, "utc": utc_now()})
    clock = elapsed(directory, manifest, started)
    if clock["total_elapsed_seconds"] >= manifest["budget_seconds"]:
        write_json(directory / "budget-expired.json", clock)
        raise ValueError("the session budget has expired")
    print("Continuation accepted.")
    if receipt is not None:
        print("\nIndependent checkpoint review\n" + receipt["advice"])


def finish(directory, reply):
    require_active(directory)
    manifest = read_json(directory / "run.json")
    clock = elapsed(directory, manifest)
    (directory / "reply.txt").write_text(reply + "\n", encoding="utf-8")
    write_json(directory / "clock.json", clock)
    write_json(directory / "end-workspace.json", workspace_tree(directory / "work"))


def artifact_grade(directory):
    manifest = read_json(directory / "run.json")
    fixture(manifest["case"])
    workspace = directory / "work"
    with tempfile.TemporaryDirectory(prefix="critical-path-long-oracle-") as scratch:
        copy = Path(scratch) / "work"
        shutil.copytree(workspace, copy, symlinks=True)
        result = grade(manifest["case"], copy)
    result["details"]["target_errors"] = [
        error.replace(str(copy) + os.sep, "<fixture>/") for error in result["details"]["target_errors"]
    ]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    actions = parser.add_subparsers(dest="action", required=True)
    new = actions.add_parser("create")
    new.add_argument("case", choices=FIXTURES)
    new.add_argument("--diagnostic-term", action="append")
    actions.add_parser("start")
    actions.add_parser("shell").add_argument("command")
    actions.add_parser("snapshot")
    new_branch = actions.add_parser("branch")
    new_branch.add_argument("destination", type=Path)
    new_branch.add_argument("--review", type=Path)
    actions.add_parser("resume").add_argument("token")
    actions.add_parser("finish").add_argument("reply")
    actions.add_parser("grade")
    args = parser.parse_args()
    directory = args.directory.resolve()
    try:
        if args.action == "create":
            create(directory, args.case, args.diagnostic_term)
            return 0
        with run_lock(directory):
            if args.action == "start":
                start(directory)
            elif args.action == "shell":
                return shell(directory, args.command)
            elif args.action == "snapshot":
                sys.stdout.buffer.write(frozen_checkpoint(directory)[3])
            elif args.action == "branch":
                branch(directory, args.destination.resolve(), args.review)
            elif args.action == "resume":
                resume(directory, args.token)
            elif args.action == "finish":
                finish(directory, args.reply)
            elif args.action == "grade":
                print(json.dumps(artifact_grade(directory), indent=2))
    except (KeyError, OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
