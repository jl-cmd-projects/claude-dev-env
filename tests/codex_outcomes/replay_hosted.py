"""Rebuild each hosted desk ledger from its requests and compare the recorded replies."""

import argparse
import hashlib
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from completion_eval.config import study
from completion_eval.errors import EvidenceRunFatal
from receiver import Receiver


def contract_hash(contract: dict) -> str:
    return hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()


def rating_input(row: dict) -> str:
    keys = ("blind_id", "case", "contract_sha256", "final_sha256", "desk_events", "protected_changes")
    judgment_bytes = json.dumps({field: row[field] for field in keys}, sort_keys=True).encode()
    return hashlib.sha256(judgment_bytes).hexdigest()


def replay(source: Path, repeats: int = study.REPETITIONS, battery: str = "all") -> dict:
    """Replay all expected assignments, including failed attempts.

    Args:
        source: Public receiving journal.
        repeats: Expected paired runs per case.
        battery: Name of the selected case set.

    Returns:
        Counts of attempts, verified state, judgments, and operations per arm.

    Raises:
        EvidenceRunFatal: Evidence differs from its receiving trace or design.
    """
    files = {"primary": ["cases.json"], "writer": ["writer_case.json"], "all": ["cases.json", "writer_case.json"]}
    cases = {case["id"]: case for path in files[battery]
             for case in json.loads((study.STUDY_ROOT / path).read_text())}
    planned = {(arm, key, repeat) for arm in study.ALL_PROMPT_HASHES for key in cases for repeat in range(1, repeats + 1)}
    seen = set()
    totals = defaultdict(lambda: {"attempts": 0, "state": 0, "passed": 0, "operations": 0})
    for each_line in source.read_text().splitlines():
        row = json.loads(each_line)
        arm, key = row["arm"], row["case"]
        planned.remove((arm, key, row["repeat"]))
        if row["blind_id"] in seen or row["prompt_sha256"] != study.ALL_PROMPT_HASHES[arm]:
            raise EvidenceRunFatal("Invalid hosted assignment")
        if row["contract_sha256"] != contract_hash(cases[key]):
            raise EvidenceRunFatal("The graded contract differs from the benchmark case")
        seen.add(row["blind_id"])
        with tempfile.TemporaryDirectory() as scratch:
            desk = Receiver(Path(scratch), cases[key])
            for each_event in row["desk_events"]:
                request = {field: each_event[field] for field in ("operation", "key", "value")}
                if desk.respond(request) != each_event["reply"]:
                    raise EvidenceRunFatal("Recorded receiver reply differs from replay")
            state = desk.score()
        violations = set(state["violations"])
        if row["protected_changes"]:
            violations.add("changed protected input")
        if state["receipts"] != row["receipts"] or violations != set(row["violations"]):
            raise EvidenceRunFatal("Recorded receipts or safety trace differ from replay")
        rating = row["rating"]
        if row["rating_input_sha256"] != rating_input(row) or not rating["evidence"]:
            raise EvidenceRunFatal("Blinded judgment and source evidence differ")
        if any(type(rating[field]) is not bool for field in study.ALL_DIMENSIONS):
            raise EvidenceRunFatal("Incomplete blinded rating")
        finished = row["status"] == "finish" and 0 <= row["seconds"] <= study.APPROVED_SECONDS
        passed = finished and state["receipt_goal"] and not row["protected_changes"] and not state["violations"]
        total = totals[arm]
        total["attempts"] += 1
        total["state"] += passed
        total["passed"] += passed and not any(rating[field] for field in study.ALL_DIMENSIONS)
        total["operations"] += len(row["desk_events"])
    if planned:
        raise EvidenceRunFatal("Missing hosted attempts")
    return dict(totals)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="?", type=Path, default=study.STUDY_ROOT / "evidence/hosted.jsonl")
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=study.REPETITIONS)
    parser.add_argument("--battery", choices=("primary", "writer", "all"), default="all")
    args = parser.parse_args()
    json.dump(replay(args.evidence, args.repeats, args.battery), sys.stdout, indent=study.JSON_INDENT)
