"""Recheck captured file changes without running a model."""

import json
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import suite
from config.scope import (
    ALL_ARMS,
    ALL_REPEATED_INSTRUCTION_CASES,
    INSTRUCTION_REPEAT_COUNT,
    JSON_INDENT,
    NEXT_TURN,
)


class ReplayRunFatal(ValueError):
    """The captured evidence cannot support a replay grade."""


@dataclass(frozen=True)
class _InstructionTrial:
    case: str
    arm: str
    repeat: int
    trial: str
    instructions_digest: str
    changes_by_path: dict[str, str | None]
    all_missing_or_wrong: list[str]
    all_unexpected: list[str]
    is_report_passing: bool
    sender_hashes_by_path: dict[str, str] | None
    all_sender_guide_changes: list[str] | None
    sender_instructions_digest: str | None
    relay_digest: str | None


def _decode_trial(line: str) -> _InstructionTrial:
    capture = json.loads(line)
    return _InstructionTrial(
        case=capture["case"],
        arm=capture["arm"],
        repeat=capture["repeat"],
        trial=capture["trial"],
        instructions_digest=capture["instructions_sha256"],
        changes_by_path=capture["changes"],
        all_missing_or_wrong=capture["missing_or_wrong"],
        all_unexpected=capture["unexpected"],
        is_report_passing=capture["review"]["report_pass"],
        sender_hashes_by_path=capture.get("sender_file_sha256"),
        all_sender_guide_changes=capture.get("sender_guide_changes"),
        sender_instructions_digest=capture.get("sender_instructions_sha256"),
        relay_digest=capture.get("relay_sha256"),
    )


def _verify_relay(
    case: suite.ScopeCase, trial: _InstructionTrial, instructions_digest: str
) -> None:
    if "downstream" not in case:
        return
    source_hashes = {
        name: suite.digest(contents) for name, contents in suite.fixture(case).items()
    }
    handoff = trial.changes_by_path.get("handoff.md")
    if (
        source_hashes != trial.sender_hashes_by_path
        or trial.all_sender_guide_changes != []
        or trial.sender_instructions_digest != instructions_digest
        or handoff is None
        or suite.digest(handoff.encode()) != trial.relay_digest
    ):
        raise ReplayRunFatal(f"Sender state or relay differs in {trial.trial}")


def apply_captured_changes(work: Path, changes_by_path: dict[str, str | None]) -> None:
    """Rebuild the captured final file state in a prepared workspace.

    Args:
        work: The prepared workspace root.
        changes_by_path: Captured text writes and deletions by relative path.
    """
    for each_name, each_contents in changes_by_path.items():
        path = suite.safe_file(work, each_name)
        if each_contents is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(each_contents.encode())


def _replay_trial(case: suite.ScopeCase, trial: _InstructionTrial) -> suite.FileGrade:
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch) / "work"
        prepared = suite.prepare(case, trial.arm, work)
        _verify_relay(case, trial, prepared["instructions_sha256"])
        for each_turn in range(NEXT_TURN, len(case["turns"]) + 1):
            suite.stage(case, work, each_turn)
        if prepared["instructions_sha256"] != trial.instructions_digest:
            raise ReplayRunFatal(f"Instruction mismatch in {trial.trial}")
        apply_captured_changes(work, trial.changes_by_path)
        grade = suite.assess(case, trial.arm, work)
    if grade["missing_or_wrong"] != trial.all_missing_or_wrong:
        raise ReplayRunFatal(f"{trial.trial} differs on missing_or_wrong")
    if grade["unexpected"] != trial.all_unexpected:
        raise ReplayRunFatal(f"{trial.trial} differs on unexpected")
    return grade


def replay() -> dict[str, dict[str, int]]:
    """Verify the trial roster and recompute the instruction panel counts.

    Returns:
        The totals for each instruction arm and review metric.

    Raises:
        ReplayRunFatal: A trial is missing, duplicated, or inconsistent with its capture.
    """
    cases = suite.read_cases()
    counts: Counter[tuple[str, str]] = Counter()
    all_attempts: set[tuple[str, str, int]] = set()
    with (suite.ROOT / "instruction-outcomes.jsonl").open(encoding="utf-8") as evidence:
        for each_line in evidence:
            trial = _decode_trial(each_line)
            key = (trial.case, trial.arm, trial.repeat)
            if key in all_attempts:
                raise ReplayRunFatal(f"Duplicate trial {key}")
            all_attempts.add(key)
            grade = _replay_trial(cases[trial.case], trial)
            counts[trial.arm, "graded"] += 1
            counts[trial.arm, "requested_files"] += not grade["missing_or_wrong"]
            counts[trial.arm, "all_files"] += grade["file_checks_pass"]
            counts[trial.arm, "final_report"] += trial.is_report_passing
    all_planned = {
        (case, arm, repeat)
        for case in cases
        for arm in ALL_ARMS
        for repeat in range(
            1,
            (INSTRUCTION_REPEAT_COUNT if case in ALL_REPEATED_INSTRUCTION_CASES else 1)
            + 1,
        )
    }
    if all_attempts != all_planned:
        raise ReplayRunFatal(
            f"Trial roster differs: {sorted(all_attempts ^ all_planned)}"
        )
    return {
        arm: {
            metric: total for (label, metric), total in counts.items() if label == arm
        }
        for arm in ALL_ARMS
    }


def _write_replay(stream: TextIO) -> None:
    stream.write(json.dumps(replay(), indent=JSON_INDENT) + "\n")


if __name__ == "__main__":
    _write_replay(sys.stdout)
