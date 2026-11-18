"""Rebuild the 40 compaction file grades and delivered input hashes."""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import TextIO

import recall_driver
import suite
from config.scope import (
    ALL_ARMS,
    ALL_RECALL_REPEATS,
    ALL_RECEIPT_COHORTS,
    BASELINE_ARM,
    COMPACT_COHORT,
    JSON_INDENT,
    REPORT_KEY_SEPARATOR,
)
from replay import ReplayRunFatal, apply_captured_changes


@dataclass(frozen=True)
class _RecallTrial:
    case: str
    arm: str
    cohort: str
    repeat: int
    trial: str
    session_path: PurePosixPath
    receipt: dict[str, str]
    original_context_digest: str
    delivered_context_digest: str
    changes_by_path: dict[str, str | None]
    all_missing_or_wrong: list[str]
    all_unexpected: list[str]
    is_report_passing: bool


def _decode_trial(line: str) -> _RecallTrial:
    capture = json.loads(line)
    return _RecallTrial(
        case=capture["case"],
        arm=capture["arm"],
        cohort=capture["cohort"],
        repeat=capture["repeat"],
        trial=capture["trial"],
        session_path=PurePosixPath(capture["session_path"]),
        receipt=capture["receipt"],
        original_context_digest=capture["original_context_sha256"],
        delivered_context_digest=capture["delivered_context_sha256"],
        changes_by_path=capture["files"],
        all_missing_or_wrong=capture["missing_or_wrong"],
        all_unexpected=capture["unexpected"],
        is_report_passing=capture["review"]["report_pass"],
    )


def _verify_receipt(
    trial: _RecallTrial, common: bytes, instructions: bytes, summary: bytes
) -> None:
    delivered, _ = recall_driver.context_for_arm(common, trial.arm, trial.session_path)
    if trial.cohort == COMPACT_COHORT:
        hashes = {
            "AGENTS.md": suite.digest(instructions),
            "compact-context.txt": suite.digest(delivered),
            "summary.txt": suite.digest(summary),
        }
    else:
        hashes = {
            "startup.txt": suite.digest(
                b"\n\n".join((instructions, delivered, summary))
            )
        }
    if (
        hashes != trial.receipt
        or suite.digest(common) != trial.original_context_digest
        or suite.digest(delivered) != trial.delivered_context_digest
    ):
        raise ReplayRunFatal(f"Context or receipt differs for {trial.trial}")


def _replay_trial(
    case: recall_driver.RecallCase, trial: _RecallTrial
) -> suite.FileGrade:
    with TemporaryDirectory() as scratch:
        run = Path(scratch) / "session"
        prepared = recall_driver.prepare(case, BASELINE_ARM, run)
        common = Path(prepared["context"]).read_bytes()
        work = run / "work"
        _verify_receipt(
            trial, common, (work / "AGENTS.md").read_bytes(), case["summary"].encode()
        )
        apply_captured_changes(work, trial.changes_by_path)
        grade = suite.assess(case, BASELINE_ARM, work)
    if (
        grade["missing_or_wrong"] != trial.all_missing_or_wrong
        or grade["unexpected"] != trial.all_unexpected
    ):
        raise ReplayRunFatal(f"File grade differs for {trial.trial}")
    return grade


def replay() -> dict[str, int]:
    """Recompute recall panel totals after verifying the trial and receipt roster.

    Returns:
        Counts by delivery cohort, arm, and metric.

    Raises:
        ReplayRunFatal: A trial is missing, duplicated, or inconsistent with its capture.
    """
    cases = recall_driver.read_cases()
    counts: Counter[tuple[str, str, str]] = Counter()
    all_remaining = {
        (case, arm, cohort, repeat)
        for case in cases
        for arm in ALL_ARMS
        for cohort in ALL_RECEIPT_COHORTS
        for repeat in ALL_RECALL_REPEATS
    }
    with (suite.ROOT / "recall-outcomes.jsonl").open(encoding="utf-8") as records:
        for each_line in records:
            trial = _decode_trial(each_line)
            assignment = (trial.case, trial.arm, trial.cohort, trial.repeat)
            if assignment not in all_remaining:
                raise ReplayRunFatal(f"Unknown or duplicate trial: {assignment}")
            all_remaining.remove(assignment)
            grade = _replay_trial(cases[trial.case], trial)
            counts[trial.cohort, trial.arm, "graded"] += 1
            counts[trial.cohort, trial.arm, "files"] += grade["file_checks_pass"]
            counts[trial.cohort, trial.arm, "final"] += trial.is_report_passing
    if all_remaining:
        raise ReplayRunFatal(f"Missing trials: {sorted(all_remaining)}")
    return {
        REPORT_KEY_SEPARATOR.join(key): total for key, total in sorted(counts.items())
    }


def _write_replay(stream: TextIO) -> None:
    stream.write(json.dumps(replay(), indent=JSON_INDENT) + "\n")


if __name__ == "__main__":
    _write_replay(sys.stdout)
