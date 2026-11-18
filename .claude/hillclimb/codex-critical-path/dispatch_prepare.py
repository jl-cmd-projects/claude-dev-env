"""Prepare a pressure decision with the exact portable instruction under test."""

import argparse
from pathlib import Path

import draft_run
import pressure_run
from proof import pinned_baseline, read_json
from trial import HERE, digest, write_json


def pressure_presentation(prefix, arm):
    history, historical_instructions = draft_run.presentation(prefix, "baseline")
    plan = read_json(HERE / "dispatch_schedule.json")
    baseline = pinned_baseline(plan["pin"]).encode()
    extra = (HERE / "dispatch_candidate.txt").read_bytes().strip() if arm == "candidate" else None
    instructions = pressure_run.instructions_for(baseline, extra)
    if not history.startswith(historical_instructions):
        raise ValueError("The visible background differs from the archived instructions.")
    return instructions + history[len(historical_instructions):], instructions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("sources", type=Path)
    args = parser.parse_args()
    args.root.mkdir(exist_ok=False)
    plan = read_json(HERE / "dispatch_schedule.json")
    expected_sources = read_json(HERE / "signal_schedule.json")["source_digests"]
    for row in plan["development"]:
        source = args.sources / row["case"]
        run = args.root / row["id"]
        for name, expected in expected_sources[row["case"]].items():
            if digest((source / name).read_bytes()) != expected:
                raise ValueError("The supplied prior trajectory is not the frozen source.")
        pressure_run.recover(source, run)
        data, instructions = pressure_presentation(run / "prefix", row["arm"])
        (run / "presentation.md").write_bytes(data)
        write_json(run / "overlay.json", {
            "arm": row["arm"], "source": row["case"], "source_pin": plan["pin"],
            "presentation_sha256": digest(data), "presented_instructions_sha256": digest(instructions),
            "runner_sha256": digest(Path(draft_run.__file__).read_bytes()),
        })


if __name__ == "__main__":
    main()
