"""Capture blinded trial evidence and replay fixture oracles from end-state files.

The recorded shell commands are evidence only. Fixture oracles can run synthetic
candidate code in bounded child processes under the caller's existing sandbox.
"""

import argparse
import base64
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

from cases import _bytes, _git, _workspace_files
from trial import CASES, HERE, SOURCE, digest, grade, prepare, write_json


PROOF_VERSION = 1
LIMITS = {
    "trace": "Recorded fixture shell commands and results. No server model receipt.",
    "timing": "Shell subprocess wall time and observed worker and reviewer elapsed time. No inference token bill.",
    "diversion_seconds": "Wall time for commands tagged as diversions, including any work batched in those commands.",
    "outcome": "The fixture's artifact, preservation, and verification requirements, including required blocker handling.",
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path):
    return path.read_bytes().decode("utf-8")


def encode(data):
    return base64.b64encode(data).decode("ascii")


def decode(data):
    return base64.b64decode(data, validate=True)


def json_digest(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def directory_name(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise ValueError(f"invalid run identifier: {name!r}")
    return name


def snapshot(workspace):
    files = {}
    for relative, path in sorted(_workspace_files(workspace).items()):
        mode = path.lstat().st_mode
        if not stat.S_ISREG(mode):
            raise ValueError(f"unsupported fixture file type: {relative}")
        files[relative] = {"content_base64": encode(path.read_bytes()), "mode": stat.S_IMODE(mode) & 0o777}
    return files


def restore(workspace, files):
    for path in files:
        parts = path.split("/")
        if any(part in ("", ".", "..", ".git", "__pycache__") or "\\" in part or ":" in part for part in parts):
            raise ValueError(f"unsafe fixture path: {path!r}")
    for relative, path in _workspace_files(workspace).items():
        if relative not in files:
            path.unlink()
    for relative, record in files.items():
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(decode(record["content_base64"]))
        path.chmod(record["mode"] & 0o777)


def dirty_state(case_id, workspace):
    case = CASES[case_id]
    paths = sorted(case.dirty_originals)
    if not paths:
        return None
    return {
        "paths": {
            path: {"pristine_base64": encode(_bytes(case.dirty_originals[path])),
                   "before_run_base64": encode(_bytes(case.files[path]))}
            for path in paths
        },
        "end_git_status": _git(workspace, "status", "--porcelain=v1", "--untracked-files=no", "--", *paths).splitlines(),
    }


def trace_fields(events, trace_grade):
    counts = {}
    for label, field in (("diversions", "diversion_count"), ("repeated_no_progress", "repeated_attempt_count")):
        indices = trace_grade[label]
        if any(type(i) is not int or not 1 <= i <= len(events) for i in indices) or len(set(indices)) != len(indices):
            raise ValueError(f"invalid 1-based trace indices for {label}: {indices!r}")
        counts[field] = len(indices)
    for key in ("verification_ok", "false_done", "missed_dependency"):
        if type(trace_grade[key]) is not bool:
            raise ValueError(f"expected a boolean trace grade for {key}")
    return counts


def metrics(record, events, artifact_grade):
    human = record["trace_grade"]
    clock = record["clock"]
    reviewer_seconds = record["manifest"].get("reviewer_seconds", 0)
    elapsed = clock["elapsed_seconds"]
    within_budget = elapsed <= record["manifest"]["budget_seconds"] - reviewer_seconds
    if clock["within_budget"] != within_budget:
        raise ValueError("recorded clock contradicts the shared budget")
    return {
        **trace_fields(events, human),
        "artifact_ok": artifact_grade["artifact_ok"],
        "target_ok": artifact_grade["target_ok"],
        "preservation_ok": artifact_grade["preservation_ok"],
        "verification_ok": human["verification_ok"],
        "false_done": human["false_done"],
        "missed_dependency": human["missed_dependency"],
        "verified_oracle_outcome": (artifact_grade["artifact_ok"] and human["verification_ok"]
                                    and not human["false_done"] and not human["missed_dependency"] and within_budget),
        "within_budget": within_budget,
        "tool_calls": len(events),
        "tool_seconds": round(sum(event["seconds"] for event in events), 6),
        "diversion_tool_seconds": round(sum(events[i - 1]["seconds"] for i in human["diversions"]), 6),
        "worker_elapsed_seconds": round(elapsed, 6),
        "reviewer_count": int(record["reviewer"] is not None),
        "reviewer_seconds": round(reviewer_seconds, 6),
        "total_elapsed_seconds": round(elapsed + reviewer_seconds, 6),
    }


def matching_key(record):
    manifest = record["manifest"]
    key = {name: manifest.get(name) for name in (
        "case", "scope", "pin", "baseline_sha256", "input_files", "prompt_sha256",
        "prefix_trace_sha256", "budget_seconds",
    )}
    prefix = record["prefix"]
    key["prefix_workspace_sha256"] = prefix["end_workspace_sha256"] if prefix else None
    key["declared_launcher_metadata"] = record["declared_launcher_metadata"]
    return key


def parse_trace(raw):
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def comparable_grade(artifact_grade, workspace):
    details = artifact_grade["details"]
    prefix = str(workspace) + os.sep
    errors = [error.replace(prefix, "<fixture>/") for error in details["target_errors"]]
    return {**artifact_grade, "details": {**details, "target_errors": errors}}


def pinned_baseline(pin):
    if not re.fullmatch(r"[0-9a-f]{40}", pin):
        raise ValueError(f"expected a full commit hash: {pin!r}")
    return subprocess.check_output(["git", "show", f"{pin}:{SOURCE}"], cwd=HERE, timeout=10).decode()


def reviewer_evidence(run_root, run_directory, manifest):
    reviewer_id = manifest.get("reviewer_id")
    if reviewer_id is None:
        if manifest.get("reviewer_seconds", 0) or (run_directory / "advice.txt").exists():
            raise ValueError("reviewer inputs without a reviewer ID")
        return None
    source = run_root / directory_name(reviewer_id)
    return {
        "receipt": read_json(source / "receipt.json"),
        "request": read_text(source / "request.txt"),
        "advice": read_text(run_directory / "advice.txt"),
    }


def prefix_evidence(prefixes, hash_value):
    if hash_value is None:
        return None
    matches = prefixes.get(hash_value, [])
    if len(matches) != 1:
        raise ValueError(f"expected one common prefix for {hash_value}, found {len(matches)}")
    source = matches[0]
    workspace = snapshot(source / "work")
    return {
        "run_id": source.name,
        "manifest": read_json(source / "run.json"),
        "prompt": read_text(source / "task.txt"),
        "reply": read_text(source / "reply.txt"),
        "clock": read_json(source / "clock.json"),
        "events_jsonl": read_text(source / "events.jsonl"),
        "end_workspace": workspace,
        "end_workspace_sha256": json_digest(workspace),
    }


def check_record(record, raw_trace):
    manifest = record["manifest"]
    case = CASES[manifest["case"]]
    expected_inputs = {name: digest(_bytes(value)) for name, value in case.files.items()}
    if manifest["input_files"] != expected_inputs:
        raise ValueError("fixture input hashes differ from the manifest")
    for field, contents in (("prompt", record["prompt"]), ("instructions", record["instructions"]),
                            ("baseline", record["pinned_baseline"])):
        if digest(contents.encode()) != manifest[f"{field}_sha256"]:
            raise ValueError(f"{field} SHA-256 differs from the manifest")
    if digest(raw_trace) != record["events_sha256"]:
        raise ValueError("fixture trace SHA-256 differs from the capture")
    if json_digest(record["end_workspace"]) != record["end_workspace_sha256"]:
        raise ValueError("fixture end-state SHA-256 differs from the capture")
    prefix = record["prefix"]
    prefix_digest = digest(prefix["events_jsonl"].encode()) if prefix else None
    if prefix_digest != manifest.get("prefix_trace_sha256"):
        raise ValueError("common prefix trace differs from the manifest")
    if prefix and json_digest(prefix["end_workspace"]) != prefix["end_workspace_sha256"]:
        raise ValueError("common prefix end-state SHA-256 differs from the capture")
    reviewer = record["reviewer"]
    if reviewer:
        receipt = reviewer["receipt"]
        if (receipt["session"] != manifest.get("reviewer_id")
                or receipt["elapsed_seconds"] != manifest.get("reviewer_seconds")
                or reviewer["request"] != record["prompt"]
                or receipt["request_sha256"] != manifest["prompt_sha256"]
                or receipt["advice"] != reviewer["advice"]):
            raise ValueError("reviewer receipt differs from the delivered task, advice, or budget")
    elif manifest.get("reviewer_id") or manifest.get("reviewer_seconds", 0):
        raise ValueError("missing reviewer receipt")


def capture_run(run_root, run_id, blind_directory, trace_grade, prefixes, metadata):
    directory = run_root / directory_name(run_id)
    manifest = read_json(directory / "run.json")
    raw_trace = (directory / "events.jsonl").read_bytes() if (directory / "events.jsonl").is_file() else b""
    events = parse_trace(raw_trace)
    blind_input = read_json(blind_directory / f"{run_id}.json")
    prompt = read_text(directory / "task.txt")
    reply = read_text(directory / "reply.txt")
    clock = read_json(directory / "clock.json")
    if any(blind_input[key] != value for key, value in (
        ("prompt", prompt), ("events", events), ("reply", reply), ("clock", clock),
    )):
        raise ValueError(f"{run_id}: blind grading input differs from the recorded trial")
    files = snapshot(directory / "work")
    record = {
        "proof_version": PROOF_VERSION,
        "run_id": run_id,
        "manifest": manifest,
        "held_out": CASES[manifest["case"]].held_out,
        "declared_launcher_metadata": metadata,
        "prompt": prompt,
        "pinned_baseline": pinned_baseline(manifest["pin"]),
        "instructions": read_text(directory / "instructions.md"),
        "reply": reply,
        "clock": clock,
        "started_monotonic": float(read_text(directory / "started")),
        "events_sha256": digest(raw_trace),
        "source_workspace": str((directory / "work").resolve()),
        "end_workspace": files,
        "end_workspace_sha256": json_digest(files),
        "dirty_state": dirty_state(manifest["case"], directory / "work"),
        "prefix": prefix_evidence(prefixes, manifest.get("prefix_trace_sha256")),
        "reviewer": reviewer_evidence(run_root, directory, manifest),
        "artifact_grade": blind_input["grade"],
        "trace_grade": trace_grade,
    }
    check_record(record, raw_trace)
    record["metrics"] = metrics(record, events, record["artifact_grade"])
    return record, raw_trace


def summarize(records):
    groups = {}
    by_arm = {}
    for record in records:
        key = matching_key(record)
        key_hash = json_digest(key)
        group = groups.setdefault(key_hash, {"key": key, "runs_by_arm": {}})
        arm = record["manifest"]["arm"]
        group["runs_by_arm"].setdefault(arm, []).append(record["run_id"])
        arm_metrics = by_arm.setdefault(arm, {"runs": 0})
        arm_metrics["runs"] += 1
        for measure, value in record["metrics"].items():
            arm_metrics[measure] = round(arm_metrics.get(measure, 0) + value, 6)
    for group in groups.values():
        group["matching_variants"] = len(group["runs_by_arm"]) >= 2
    for counts in by_arm.values():
        counts["verified_oracle_outcome_rate"] = round(counts["verified_oracle_outcome"] / counts["runs"], 6)
    return {"limits": LIMITS, "runs_by_arm": by_arm, "match_groups": groups}


def capture(run_root, blind_directories, output, run_ids=(), declared=None):
    blind = {}
    for directory in blind_directories:
        for run_id, trace_grade in read_json(directory / "grading.json").items():
            if run_id in blind:
                raise ValueError(f"duplicate blind grade for {run_id}")
            blind[run_id] = (directory, trace_grade)
    prefixes = {}
    for path in run_root.iterdir():
        trace = path / "events.jsonl"
        if trace.is_file() and (path / "clock.json").is_file():
            prefixes.setdefault(digest(trace.read_bytes()), []).append(path)
    selected = sorted(set(run_ids) if run_ids else blind)
    if not selected:
        raise ValueError("no completed trials with blind grades")
    data = [capture_run(run_root, run_id, *blind[run_id], prefixes, (declared or {}).get(run_id, {}))
            for run_id in selected]
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError(f"capture output must be empty: {output}")
    for record, raw_trace in data:
        directory = output / record["run_id"]
        directory.mkdir()
        write_json(directory / "proof.json", record)
        (directory / "events.jsonl").write_bytes(raw_trace)
    summary = summarize([record for record, _ in data])
    write_json(output / "summary.json", summary)
    return summary


def replay_run(directory):
    record = read_json(directory / "proof.json")
    if record["proof_version"] != PROOF_VERSION or record["run_id"] != directory.name:
        raise ValueError(f"invalid proof header in {directory}")
    raw_trace = (directory / "events.jsonl").read_bytes()
    check_record(record, raw_trace)
    case_id = record["manifest"]["case"]
    with tempfile.TemporaryDirectory(prefix="critical-path-oracle-") as temporary:
        workspace = Path(temporary)
        prepare(case_id, workspace)
        restore(workspace, record["end_workspace"])
        if dirty_state(case_id, workspace) != record["dirty_state"]:
            raise ValueError(f"{directory.name}: pre-existing dirty paths differ in the reconstructed workspace")
        recomputed_grade = grade(case_id, workspace)
    if comparable_grade(recomputed_grade, workspace.resolve()) != comparable_grade(
        record["artifact_grade"], record["source_workspace"],
    ):
        raise ValueError(f"{directory.name}: fixture oracle differs on replay: {recomputed_grade!r}")
    if metrics(record, parse_trace(raw_trace), recomputed_grade) != record["metrics"]:
        raise ValueError(f"{directory.name}: metrics differ on replay")
    return record


def replay(output, run_ids=()):
    directories = sorted(output / directory_name(run_id) for run_id in set(run_ids)) if run_ids else sorted(
        path for path in output.iterdir() if (path / "proof.json").is_file()
    )
    if not directories:
        raise ValueError(f"no captured trials under {output}")
    summary = summarize([replay_run(directory) for directory in directories])
    if not run_ids and summary != read_json(output / "summary.json"):
        raise ValueError("recomputed study summary differs from the capture")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    collect = actions.add_parser("capture", help="capture completed, blindly graded trials")
    collect.add_argument("--runs-root", required=True, type=Path)
    collect.add_argument("--blind-dir", required=True, action="append", type=Path)
    collect.add_argument("--output", required=True, type=Path)
    collect.add_argument("--run", action="append", default=[])
    collect.add_argument("--declared-metadata", type=Path,
                         help="JSON mapping run IDs to runner-declared model, effort, and launcher details")
    reproduce = actions.add_parser("replay", help="rebuild synthetic end-states and run fixture oracles")
    reproduce.add_argument("--output", required=True, type=Path)
    reproduce.add_argument("--run", action="append", default=[])
    args = parser.parse_args()
    try:
        if args.action == "capture":
            declared = read_json(args.declared_metadata) if args.declared_metadata else None
            summary = capture(args.runs_root, args.blind_dir, args.output, args.run, declared)
        else:
            summary = replay(args.output, args.run)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
