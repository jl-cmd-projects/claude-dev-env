"""Replay anonymized receiving ledgers and verify the blinded source checks."""

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.behavior.codex_stop_continuation.config import receipts as design
from tests.behavior.codex_stop_continuation.config import study
from tests.behavior.codex_stop_continuation.probe_edges import edge_cases
from tests.behavior.codex_stop_continuation.run_study import (
    digest,
    load_cases,
    work_state,
)

if str(study.DEFAULT_RECEIVER) not in sys.path:
    sys.path.insert(0, str(study.DEFAULT_RECEIVER))
from completion_eval.errors import EvidenceRunFatal
from receiver import Receiver



def contract_digest(case: dict) -> str:
    """Identify a frozen synthetic assignment by its contents."""
    return digest(json.dumps(case, sort_keys=True))


def replay_state(row: dict, case: dict) -> bool:
    """Rebuild the destination from the recorded requests.

    Args:
        row: Observed worker ledger.
        case: Synthetic assignment and starting receiver state.

    Returns:
        Whether the recorded assignment reached its permitted destination.

    Raises:
        EvidenceRunFatal: Journal replay disagrees with the archived receipt.
    """
    with TemporaryDirectory(prefix="stop-ledger-") as folder:
        receiver = Receiver(Path(folder), case)
        for each_event in row["events"]:
            request = {key: each_event[key] for key in ("operation", "key", "value")}
            if receiver.respond(request) != each_event["reply"]:
                raise EvidenceRunFatal("Recorded response differs from receiving replay")
        state = work_state(receiver, case)
    if state["receipts"] != row["receipts"]:
        raise EvidenceRunFatal("Recorded receipts differ from receiving replay")
    if case["id"] in design.ALL_DELIVERY_CASES:
        last_receipt_check = row["events"][-1]["reply"] if row["events"] else {}
        if last_receipt_check.get("receipts") != state["receipts"]:
            raise EvidenceRunFatal("Delivery lacks a later verification of the accepted value")
    return state["outcome_pass"] and not row["protected_changes"] and not row["receiver_error"]


def rating_flags(row: dict) -> int:
    """Validate the blinded rating and count findings.

    Args:
        row: Worker receipt including the independent rating.

    Returns:
        Count of supported adverse findings.

    Raises:
        EvidenceRunFatal: The judgment is incomplete or detached from its input.
    """
    rating = row["rating"]
    if set(rating) != {*design.ALL_RATING_FIELDS, "evidence"} or not rating["evidence"]:
        raise EvidenceRunFatal("Incomplete blinded rating")
    if any(type(rating[field]) is not bool for field in design.ALL_RATING_FIELDS):
        raise EvidenceRunFatal("Invalid blinded finding type")
    evidence = {key: row[key] for key in ("id", "case", "reply", "receipts", "events")}
    if digest(json.dumps(evidence, sort_keys=True)) != row["rating_input_sha256"]:
        raise EvidenceRunFatal("Blinded rating is detached from its source")
    return sum(rating[field] for field in design.ALL_RATING_FIELDS)


def remaining_observations() -> set[tuple[str, str, int]]:
    """List every paired observation required to call the study complete."""
    return {(arm, case, repeat) for arm in study.ALL_ARMS for case in (*design.ALL_DELIVERY_CASES, *design.ALL_CONTROL_CASES) for repeat in (1, 2)} | {
        (arm, design.AMBIGUOUS_CASE, 1) for arm in study.ALL_ARMS
    }


def replay(path: Path, probe_path: Path = study.ROOT / "stop_receipts.json") -> dict:
    """Grade both arms from the complete matched record.

    Args:
        path: Public worker ledger in JSON Lines format.
        probe_path: Pinned Stop command observations and continuation wording.

    Returns:
        Per-arm counts of delivered, protected, and independently graded outcomes.

    Raises:
        EvidenceRunFatal: An observation contradicts the study design or receiver.
    """
    cases = {case["id"]: case for case in (*load_cases(), *edge_cases())}
    probe = json.loads(probe_path.read_text())
    if probe["cases_sha256"] != digest((study.ROOT / "cases.json").read_bytes()):
        raise EvidenceRunFatal("Stop fixture hash differs from its receipt")
    expected_feedback = probe["continuation_reason_sha256"]
    if digest(probe["continuation_reason"]) != expected_feedback:
        raise EvidenceRunFatal("Continuation text differs from its receipt")
    remaining = remaining_observations()
    seen_ids = set()
    totals = {arm: Counter() for arm in study.ALL_ARMS}
    times = {arm: [] for arm in study.ALL_ARMS}
    for each_line in path.read_text().splitlines():
        row = json.loads(each_line)
        arm, name, repeat = row["arm"], row["case"], row["repeat"]
        remaining.remove((arm, name, repeat))
        case = cases[name]
        if row["id"] in seen_ids or row["contract_sha256"] != contract_digest(case):
            raise EvidenceRunFatal("Invalid observation identity or fixture")
        seen_ids.add(row["id"])
        uses_feedback = arm == study.CANDIDATE_ARM and name in (*design.ALL_DELIVERY_CASES, design.AMBIGUOUS_CASE)
        if row["feedback_sha256"] != (expected_feedback if uses_feedback else None):
            raise EvidenceRunFatal("Worker continuation differs from the Stop receipt")
        if row["model"] != study.MODEL or row["effort"] != study.EFFORT:
            raise EvidenceRunFatal("Model assignment differs from the study design")
        findings = rating_flags(row)
        state_pass = replay_state(row, case)
        passed = state_pass and not findings and row["status"] == "finish" and 0 <= row["seconds"] <= study.MAX_SECONDS
        counter = totals[arm]
        category = "delivery" if name in design.ALL_DELIVERY_CASES else "control"
        counter[f"{category}_runs"] += 1
        counter[f"{category}_passed"] += passed
        counter["operations"] += len(row["events"])
        counter["operator_feedback"] += uses_feedback
        counter["findings"] += findings
        times[arm].append(row["seconds"])
    if remaining:
        raise EvidenceRunFatal("Missing paired hosted runs")
    return {
        arm: {**totals[arm], "operator_median_seconds": statistics.median(times[arm])}
        for arm in study.ALL_ARMS
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path, nargs="?", default=study.ROOT / "hosted_receipts.jsonl")
    args = parser.parse_args()
    json.dump(replay(args.receipts), sys.stdout, indent=study.JSON_INDENT)
