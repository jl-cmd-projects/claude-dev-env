"""Recheck captured file changes without running a model."""

import json
import tempfile
from collections import Counter
from pathlib import Path

import suite


def verify_relay(case, row, instructions_digest):
    if "downstream" not in case:
        return
    source_files = {
        name: suite.digest(contents) for name, contents in suite.fixture(case).items()
    }
    if (
        source_files != row["sender_file_sha256"]
        or row["sender_guide_changes"]
        or row["sender_instructions_sha256"] != instructions_digest
        or suite.digest(row["changes"]["handoff.md"].encode()) != row["relay_sha256"]
    ):
        raise ValueError(f"Sender state or relay differs in {row['trial']}")


def replay():
    cases = suite.read_cases()
    count = Counter()
    attempts = set()
    with (suite.ROOT / "instruction-outcomes.jsonl").open(encoding="utf-8") as evidence:
        for line in evidence:
            row = json.loads(line)
            case = cases[row["case"]]
            arm = row["arm"]
            key = (row["case"], arm, row["repeat"])
            if key in attempts:
                raise ValueError(f"Duplicate trial {key}")
            attempts.add(key)
            with tempfile.TemporaryDirectory() as scratch:
                work = Path(scratch) / "work"
                prepared = suite.prepare(case, arm, work)
                verify_relay(case, row, prepared["instructions_sha256"])
                for turn in range(2, len(case["turns"]) + 1):
                    suite.stage(case, work, turn)
                if prepared["instructions_sha256"] != row["instructions_sha256"]:
                    raise ValueError(f"Instruction mismatch in {key}")
                for name, contents in row["changes"].items():
                    path = suite.safe_file(work, name)
                    if contents is None:
                        path.unlink()
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(contents.encode())
                grade = suite.assess(case, arm, work)
                for metric in ("missing_or_wrong", "unexpected"):
                    if grade[metric] != row[metric]:
                        raise ValueError(f"{key} differs on {metric}")
                count[arm, "graded"] += 1
                count[arm, "requested_files"] += not grade["missing_or_wrong"]
                count[arm, "all_files"] += grade["file_checks_pass"]
                count[arm, "final_report"] += row["review"]["report_pass"]
    repeated = {"cutover", "interrupted", "badge-desk", "dispatch-desk"}
    planned = {
        (case, arm, repeat)
        for case in cases
        for arm in ("baseline", "candidate")
        for repeat in range(1, 3 if case in repeated else 2)
    }
    if attempts != planned:
        raise ValueError(f"Trial roster differs: {sorted(attempts ^ planned)}")
    return {
        arm: {metric: total for (label, metric), total in count.items() if label == arm}
        for arm in ("baseline", "candidate")
    }


if __name__ == "__main__":
    print(json.dumps(replay(), indent=2))
