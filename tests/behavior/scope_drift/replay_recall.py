"""Rebuild the 40 compaction file grades and delivered input hashes."""

import json
from collections import Counter
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

import recall_driver
import suite


def replay():
    cases = recall_driver.read_cases()
    counts = Counter()
    roster = {
        (case, arm, cohort, repeat)
        for case in cases
        for arm in ("baseline", "candidate")
        for cohort in ("neutral", "compact")
        for repeat in (1, 2)
    }
    with (suite.ROOT / "recall-outcomes.jsonl").open(encoding="utf-8") as records:
        for line in records:
            row = json.loads(line)
            case = cases[row["case"]]
            arm, cohort = row["arm"], row["cohort"]
            roster.remove((case["id"], arm, cohort, row["repeat"]))
            with TemporaryDirectory() as scratch:
                run = Path(scratch) / "session"
                meta = recall_driver.prepare(case, "baseline", run)
                common = Path(meta["context"]).read_bytes()
                delivered, _ = recall_driver.context_for_arm(
                    common, arm, PurePosixPath(row["session_path"])
                )
                summary = case["summary"].encode()
                sol = (run / "work/AGENTS.md").read_bytes()
                hashes = (
                    {
                        "AGENTS.md": suite.digest(sol),
                        "compact-context.txt": suite.digest(delivered),
                        "summary.txt": suite.digest(summary),
                    }
                    if cohort == "compact"
                    else {
                        "startup.txt": suite.digest(
                            b"\n\n".join((sol, delivered, summary))
                        )
                    }
                )
                if (
                    hashes != row["receipt"]
                    or suite.digest(common) != row["original_context_sha256"]
                    or suite.digest(delivered) != row["delivered_context_sha256"]
                ):
                    raise ValueError(f"Context or receipt differs for {row['trial']}")
                for name, contents in row["files"].items():
                    path = suite.safe_file(run / "work", name)
                    if contents is None:
                        path.unlink()
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(contents.encode())
                checks = suite.assess(case, "baseline", run / "work")
                for key in ("unexpected", "missing_or_wrong"):
                    if checks[key] != row[key]:
                        raise ValueError(f"File grade differs for {row['trial']}")
                counts[cohort, arm, "graded"] += 1
                counts[cohort, arm, "files"] += checks["file_checks_pass"]
                counts[cohort, arm, "final"] += row["review"]["report_pass"]
    if roster:
        raise ValueError(f"Missing trials: {sorted(roster)}")
    return {" ".join(key): total for key, total in sorted(counts.items())}


if __name__ == "__main__":
    print(json.dumps(replay(), indent=2))
