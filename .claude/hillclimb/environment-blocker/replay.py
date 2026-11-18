"""Score every recorded session with its receipt-bound blind review."""

import hashlib
import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import TextIO

from config.replay_constants import ALL_ARCHIVE_FILENAMES, ALL_CASE_FILENAMES, EVIDENCE, FIXTURE_ROOT
from grade import grade


class ReplayRunFatal(ValueError):
    """The archive lacks evidence required for a replay score."""


@dataclass(frozen=True)
class _Receipt:
    arm: str
    case: str
    events: list[dict[str, object]]
    state: dict[str, object]
    repeat: str | None


def _decode_receipt(line: str) -> _Receipt:
    archive = json.loads(line)
    return _Receipt(archive["arm"], archive["case"], archive["events"], archive["state"], archive.get("repeat"))


def _hashes_by_assignment(order_by_name: Mapping[str, Mapping[str, object]]) -> dict[tuple[str, str], str]:
    hashes_by_assignment = {}
    for each_name, each_order in order_by_name.items():
        hashes_by_arm = each_order.get("receipt_sha256_by_arm")
        workers_by_arm = each_order.get("worker_by_arm")
        if not isinstance(hashes_by_arm, dict) or not isinstance(workers_by_arm, dict):
            raise ReplayRunFatal(f"Missing receipt hashes or worker assignments for {each_name}")
        if hashes_by_arm.keys() != workers_by_arm.keys():
            raise ReplayRunFatal(f"Receipt hashes do not match assignments for {each_name}")
        hashes_by_assignment.update({(each_name, arm): digest for arm, digest in hashes_by_arm.items()})
    if len(set(hashes_by_assignment.values())) != len(hashes_by_assignment):
        raise ReplayRunFatal("Duplicate receipt hash in launch manifest")
    return hashes_by_assignment


def _receipt_hash(receipt: _Receipt) -> str:
    capture = {"events": receipt.events, "state": receipt.state}
    encoded_capture = json.dumps(capture, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded_capture).hexdigest()


def _verified_receipts(order_by_name: Mapping[str, Mapping[str, object]]) -> list[_Receipt]:
    remaining = _hashes_by_assignment(order_by_name)
    receipts = [
        _decode_receipt(line)
        for filename in ALL_ARCHIVE_FILENAMES
        for line in (EVIDENCE / filename).read_text(encoding="utf-8").splitlines()
    ]
    for each_receipt in receipts:
        assignment = (each_receipt.repeat or each_receipt.case, each_receipt.arm)
        if assignment not in remaining:
            raise ReplayRunFatal(f"Unknown or duplicate assignment: {assignment}")
        if _receipt_hash(each_receipt) != remaining.pop(assignment):
            raise ReplayRunFatal(f"Receipt hash mismatch for {assignment}")
    if remaining:
        raise ReplayRunFatal(f"Missing assignments: {sorted(remaining)}")
    return receipts


def _catalog_reads_before_contact(
    receipt: _Receipt, all_sources: Sequence[str], first_contact: int | None
) -> int:
    count = 0
    for each_event in receipt.events:
        sequence = each_event["seq"]
        if (
            each_event["operation"] == "read"
            and each_event["target"] in all_sources
            and (first_contact is None or (isinstance(sequence, int) and sequence < first_contact))
        ):
            count += 1
    return count


def _grade_receipt(
    receipt: _Receipt, case_by_field: dict[str, object], review_by_hash: dict[str, dict[str, object]]
) -> dict[str, object]:
    inventory = grade(case_by_field, receipt.events, receipt.state)
    if inventory["status"] == "invalid_evidence":
        raise ReplayRunFatal(f"Invalid evidence for {receipt.case} / {receipt.arm}: {inventory}")
    deliveries = inventory["notifications"] + inventory["completion_update_candidates"]
    selected = [review_by_hash[entry["message_sha256"]] for entry in deliveries]
    score = grade(case_by_field, receipt.events, receipt.state, {"reviews": selected})
    stage = case_by_field.get("stage")
    if isinstance(stage, dict):
        first_contact = score["metrics"]["first_actionable_notification_seq"]
        score["metrics"]["catalog_reads_before_contact"] = _catalog_reads_before_contact(
            receipt, stage["sources"], first_contact
        )
    return {"arm": receipt.arm, "repeat": receipt.repeat or 1, **score}


def replay() -> Iterator[dict[str, object]]:
    """Yield one score per verified assignment.

    Yields:
        A score with notification and fixture metrics for a session.

    Raises:
        ReplayRunFatal: A receipt is missing, duplicated, misassigned, or invalid.
    """
    cases = {
        case["id"]: case
        for filename in ALL_CASE_FILENAMES
        for case in json.loads((FIXTURE_ROOT / filename).read_text(encoding="utf-8"))["cases"]
    }
    reviews = {
        review["message_sha256"]: review
        for review in json.loads((EVIDENCE / "semantic-review.json").read_text(encoding="utf-8"))
    }
    orders = json.loads((EVIDENCE / "launch.json").read_text(encoding="utf-8"))["work_orders"]
    for each_receipt in _verified_receipts(orders):
        yield _grade_receipt(each_receipt, cases[each_receipt.case], reviews)


def _write_scores(stream: TextIO) -> None:
    for each_score in replay():
        stream.write(json.dumps(each_score, sort_keys=True) + "\n")


if __name__ == "__main__":
    _write_scores(sys.stdout)
