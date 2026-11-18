"""Prepare arm-masked trace packets and independently regrade archived queue runs."""

import argparse
import json
import re
import secrets
from pathlib import Path

from long_proof import ARM_DISCLOSURE
from proof import read_json
from queue_run import events, grade, replay
from trial import PIN, write_json


HERE = Path(__file__).resolve().parent
ROLES = ("prefix", "incumbent", "fork")
ACTION_LABELS = ("diversions", "repeated_no_progress", "necessary_waits")


def sampled():
    return read_json(HERE / "queue_schedule.json")["cells"]


def observed_runs(root):
    for cell in sampled():
        for role in ROLES:
            directory = root / cell[role]
            if (directory / "started.json").is_file():
                yield cell, role, directory


def scrub(value, directory):
    value = value.replace(str(directory / "work"), "<workspace>").replace(str(directory), "<run>")
    receipt = directory / "reviewer-receipt.json"
    if receipt.is_file():
        advice = read_json(receipt)["advice"]
        if advice.strip():
            value = value.replace(advice.strip(), "<masked>")
    return ARM_DISCLOSURE.sub("<masked>", re.sub(r"\b[qcv]\d{3}\b", "<run>", value))


def packet(directory):
    def safe_actions(rows):
        return [
            {key: scrub(event[key], directory) if isinstance(event[key], str) else event[key]
             for key in ("command", "stdout", "stderr", "status", "exit", "seconds", "service_age_seconds")
             if key in event}
            for event in rows
        ]
    prefix_file = directory / "prefix-events.jsonl"
    history = [json.loads(line) for line in prefix_file.read_text().splitlines()] if prefix_file.exists() else []
    reply = directory / "reply.txt"
    return {
        "goal": (directory / "task.txt").read_text(), "prior_actions": safe_actions(history),
        "status_at_start": read_json(directory / "started.json")["initial_observation"]["status"],
        "actions": safe_actions(events(directory)),
        "final_answer": scrub(reply.read_text(), directory) if reply.exists() else None,
    }


def blind(root, destination):
    destination.mkdir(parents=True, exist_ok=False)
    key_path = root / "blind-key.json"
    if key_path.exists():
        raise ValueError("The grading key already exists.")
    keys = {}
    for _, _, directory in observed_runs(root):
        key = secrets.token_hex(12)
        write_json(destination / (key + ".json"), packet(directory))
        keys[key] = directory.name
    write_json(key_path, keys)


def run_summary(directory, mark):
    result = replay(directory)
    manifest = result["manifest"]
    if manifest["pin"] != PIN or manifest["budget_seconds"] != 1500:
        raise ValueError("Unexpected baseline or time budget.")
    trace = events(directory)
    receipt = next((i for i, event in enumerate(trace, 1)
                    if event["observation"]["relevance"] in ("optional", "required")), None)
    if manifest["phase"] == "continuation":
        receipt = 0
    first = mark["first_useful_after_receipt"]
    first_decision = mark["first_consequential_after_receipt"]
    for index in (first, first_decision):
        if index is not None and (type(index) is not int or receipt is None or not receipt < index <= len(trace)):
            raise ValueError("First action precedes the receipt or falls outside the trace.")
    if first and first_decision and first < first_decision:
        raise ValueError("Useful action precedes the first consequential action.")
    actions = {}
    for field in ACTION_LABELS:
        indices = mark[field]
        if len(set(indices)) != len(indices) or any(type(i) is not int or not 1 <= i <= len(trace) for i in indices):
            raise ValueError("Invalid action indices for " + field)
        actions[field] = {"indices": indices, "shell_seconds": round(sum(trace[i - 1]["seconds"] for i in indices), 3)}
    for field in ("sustained_detour", "verification_ok", "false_done", "missed_dependency"):
        if type(mark[field]) is not bool:
            raise ValueError("Missing boolean grade for " + field)
    first_time = trace[first - 1]["clock"]["total_elapsed_seconds"] if first else None
    origin = None
    if receipt:
        origin = trace[receipt - 1]["clock"]["total_elapsed_seconds"]
    elif receipt == 0:
        origin = read_json(directory / "prefix-checkpoint.json")["clock"]["worker_elapsed_seconds"]
    end = result["outcome"]
    oracle = grade(directory) if end else None
    return {
        "outcome": end["outcome"] if end else "checkpoint", "clock": end["clock"] if end else None,
        "shell_calls": len(trace), "shell_seconds": round(sum(e["seconds"] for e in trace), 3),
        "first_receipt_observation": receipt, "receipt_active_seconds": origin,
        "first_consequential_after_receipt": first_decision, "first_useful_after_receipt": first,
        "charged_seconds_receipt_to_useful": round(first_time - origin, 3) if first_time is not None else None,
        "eligibility_actions": result["eligible_actions"], **actions,
        "grade": mark, "artifact_oracle": oracle,
    }


def summarize(root):
    marks = read_json(root / "grades.json")
    keys = read_json(root / "blind-key.json")
    provenance = read_json(root / "provenance.json")
    if set(marks) != set(keys) or len(set(keys.values())) != len(keys):
        raise ValueError("Grader and key coverage differ.")
    grades = {keys[k]: v for k, v in marks.items()}
    outcomes = {}
    for cell, role, directory in observed_runs(root):
        name = directory.name
        if name not in grades or name not in provenance:
            raise ValueError("Missing grade or launch record for " + name)
        record = provenance[name]
        if role == "prefix" and (record["launch"]["model"] != cell["model"]
                                 or record["launch"]["reasoning_effort"] != cell["effort"]
                                 or record["launch_receipt"]["task_name"] != "/root/" + name):
            raise ValueError("Prefix launch differs from its schedule.")
        outcomes[name] = {"case": cell["case"], "model": cell["model"], "role": role,
                          **run_summary(directory, grades[name])}
    if set(outcomes) != set(grades):
        raise ValueError("Graded runs and recorded launches differ.")
    allocations = {}
    for cell in sampled():
        prefix = cell["prefix"]
        if prefix not in provenance:
            raise ValueError("Missing prefix launch record for " + prefix)
        triggered = bool(outcomes.get(prefix, {}).get("eligibility_actions"))
        for role in (*ROLES, "reviewer"):
            name = cell[role]
            if name in outcomes:
                status = outcomes[name]["outcome"]
            elif name in provenance:
                status = provenance[name]["status"]
            else:
                status = "missing-after-trigger" if triggered else "not-triggered"
            allocations[name] = {"role": role, "prefix": prefix, "status": status}
    return {"schedule": sampled(), "provenance": provenance, "allocations": allocations,
            "observed_runs": outcomes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    blinded = commands.add_parser("blind")
    blinded.add_argument("root", type=Path)
    blinded.add_argument("destination", type=Path)
    scored = commands.add_parser("replay")
    scored.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.action == "blind":
        blind(args.root, args.destination)
    else:
        print(json.dumps(summarize(args.root), indent=2))


if __name__ == "__main__":
    main()
