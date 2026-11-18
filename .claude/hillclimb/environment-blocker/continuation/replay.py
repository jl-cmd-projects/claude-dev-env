"""Replay four status-only hosted Codex continuation cells."""

import hashlib
import json
import sys
from pathlib import Path
from typing import TextIO

from continuation.config.continuation_grading_constants import ALL_APPROVAL_TEXT_BY_STATUS
from continuation.config.continuation_replay_constants import (
    ALL_ARMS,
    BASELINE_LAUNCH_PATH,
    CONTINUATION_CASES_PATH,
    CONTINUATION_EVIDENCE_PATH,
    LAUNCH_MESSAGE_SHA256,
    ORDER_SHA256,
)
from continuation.grade import JsonRow, grade


StudyCell = tuple[str, str]


class ContinuationReplayRunFatal(ValueError):
    """The four-cell study cannot be scored from the supplied receipts."""


def _check_launch(receipt: JsonRow, instructions_by_arm: dict[str, str]) -> tuple[str, str]:
    arm, approval = receipt["arm"], receipt["status"]
    cell = (arm, approval)
    controller = receipt["controller"]
    if (controller["arm"], controller["status"]) != cell:
        raise ContinuationReplayRunFatal(f"Controller assignment mismatch for {cell}")
    launch = controller["launch"]
    if hashlib.sha256(launch["message"].encode()).hexdigest() != LAUNCH_MESSAGE_SHA256:
        raise ContinuationReplayRunFatal(f"Launch prompt digest mismatch for {cell}")
    if launch["order_sha256"] != ORDER_SHA256:
        raise ContinuationReplayRunFatal(f"Staged order digest mismatch for {cell}")
    if launch["instructions_sha256"] != instructions_by_arm[arm]:
        raise ContinuationReplayRunFatal(f"Instruction digest mismatch for {cell}")
    journal = json.dumps(receipt["events"], sort_keys=True, separators=(",", ":"), allow_nan=False)
    return controller["worker"], hashlib.sha256(journal.encode()).hexdigest()


def _score(case: JsonRow, receipt: JsonRow, cell: StudyCell) -> JsonRow:
    report = grade(case, receipt["events"], receipt["state"], receipt["controller"], receipt["review"])
    if report["status"] == "invalid_evidence":
        raise ContinuationReplayRunFatal(f"Invalid evidence for {cell}: {report['evidence_error']}")
    if report["status"] not in {"pass", "fail"} or report["needs_review"]:
        raise ContinuationReplayRunFatal(f"Inconclusive evidence for {cell}: {report['needs_review']}")
    return {"arm": cell[0], "approval_status": cell[1], **report}


def _score_matrix(all_receipts: list[JsonRow], case: JsonRow, instructions_by_arm: dict[str, str]) -> list[JsonRow]:
    remaining = {(arm, approval) for arm in ALL_ARMS for approval in ALL_APPROVAL_TEXT_BY_STATUS}
    all_workers, all_journals, all_scores = set(), set(), []
    for each_receipt in all_receipts:
        cell = (each_receipt["arm"], each_receipt["status"])
        if cell not in remaining:
            raise ContinuationReplayRunFatal(f"Unexpected or duplicate cell: {cell}")
        remaining.remove(cell)
        worker, journal_digest = _check_launch(each_receipt, instructions_by_arm)
        if worker in all_workers:
            raise ContinuationReplayRunFatal(f"Repeated worker for {cell}: {worker}")
        if journal_digest in all_journals:
            raise ContinuationReplayRunFatal(f"Repeated service journal for {cell}")
        all_workers.add(worker)
        all_journals.add(journal_digest)
        all_scores.append(_score(case, each_receipt, cell))
    if remaining:
        raise ContinuationReplayRunFatal(f"Missing continuation cells: {sorted(remaining)}")
    return all_scores


def replay(evidence_path: Path = CONTINUATION_EVIDENCE_PATH) -> list[JsonRow]:
    """Score the complete, matched four-cell study.

    Args:
        evidence_path: JSONL file of controller, service and review receipts.

    Returns:
        An arm, approval status, and grade for each distinct cell.

    Raises:
        ContinuationReplayRunFatal: Receipts are missing, inconsistent or inconclusive.
    """
    try:
        all_lines = evidence_path.read_text(encoding="utf-8").splitlines()
        all_receipts = [json.loads(line) for line in all_lines]
        case, = json.loads(CONTINUATION_CASES_PATH.read_text(encoding="utf-8"))["cases"]
        launch = json.loads(BASELINE_LAUNCH_PATH.read_text(encoding="utf-8"))
        return _score_matrix(all_receipts, case, launch["arm_instructions_sha256"])
    except ContinuationReplayRunFatal:
        raise
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as error:
        raise ContinuationReplayRunFatal(f"Cannot replay {evidence_path}: {error}") from error


def _write_scores(stream: TextIO) -> None:
    for each_score in replay():
        stream.write(json.dumps(each_score, sort_keys=True) + "\n")


if __name__ == "__main__":
    try:
        _write_scores(sys.stdout)
    except ContinuationReplayRunFatal as error:
        raise SystemExit(str(error)) from error
