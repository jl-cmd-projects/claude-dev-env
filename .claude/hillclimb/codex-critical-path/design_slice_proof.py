"""Blind and replay the matched design delivery trial."""

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import design_slice_run as runner
import pivot_proof
import pivot_steady
from pivot_proof import require
from proof import directory_name, parse_trace, read_json
from trial import HERE, digest


SCHEDULE = "design_slice_schedule.json"
MANIFEST = "design_slice_blind_manifest.json"
GRADES = "design_slice_blind_grades.json"
record_prefix = pivot_proof.prefix_record
record_branch = pivot_proof.branch_record
measure_actions = pivot_proof.action_measures
summarize_arm = pivot_proof.arm_summary
SUBPROBE_PHASES = {
    "prefix": ("actions_before_update", "irrelevant_prefix_actions"),
    "continuation": ("actions_after_update", "irrelevant_actions"),
}
LIMITS = tuple(limit for index, limit in enumerate(pivot_proof.LIMITS) if index != 1) + (
    "The original request stays in force on both arms. The inspection boundary is a trial nomination.",
    "Browser and ledger fixture results cannot establish deployment coverage.",
    "Subprobe labels cite spans in recorded commands. Blind judges assess their execution and avoidability.",
    "Subprobe counts have no separate duration because timing covers the enclosing shell call.",
)


def schedule_for(root):
    path = HERE / SCHEDULE
    archive = root / SCHEDULE
    require(not archive.exists() or archive.read_bytes() == path.read_bytes(),
            "The archived design schedule differs from the frozen schedule.")
    schedule = read_json(path)
    require(schedule["pin"] == runner.PIN and schedule["budget_seconds"] == runner.BUDGET_SECONDS,
            "The schedule changes the pinned instructions or active budget.")
    for name, expected in schedule.get("case_sha256", {}).items():
        require(digest((HERE / directory_name(name)).read_bytes()) == expected,
                f"The frozen trial input changed: {name}.")
    rows = [{"mode": "steady", **row} for row in schedule["rows"]]
    require(all(row["mode"] == "steady" and row["case"] in runner.CASES
                and row["incumbent_arm"] in pivot_proof.ARMS for row in rows),
            "The design allocation has an unsupported case, incumbent arm, or dialogue mode.")
    keys = ("id", *pivot_proof.ARMS, "reviewer")
    ids = [directory_name(row[key]) for row in rows for key in keys]
    require(rows and len(ids) == len(set(ids)), "The schedule reuses run identifiers or lists no runs.")
    return {"prefix_work_actions": 2, **schedule, "rows": rows}


def history(case):
    return runner.fixture(case).history(case)


def prefix_record(directory, row, schedule, baseline):
    prefix = record_prefix(directory, row, schedule, baseline)
    checkpoint = prefix["checkpoint"]
    if checkpoint:
        require(checkpoint.get("review_policy") == runner.pivot_run.REVIEW_POLICY,
                "The design checkpoint has no visible review policy marker.")
        events = parse_trace((directory / "events.jsonl").read_text(encoding="utf-8"))
        require(not any(runner.review_trigger(directory, prefix["manifest"], events[:index], None)["eligible"]
                        for index in range(2, len(events))),
                "The prefix continued past an eligible nomination.")
    return prefix


def branch_record(directory, prefix, review=None):
    runner.verify_review(directory)
    return record_branch(directory, prefix, review)


def subprobe_counts(visible, rows):
    require(isinstance(rows, list), "The blind grade requires a list of subprobes.")
    spans = defaultdict(list)
    counts = dict.fromkeys(SUBPROBE_PHASES, 0)
    for row in rows:
        require(isinstance(row, dict) and set(row) == {"phase", "action", "operation", "why"},
                "A subprobe requires phase, action, operation and why.")
        phase, index = row["phase"], row["action"]
        require(type(phase) is str and phase in SUBPROBE_PHASES, "Invalid subprobe phase.")
        events = visible[SUBPROBE_PHASES[phase][0]]
        require(type(index) is int and 1 <= index <= len(events), "Invalid subprobe action index.")
        operation, why = row["operation"], row["why"]
        require(all(isinstance(value, str) and value.strip() for value in (operation, why)),
                "A subprobe requires a concrete operation and a reason.")
        command_span = " ".join(operation.split())
        command = " ".join(events[index - 1]["command"].split())
        matches = list(re.finditer(r"(?<![\w./-])" + re.escape(command_span) + r"(?![\w./-])", command))
        require(len(matches) == 1, "A subprobe operation must quote a unique span in its recorded command.")
        start, end = matches[0].span()
        slot = spans[phase, index]
        require(all(end <= other_start or start >= other_end for other_start, other_end in slot),
                "Subprobes overlap or repeat the same operation.")
        slot.append((start, end))
        counts[phase] += 1
    return counts, spans


def action_measures(visible, grade):
    sustained = grade["sustained_detour"]
    checked = {**grade, "sustained_detour": False} if sustained is True else grade
    measures = measure_actions(visible, checked)
    counts, spans = subprobe_counts(visible, grade.get("subprobes", []))
    phases = SUBPROBE_PHASES if visible["user_update"] is None else ("continuation",)
    avoidable = sum(counts[phase] + sum((phase, action) not in spans for action in grade[SUBPROBE_PHASES[phase][1]])
                    for phase in phases)
    require(not sustained or avoidable >= 2, "A sustained detour needs at least two distinct avoidable operations.")
    return {**measures, "subprobes": sum(counts.values()),
            **{phase + "_subprobes": count for phase, count in counts.items()}}


def arm_summary(rows):
    return {
        **summarize_arm(rows),
        **{"total_" + field: sum(row["measures"][field] for row in rows)
           for field in ("subprobes", "prefix_subprobes", "continuation_subprobes")},
    }


def run_proof(command, root, panel):
    schedule_sha256 = digest((HERE / SCHEDULE).read_bytes())
    runner_sha256 = digest(Path(runner.__file__).read_bytes())
    with runner.pivot_fixture(), patch.object(pivot_steady, "history", history), patch.multiple(
        pivot_proof, schedule_for=schedule_for, SCHEDULE_SHA256=schedule_sha256, STEADY_SHA256=schedule_sha256,
        RUNNER_SHA256=runner_sha256, MANIFEST=MANIFEST, GRADES=GRADES, LIMITS=LIMITS,
        prefix_record=prefix_record, branch_record=branch_record,
        action_measures=action_measures, arm_summary=arm_summary,
    ):
        if command == "blind":
            return pivot_proof.blind(root, panel)
        result = pivot_proof.replay(root, panel)
    result.pop("steady_schedule_sha256")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("blind", "replay"))
    parser.add_argument("root", type=Path)
    parser.add_argument("panel", type=Path, nargs="?")
    args = parser.parse_args()
    if args.command == "blind" and args.panel is None:
        parser.error("blind requires a panel directory")
    try:
        result = run_proof(args.command, args.root.resolve(), args.panel.resolve() if args.panel else None)
    except (ImportError, KeyError, OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
