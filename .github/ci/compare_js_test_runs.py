"""Compare Node spec reports without accepting a speedup from missing tests."""

import argparse
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Report:
    counts: dict[str, int]
    passed_names: Counter[str]
    duration_ms: float


def read_report(path: Path) -> Report:
    text = path.read_text(encoding="utf-8-sig")
    counts = {
        match[1]: int(match[2])
        for match in re.finditer(
            r"^\u2139 (tests|pass|fail|cancelled|skipped|todo) (\d+)$", text, re.MULTILINE
        )
    }
    duration = re.search(r"^\u2139 duration_ms ([\d.]+)$", text, re.MULTILINE)
    passed_names = Counter(
        re.findall(r"^\u2714 (.+) \([\d.]+ms\)$", text, re.MULTILINE)
    )
    if len(counts) != 6 or duration is None or not counts.get("tests"):
        raise ValueError(f"{path}: missing test summary")
    if counts["fail"] or counts["cancelled"]:
        raise ValueError(f"{path}: failed or cancelled tests")
    if sum(passed_names.values()) != counts["pass"]:
        raise ValueError(f"{path}: incomplete passed-test names")
    duration_ms = float(duration[1])
    if duration_ms <= 0:
        raise ValueError(f"{path}: duration must be positive")
    return Report(counts, passed_names, duration_ms)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--max-ratio", type=float, default=0.5)
    args = parser.parse_args()
    if not 0 < args.max_ratio <= 1:
        parser.error("--max-ratio must be greater than zero and at most one")
    try:
        before = read_report(args.before)
        after = read_report(args.after)
        if before.counts != after.counts or before.passed_names != after.passed_names:
            raise ValueError("test counts or passed-test names changed")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    ratio = after.duration_ms / before.duration_ms
    print(f"Same {after.counts['tests']} tests, {after.counts['pass']} passed")
    print(f"Before {before.duration_ms / 1000:.2f}s, after {after.duration_ms / 1000:.2f}s")
    print(f"Duration ratio {ratio:.3f}, limit {args.max_ratio:.3f}")
    return int(ratio > args.max_ratio)


if __name__ == "__main__":
    raise SystemExit(main())
