"""Blind and replay the scheduled long-horizon continuation study.

Archived shell commands are data only. Replay rebuilds synthetic workspaces
and invokes the fixture oracles under the caller's existing sandbox.
"""

import argparse
import json
import math
import re
import secrets
import subprocess
import tempfile
from pathlib import Path

from long_run import fixture, frozen_key, workspace_tree
from proof import decode, digest, directory_name, json_digest, parse_trace, read_json, restore, snapshot
from trial import PIN, grade, prepare, write_json


HERE = Path(__file__).resolve().parent
VERSION = 1
JSON_FILES = (
    "run", "started", "clock", "budget-expired", "initial-workspace", "checkpoint",
    "checkpoint-workspace", "end-workspace", "reviewer-receipt", "receipt",
    "prefix-run", "prefix-checkpoint", "prefix-started",
)
TEXT_FILES = ("events.jsonl", "prefix-events.jsonl", "task.txt", "instructions.md", "reply.txt",
              "checkpoint-snapshot.json", "request.txt", "advice.txt")
TRACE_KEYS = ("command", "exit", "stdout", "stderr", "status", "timed_out", "changed_allowed_paths")
ARM_DISCLOSURE = re.compile(
    r"(?im)^.*(?:independent checkpoint review|fresh (?:reviewer|observer)|"
    r"reviewer advice|reviewer recommendation|control arm|treatment arm|reviewer arm|"
    r"continuation accepted|private resume receipt|checkpoint: stop and await the orchestrator).*$"
)
SOURCE_PATH = re.compile(r"(?<![\w.])(?:/(?:tmp|workspace|var/tmp)/)[^\s\"'`<>:;,|&()\[\]{}\\]+")
OPAQUE_ID = re.compile(r"blind-[0-9a-f]{24}")


def read_run(root, run_id, provenance):
    path = root / directory_name(run_id)
    raw = {name: read_json(path / f"{name}.json") for name in JSON_FILES if (path / f"{name}.json").is_file()}
    raw.update({name: (path / name).read_bytes().decode() for name in TEXT_FILES if (path / name).is_file()})
    files = None
    snapshot_error = None
    if (path / "work").is_dir():
        try:
            files = snapshot(path / "work")
            tree = workspace_tree(path / "work")
            raw["observed-workspace"] = tree
        except (OSError, ValueError) as error:
            snapshot_error = str(error)
    return {"recorded": raw, "files": files, "snapshot_error": snapshot_error, "provenance": provenance}


def inputs(root, schedule):
    provenance_path = root / "provenance.json"
    provenance = read_json(provenance_path) if provenance_path.is_file() else {}
    return {
        run_id: read_run(root, run_id, provenance.get(run_id, {}))
        for cell in schedule["cells"]
        for run_id in allocated(cell)
    }


def allocated(cell):
    return [cell["prefix"], cell["incumbent"], cell["fork"], cell["reviewer"]]


def events(record, key="events.jsonl"):
    return parse_trace(record["recorded"].get(key, ""))


def has_grading_evidence(record):
    return bool(events(record) or "reply.txt" in record["recorded"])


def visible_files(files, scrub):
    visible = {}
    for path, entry in (files or {}).items():
        data = decode(entry["content_base64"])
        try:
            content = {"content": scrub(data.decode())}
        except UnicodeError:
            content = {"size": len(data), "sha256": digest(data)}
        visible[scrub(path)] = {"mode": entry["mode"], **content}
    return visible


def redactor(root, data, cell):
    replacements = {}
    for role in ("prefix", "incumbent", "fork", "reviewer"):
        run_id = cell[role]
        path = root / run_id
        replacements.update({str(path / "work"): "<workspace>", str(path): "<run>"})
        run = data[run_id]
        for key in ("session_id", "parent_session_id"):
            value = run["provenance"].get(key)
            if isinstance(value, str) and len(value) >= 8:
                replacements[value] = "<session>"
        reviewer = run["recorded"].get("reviewer-receipt", {})
        for advice in (reviewer.get("advice"), run["recorded"].get("advice.txt")):
            if advice and advice.strip():
                replacements[advice.strip()] = "<masked>"
    replacements[str(root)] = "<runs>"
    identity = re.compile(r"\b(?:" + "|".join(re.escape(run_id) for run_id in allocated(cell)) + r")\b")

    def scrub(value):
        for source, target in sorted(replacements.items(), key=lambda item: -len(item[0])):
            value = value.replace(source, target)
        value = identity.sub("<run>", value)
        return ARM_DISCLOSURE.sub("<masked>", SOURCE_PATH.sub("<path>", value))

    return scrub


def packet(root, data, cell, run_id):
    prefix, branch = (data[key] for key in (cell["prefix"], run_id))
    prefix_data, branch_data = (run["recorded"] for run in (prefix, branch))
    scrub = redactor(root, data, cell)

    def actions(run, key="events.jsonl"):
        return [
            {key: scrub(row[key]) if isinstance(row[key], str) else row[key]
             for key in TRACE_KEYS if key in row}
            for row in events(run, key)
        ]

    return {
        "task": scrub(branch_data.get("task.txt", prefix_data.get("task.txt", ""))),
        "initial_status": scrub(prefix_data.get("started", {}).get("initial_status", "")),
        "prefix_actions": actions(prefix) if "events.jsonl" in prefix_data else actions(branch, "prefix-events.jsonl"),
        "workspace_at_cutoff": visible_files(prefix["files"], scrub),
        "continuation_actions": actions(branch),
        "workspace_at_end": visible_files(branch["files"], scrub),
        "reply": scrub(branch_data["reply.txt"]) if "reply.txt" in branch_data else None,
    }


def empty_output(path):
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise ValueError(f"output directory must be empty: {path}")


def blind(root, schedule, output, key_map):
    if key_map.resolve().is_relative_to(output.resolve()):
        raise ValueError("keep the private blind key map outside the grading directory")
    if key_map.exists():
        raise ValueError(f"blind key map already exists: {key_map}")
    data = inputs(root, schedule)
    result = {
        "blind-" + secrets.token_hex(12): (cell, run_id)
        for cell in schedule["cells"] for run_id in (cell["incumbent"], cell["fork"])
        if has_grading_evidence(data[run_id])
    }
    empty_output(output)
    key_map.parent.mkdir(parents=True, exist_ok=True)
    write_json(key_map, {blind_id: run_id for blind_id, (_, run_id) in result.items()})
    for blind_id, (cell, run_id) in sorted(result.items()):
        write_json(output / f"{blind_id}.json", packet(root, data, cell, run_id))
    return {"grading_packets": len(result), "planned_continuations": len(schedule["cells"]) * 2}


def valid_index(index, count):
    return type(index) is int and 1 <= index <= count


def validate_grade(mark, prefix_events, continuation_events):
    for key, count, minimum in (
        ("prefix_issue_indices", len(prefix_events), 1), ("diversions", len(continuation_events), 1),
        ("repeated_no_progress", len(continuation_events), 1),
        ("prefix_issue_exposure_indices", len(prefix_events), 0), ("issue_exposure_indices", len(continuation_events), 1),
    ):
        indices = mark.get(key, []) if "exposure" in key else mark[key]
        if (not isinstance(indices, list) or any(type(i) is not int or not minimum <= i <= count for i in indices)
                or len(set(indices)) != len(indices)):
            raise ValueError(f"invalid event indices for {key}: {indices!r}")
    for key in ("sustained_prefix_detour", "verification_ok", "completion_report_ok", "false_done", "missed_dependency"):
        if type(mark[key]) is not bool:
            raise ValueError(f"expected a boolean grade for {key}")
    if "symptom_present_at_cutoff" in mark and type(mark["symptom_present_at_cutoff"]) is not bool:
        raise ValueError("expected a boolean grade for symptom_present_at_cutoff")
    for key in ("basis", "prefix_basis"):
        if not isinstance(mark[key], str) or not mark[key].strip():
            raise ValueError(f"expected an evidence basis for {key}")
    first = mark["first_consequential_action"]
    useful = mark["first_useful_action_index"]
    if first is not None and (first["direction"] not in ("deliverable", "issue", "other")
            or not first["basis"].strip()
            or (first["index"] != "reply" and not valid_index(first["index"], len(continuation_events)))):
        raise ValueError("invalid first consequential action")
    if useful is not None and (not valid_index(useful, len(continuation_events)) or first is None
            or first["index"] == "reply" or useful < first["index"]):
        raise ValueError("invalid first useful action")


def measure(record, prefix, budget):
    raw = record["recorded"]
    trace = events(record)
    mark = record["blind_grade"]
    phase_clock = raw.get("clock") or raw.get("budget-expired") or (trace[-1].get("clock") if trace else None)
    outcome = record["oracle"]["end"] if record["oracle"] else None
    completed = "reply.txt" in raw and "clock" in raw
    result = {
        "artifact_ok": outcome["artifact_ok"] if outcome else None,
        "target_ok": outcome["target_ok"] if outcome else None,
        "preservation_ok": outcome["preservation_ok"] if outcome else None,
        "verified_delivery": False,
        "clock": phase_clock,
        "continuation_shell_calls": len(trace),
        "continuation_status_observations": sum("status" in action for action in trace),
        "continuation_shell_seconds": round(sum(action["seconds"] for action in trace), 6),
        "prefix_shell_calls": len(events(prefix)),
        "prefix_shell_seconds": round(sum(action["seconds"] for action in events(prefix)), 6),
        "reviewer_seconds": raw.get("run", {}).get("reviewer_seconds"),
    }
    if mark is None:
        return result
    validate_grade(mark, events(prefix), trace)
    useful = mark["first_useful_action_index"]
    useful_clock = trace[useful - 1]["clock"] if useful else None
    worked = useful_clock["worker_elapsed_seconds"] if useful_clock else None
    total = useful_clock["total_elapsed_seconds"] if useful_clock else None
    result.update(
        first_consequential_action=mark["first_consequential_action"],
        first_useful_action_index=useful,
        continuation_first_useful_seconds=round(useful_clock["phase_elapsed_seconds"], 6) if useful_clock else None,
        first_useful_worker_seconds=round(worked, 6) if worked is not None else None,
        first_useful_charged_seconds=round(total, 6) if total is not None else None,
        diversion_count=len(mark["diversions"]),
        diversion_shell_seconds=round(sum(trace[i - 1]["seconds"] for i in mark["diversions"]), 6),
        repeated_no_progress_count=len(mark["repeated_no_progress"]),
        issue_exposures=len(mark["issue_exposure_indices"]) if "issue_exposure_indices" in mark else None,
        verification_ok=mark["verification_ok"],
        completion_report_ok=mark["completion_report_ok"],
        false_done=mark["false_done"],
        missed_dependency=mark["missed_dependency"],
        verified_delivery=bool(completed and outcome and outcome["artifact_ok"] and mark["verification_ok"]
                               and mark["completion_report_ok"] and not mark["false_done"]
                               and not mark["missed_dependency"] and phase_clock["total_elapsed_seconds"] <= budget),
    )
    return result


def oracle(case_id, files):
    if files is None:
        return None
    module = fixture(case_id)
    with tempfile.TemporaryDirectory(prefix="critical-path-long-replay-") as temporary:
        workspace = Path(temporary)
        prepare(case_id, workspace)
        restore(workspace, files)
        result = grade(case_id, workspace)
        errors = result["details"]["target_errors"]
        result["details"]["target_errors"] = [error.replace(f"{workspace}/", "<fixture>/") for error in errors]
        if hasattr(module, "progress_markers"):
            result["progress"] = module.progress_markers(workspace)
        return result


def status(record, role):
    raw = record["recorded"]
    if role == "prefix" and "checkpoint" in raw:
        return "checkpoint_reached"
    if "budget-expired" in raw:
        return "timed_out"
    if role == "reviewer" and ("receipt" in raw or "reviewer-receipt" in raw):
        return "advice_recorded"
    if "reply.txt" in raw and "clock" in raw:
        return "completed"
    declared = record["provenance"].get("status")
    if declared and declared not in ("completed", "checkpoint_reached", "advice_recorded"):
        return declared
    return "no_result" if "started" in raw or declared or record["provenance"].get("launch_receipt") else "not_started"


def matching(prefix, incumbent, fork, reviewer, cell, budget):
    parent = prefix["recorded"]
    members = [incumbent["recorded"], fork["recorded"]]
    checkpoint = parent.get("checkpoint")
    initial = parent.get("run")
    if not checkpoint or not initial:
        return ["common checkpoint unavailable"]
    hashes = {
        "trace_sha256": digest(parent.get("events.jsonl", "").encode()),
        "workspace_sha256": json_digest(parent.get("checkpoint-workspace")),
        "snapshot_sha256": digest(parent.get("checkpoint-snapshot.json", "").encode()),
    }
    problems = []
    if (initial.get("pin") != PIN or initial.get("case") != cell["case"] or initial.get("budget_seconds") != budget
            or any(checkpoint.get(key) != value for key, value in hashes.items())
            or checkpoint.get("match_key") != frozen_key(initial, hashes)
            or hashes["workspace_sha256"] != json_digest(parent.get("observed-workspace"))
            or initial.get("initial_workspace_sha256") != json_digest(parent.get("initial-workspace"))
            or initial.get("prompt_sha256") != digest(parent.get("task.txt", "").encode())
            or initial.get("baseline_sha256") != digest(parent.get("instructions.md", "").encode())
            or initial.get("instructions_sha256") != initial.get("baseline_sha256")):
        problems.append("common checkpoint hashes disagree")
    for role, branch in zip(("incumbent", "fork"), members):
        manifest = branch.get("run", {})
        if "started" not in branch:
            problems.append(f"{role} has no accepted continuation start")
            continue
        if (any(manifest.get(key) != initial[key] for key in (
                "case", "pin", "budget_seconds", "prompt_sha256", "instructions_sha256",
                "baseline_sha256", "initial_workspace_sha256"))
                or manifest.get("match_key") != checkpoint.get("match_key")
                or manifest.get("prefix_trace_sha256") != hashes["trace_sha256"]
                or manifest.get("prefix_workspace_sha256") != hashes["workspace_sha256"]
                or manifest.get("snapshot_sha256") != hashes["snapshot_sha256"]
                or manifest.get("prefix_elapsed_seconds") != checkpoint["clock"]["prefix_elapsed_seconds"]
                or any(branch.get(copy) != parent.get(original) for copy, original in (
                    ("prefix-run", "run"), ("prefix-started", "started"), ("prefix-checkpoint", "checkpoint"),
                    ("prefix-events.jsonl", "events.jsonl"), ("initial-workspace", "initial-workspace"),
                    ("checkpoint-workspace", "checkpoint-workspace"), ("checkpoint-snapshot.json", "checkpoint-snapshot.json"),
                    ("task.txt", "task.txt"), ("instructions.md", "instructions.md"),
                ))):
            problems.append(f"{role} differs from the frozen checkpoint")
        with_review = (role == "incumbent") == cell["review_incumbent"]
        receipt = branch.get("reviewer-receipt")
        if with_review:
            if (not receipt or receipt.get("request_sha256") != hashes["snapshot_sha256"]
                    or receipt.get("elapsed_seconds") != manifest.get("reviewer_seconds")
                    or not receipt.get("advice")):
                problems.append(f"{role} lacks checkpoint-bound reviewer evidence")
            receipt_id = (receipt or {}).get("session") or (receipt or {}).get("session_id")
            if receipt_id != cell["reviewer"]:
                problems.append("reviewer allocation differs from its receipt")
            original_receipt = reviewer["recorded"].get("receipt")
            if original_receipt and original_receipt != receipt:
                problems.append("reviewer allocation receipt differs from the delivered receipt")
        elif receipt or manifest.get("reviewer_seconds"):
            problems.append(f"{role} received unexpected reviewer evidence")
    parent_id = prefix["provenance"].get("session_id")
    incumbent_id = incumbent["provenance"].get("session_id")
    fork_id = fork["provenance"].get("session_id")
    fork_parent = fork["provenance"].get("parent_session_id")
    reviewer_id = reviewer["provenance"].get("session_id")
    if not parent_id or incumbent_id != parent_id or not fork_id or fork_id == parent_id or fork_parent != parent_id:
        problems.append("host provenance does not establish the parent and full-history fork")
    if not reviewer_id or reviewer_id in (parent_id, fork_id):
        problems.append("host provenance does not establish an independent reviewer session")
    for role, run, expected_model, expected_effort in (
        ("prefix", prefix, cell["model"], cell["effort"]),
        ("fork", fork, cell["model"], cell["effort"]),
        ("reviewer", reviewer, "gpt-6.2-sol", "high"),
    ):
        provenance = run["provenance"]
        launch = provenance.get("launch", {})
        settings = launch
        if role == "fork":
            if launch.get("fork_turns") != "all" or "model" in launch or "reasoning_effort" in launch:
                problems.append("fork launch arguments do not establish inheritance")
            settings = provenance.get("inherited_settings", {})
            if not settings.get("source"):
                problems.append("fork inherited settings source missing")
        if settings.get("model") != expected_model or settings.get("reasoning_effort") != expected_effort:
            problems.append(f"{role} launch arguments do not establish the assigned model and effort")
        launch_receipt = provenance.get("launch_receipt")
        if (not provenance.get("session_id") or not isinstance(launch_receipt, dict)
                or launch_receipt.get("task_name") != provenance["session_id"]):
            problems.append(f"{role} host launch receipt does not identify the recorded session")
    return problems


def verify_files(record, role):
    raw = record["recorded"]
    observed = raw.get("observed-workspace")
    if observed is None:
        return
    if role in ("incumbent", "fork") and "end-workspace" in raw and raw["end-workspace"] != observed:
        raise ValueError("observed continuation workspace differs from the end-state recorded at finish")
    for path, info in record["files"].items():
        entry = observed.get(path, {})
        contents = decode(info["content_base64"])
        if (entry.get("sha256") != digest(contents) or entry.get("bytes") != len(contents)
                or entry.get("mode", 0) & 0o777 != info["mode"]):
            raise ValueError(f"workspace file evidence disagrees for {path}")


def verify_clock(record, budget):
    raw = record["recorded"]
    manifest = raw.get("run", {})
    trace = events(record)
    for clock in (raw.get("clock"), raw.get("budget-expired"), raw.get("checkpoint", {}).get("clock"),
                  *(event.get("clock") for event in trace)):
        if clock is None:
            continue
        phase = clock["phase_elapsed_seconds"]
        prefix = manifest.get("prefix_elapsed_seconds", 0)
        work = clock["worker_elapsed_seconds"]
        review = clock["reviewer_seconds"]
        total = clock["total_elapsed_seconds"]
        if (not all(type(value) in (int, float) and math.isfinite(value) and value >= 0
                    for value in (phase, prefix, work, review, total))
                or not math.isclose(phase + prefix, work, abs_tol=1e-6)
                or not math.isclose(work + review, total, abs_tol=1e-6)
                or review != manifest.get("reviewer_seconds", 0)
                or clock["within_budget"] != (total <= budget)):
            raise ValueError("recorded clock disagrees with the shared active budget")
    for event in trace:
        duration = event["seconds"] + event["status_seconds"]
        expected_elapsed = event["start"] + duration - raw["started"]["monotonic"]
        if not math.isclose(expected_elapsed, event["clock"]["phase_elapsed_seconds"], abs_tol=1e-6):
            raise ValueError("recorded event timing disagrees with the phase clock")


def summarize(schedule, data):
    groups = []
    totals = {}
    budget = schedule["active_budget_seconds"]
    for cell in schedule["cells"]:
        prefix, incumbent, fork, reviewer = (data[run_id] for run_id in allocated(cell))
        problems = matching(prefix, incumbent, fork, reviewer, cell, budget)
        marks = [branch["blind_grade"] for branch in (incumbent, fork) if branch["blind_grade"] is not None]
        sustained_labels = {mark["sustained_prefix_detour"] for mark in marks}
        group = {
            "prefix": cell["prefix"], "case": cell["case"], "assigned_model": cell["model"],
            "assigned_reasoning_effort": cell["effort"], "case_family": cell["case"].split("-")[0],
            "symptom_relevance": "required" if cell["case"].endswith("-b") else "incidental",
            "common_checkpoint": prefix["recorded"].get("checkpoint"),
            "prefix_progress": prefix["oracle"]["cutoff"].get("progress") if prefix["oracle"] else None,
            "prefix_sustained_detour": next(iter(sustained_labels)) if len(sustained_labels) == 1 else None,
            "prefix_grade_disagreement": len(sustained_labels) > 1,
            "prefix_grade_count": len(marks),
            "prefix_issue_exposure_counts": [
                len(mark["prefix_issue_exposure_indices"]) for mark in marks if "prefix_issue_exposure_indices" in mark
            ],
            "symptom_present_at_cutoff_labels": [
                mark["symptom_present_at_cutoff"] for mark in marks if "symptom_present_at_cutoff" in mark
            ],
            "match_problems": problems,
            "allocations": {},
        }
        for role, run_id in zip(("prefix", "incumbent", "fork", "reviewer"), allocated(cell)):
            record = data[run_id]
            disposition = status(record, role)
            totals[disposition] = totals.get(disposition, 0) + 1
            allocation = {
                "role": role, "status": disposition, "coordinator_status": record["provenance"].get("status"),
                "reason": record["provenance"].get("reason"), "snapshot_error": record["snapshot_error"],
            }
            if role in ("incumbent", "fork"):
                allocation["arm"] = "reviewer" if (role == "incumbent") == cell["review_incumbent"] else "unassisted"
                allocation["metrics"] = measure(record, prefix, budget)
                allocation["end_progress"] = record["oracle"]["end"].get("progress") if record["oracle"] else None
            group["allocations"][run_id] = allocation
        groups.append(group)
    by_model_and_relevance = {}
    for group in groups:
        key = f"{group['assigned_model']} / {group['symptom_relevance']}"
        counts = by_model_and_relevance.setdefault(key, {
            "planned_pairs": 0, "matched_pairs": 0, "matched_graded_pairs": 0,
            "planned_arms": {"reviewer": 0, "unassisted": 0},
            "verified_delivery": {"reviewer": 0, "unassisted": 0},
            "matched_graded_verified_delivery": {"reviewer": 0, "unassisted": 0},
        })
        counts["planned_pairs"] += 1
        matched = not group["match_problems"]
        graded = group["prefix_grade_count"] == 2
        counts["matched_pairs"] += matched
        counts["matched_graded_pairs"] += matched and graded
        for allocation in group["allocations"].values():
            if "arm" not in allocation:
                continue
            arm = allocation["arm"]
            delivered = allocation["metrics"]["verified_delivery"]
            counts["planned_arms"][arm] += 1
            counts["verified_delivery"][arm] += delivered
            counts["matched_graded_verified_delivery"][arm] += matched and graded and delivered
    return {
        "active_budget_seconds": budget,
        "planned_allocations": len(data),
        "planned_continuations": len(groups) * 2,
        "allocation_status_counts": totals,
        "scored_prefixes": sum(group["prefix_grade_count"] > 0 for group in groups),
        "confirmed_sustained_prefix_detours": sum(group["prefix_sustained_detour"] is True for group in groups),
        "by_model_and_symptom_relevance": by_model_and_relevance,
        "groups": groups,
        "limits": {
            "model": "Model and effort derive from launch arguments and documented full-history inheritance. "
                     "They are launcher evidence without independent provider attestation.",
            "timing": "First useful times end when the recorded shell action and status observation finish. "
                      "Worker time includes the common prefix. Charged time also includes the reviewer.",
            "grade": "Replay reruns independent fixture oracles and derives metrics from retained blind grades.",
        },
    }


def score(schedule, data, grades, verify=False):
    roles = ("prefix", "incumbent", "fork", "reviewer")
    for cell in schedule["cells"]:
        for role, run_id in zip(roles, allocated(cell)):
            record = data[run_id]
            verify_files(record, role)
            verify_clock(record, schedule["active_budget_seconds"])
            raw = record["recorded"]
            mark = grades.get(run_id)
            if mark and mark["first_consequential_action"] and mark["first_consequential_action"]["index"] == "reply":
                if "reply.txt" not in raw:
                    raise ValueError(f"{run_id}: a reply decision is marked but no reply was recorded")
            label = "cutoff" if role == "prefix" and "checkpoint" in raw else (
                "end" if role in ("incumbent", "fork") and "started" in raw else None
            )
            result = oracle(cell["case"], record["files"]) if label else None
            expected = {"blind_grade": mark, "oracle": {label: result} if result else None}
            if verify and any(record[key] != value for key, value in expected.items()):
                raise ValueError(f"{run_id}: replayed grading differs from the capture")
            record.update(expected)
    return summarize(schedule, data)


def capture(root, schedule, blind_dir, key_map, grades_path, output):
    data = inputs(root, schedule)
    mapping = read_json(key_map)
    marks = read_json(grades_path)
    expected = {run_id: cell for cell in schedule["cells"] for run_id in (cell["incumbent"], cell["fork"])
                if has_grading_evidence(data[run_id])}
    if (set(mapping.values()) != set(expected) or len(mapping) != len(expected)
            or set(mapping) != set(marks)
            or any(not OPAQUE_ID.fullmatch(blind_id) for blind_id in mapping)):
        raise ValueError("the blind key map and grades must cover each continuation with grading evidence")
    for blind_id, run_id in mapping.items():
        if read_json(blind_dir / f"{blind_id}.json") != packet(root, data, expected[run_id], run_id):
            raise ValueError(f"{blind_id}: blinded input differs from the recorded continuation")
        data[run_id]["blind_id"] = blind_id
    grades = {mapping[blind_id]: grade for blind_id, grade in marks.items()}
    summary = score(schedule, data, grades)
    empty_output(output)
    collection = {"version": VERSION, "schedule": schedule, "runs": data}
    write_json(output / "records.json", {**collection, "sha256": json_digest(collection)})
    write_json(output / "summary.json", summary)
    return summary


def replay(output):
    collection = read_json(output / "records.json")
    checksum = collection.pop("sha256")
    if json_digest(collection) != checksum or collection["version"] != VERSION:
        raise ValueError("long-horizon record checksum or version mismatch")
    data = collection["runs"]
    expected = {run_id for cell in collection["schedule"]["cells"] for run_id in allocated(cell)}
    if set(data) != expected:
        raise ValueError("replay records do not cover the frozen allocations")
    grades = {run_id: record["blind_grade"] for run_id, record in data.items() if record["blind_grade"] is not None}
    summary = score(collection["schedule"], data, grades, verify=True)
    if summary != read_json(output / "summary.json"):
        raise ValueError("recomputed study summary differs from the capture")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("blind", "capture", "replay"):
        command = actions.add_parser(action)
        command.add_argument("--output", required=True, type=Path)
        if action != "replay":
            command.add_argument("--runs-root", required=True, type=Path)
            command.add_argument("--key-map", required=True, type=Path)
            command.add_argument("--schedule", default=HERE / "long_schedule.json", type=Path)
        if action == "capture":
            command.add_argument("--blind-dir", required=True, type=Path)
            command.add_argument("--grades", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.action == "replay":
            result = replay(args.output)
        else:
            root, schedule = args.runs_root.resolve(), read_json(args.schedule)
            if args.action == "blind":
                result = blind(root, schedule, args.output, args.key_map)
            else:
                result = capture(root, schedule, args.blind_dir, args.key_map, args.grades, args.output)
    except (KeyError, OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
