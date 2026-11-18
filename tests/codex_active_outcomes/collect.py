"""Collect facility-owned acquisition logs and scoped operator reviews."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from active_eval.config import experiment
from active_eval.errors import EvidenceRunFatal
from active_study import digest


def allocations(records: Path) -> dict:
    """Load the controller's assignments across acquisition waves.

    Args:
        records: Directory of acquisition manifests.

    Returns:
        Orders keyed by their opaque identifiers.

    Raises:
        EvidenceRunFatal: The manifests are empty or contain duplicate orders.
    """
    manifests = [records / "manifest.json"] if (records / "manifest.json").is_file() else sorted(records.glob("*/manifest.json"))
    allocation = {}
    for each_manifest in manifests:
        for each_identity, each_info in json.loads(each_manifest.read_text()).items():
            if each_identity in allocation:
                raise EvidenceRunFatal("Order identity appears in multiple acquisition records")
            allocation[each_identity] = (each_info, each_manifest.parent / (each_identity + experiment.JSON_SUFFIX))
    if not allocation:
        raise EvidenceRunFatal("No facility records found")
    return allocation


def review_inputs(records: Path) -> list:
    """Prepare delivered notices for arm-blind review.

    Args:
        records: Directory holding the controller's manifests and journals.

    Returns:
        Delivered notice for each protected order.
    """
    notices = []
    for each_name, (each_metadata, each_path) in sorted(allocations(records).items()):
        case = experiment.ALL_CASES[each_metadata["case"]]
        if case["split"] == "protected":
            events = json.loads(each_path.read_text())["events"]
            delivery = next((event for event in events if event["reply"].get("recipient") == "exhibit steward"), None)
            notices.append({"id": each_name, "order": case["order"], "delivery": delivery})
    return notices


def collect(records: Path, work: Path, identities: Path, reviewed_inputs: Path, ratings: Path, destination: Path) -> None:
    """Bind assignments, participant inputs, receiving traces and notice reviews.

    Args:
        records: Directory of receiving journals.
        work: Directory of participant workspaces.
        identities: Operator's worker and continuation allocation.
        reviewed_inputs: Blinded notices given to the reviewer.
        ratings: Review keyed by opaque order identifier.
        destination: New directory for the public evidence.

    Raises:
        EvidenceRunFatal: Assignment, participant inputs or review cannot be verified.
    """
    client_sources = {each_name: digest((experiment.HERE / each_name).read_bytes()) for each_name in ("console.py", experiment.CONFIG_CLIENT)}
    allocation = allocations(records)
    workers = json.loads(identities.read_text())
    notice_ratings = json.loads(ratings.read_text())
    notices = {record["id"]: record["delivery"] for record in json.loads(reviewed_inputs.read_text())}
    if set(workers) != set(allocation):
        raise EvidenceRunFatal("Record one hosted worker identity for each staged order")
    destination.mkdir(exist_ok=False)
    rows = []
    launches = {}
    prompts = {}
    for each_name, (each_metadata, each_path) in allocation.items():
        row = json.loads(each_path.read_text())
        if any(row[field] != expected for field, expected in each_metadata.items()):
            raise EvidenceRunFatal("Desk metadata and allocation differ")
        participant = workers[each_name]
        row.update(participant)
        if set(participant) - {"worker", "resumed_worker"} or row["worker"] in launches:
            raise EvidenceRunFatal("Invalid hosted worker identity fields")
        launches[row["worker"]] = {field: row[field] for field in ("id", "arm", "case", "repeat")}
        prompts.setdefault(row["arm"], row["prompt_sha256"])
        root = work / each_name
        row["sources"] = {each_path: digest((root / each_path).read_bytes()) for each_path in ("AGENTS.md", "order.md", "desk.md", *client_sources)}
        case = experiment.ALL_CASES[row["case"]]
        brief = case["desk"] + experiment.DESK_USAGE
        if (row["sources"]["AGENTS.md"] != row["prompt_sha256"] or row["sources"]["order.md"] != row["order_sha256"]
                or row["sources"]["desk.md"] != digest(brief.encode()) or any(row["sources"][field] != signature for field, signature in client_sources.items())):
            raise EvidenceRunFatal("A worker's instructions, order or client changed")
        if case["split"] == "protected":
            delivered = next((event for event in row["events"] if event["reply"].get("recipient") == "exhibit steward"), None)
            if notices[each_name] != delivered:
                raise EvidenceRunFatal("The blinded reviewer received a different notice")
            notice_sha = hashlib.sha256(json.dumps(delivered, sort_keys=True).encode()).hexdigest() if delivered else None
            row["request_review"] = {**notice_ratings[each_name], "notice_sha256": notice_sha}
        rows.append(row)
    launch = {"runner": "Codex collaboration.spawn_agent, fork_turns=none", "model": experiment.WORKER_MODEL, "effort": experiment.REASONING_EFFORT,
              "source_revision": experiment.SOURCE_REVISION, "repeats": max(row["repeat"] for row in rows),
              "prompts": prompts, "client_inputs_sha256": client_sources, "case_sources_sha256": {file: digest((experiment.HERE / file).read_bytes()) for file in experiment.ALL_CASE_FILES}, "workers": launches}
    (destination / "launch.json").write_text(json.dumps(launch, indent=experiment.JSON_INDENT) + "\n")
    (destination / "receipts.jsonl").write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inputs = commands.add_parser("notices")
    inputs.add_argument("records", type=Path)
    capture = commands.add_parser("capture")
    for each_argument in ("records", "work", "identities", "reviewed_inputs", "ratings", "destination"):
        capture.add_argument(each_argument, type=Path)
    options = parser.parse_args()
    if options.command == "notices":
        json.dump(review_inputs(options.records), sys.stdout, indent=experiment.JSON_INDENT)
    else:
        collect(options.records, options.work, options.identities, options.reviewed_inputs, options.ratings, options.destination)
