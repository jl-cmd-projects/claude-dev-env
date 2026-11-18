"""Mask album traces for reviewers and recheck the graded artifacts from an archive."""

import argparse
import json
import re
import secrets
from pathlib import Path

import manifest_holdout as album
from proof import json_digest, read_json


def material(root, row):
    run_id = row["id"]
    directory = root / run_id
    receipt = read_json(root / "launches.json")[run_id]
    if receipt["receipt"] != {"task_name": "/root/" + run_id} or any(
        row[key] != receipt[key] for key in ("model", "reasoning_effort")
    ):
        raise ValueError("Worker launch disagrees with scheduled model.")
    run = read_json(directory / "run.json")
    if (run["arm"], run["case"]) != (row["arm"], row["case"]):
        raise ValueError("Run inputs disagree with the schedule.")
    if not album.matching_inputs(directory, run):
        raise ValueError("Recorded instructions or assignment changed.")
    baseline = album.pinned_baseline(album.PIN).encode()
    extra = (album.HERE / "pressure_intervention.txt").read_bytes().strip()
    expected = album.instructions_for(baseline, extra if row["arm"] == "candidate" else None)
    if (run["pin"] != album.PIN or (directory / "instructions.md").read_bytes() != expected
            or run["runner_sha256"] != album.digest(Path(album.__file__).read_bytes())
            or (directory / "task.txt").read_bytes() != album.PROMPT.encode()):
        raise ValueError("Archived run differs from the pinned comparison.")
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    for name, checksum in events[-1]["target_sha256"].items():
        if album.digest((directory / "work" / name).read_bytes()) != checksum:
            raise ValueError("Final deliverable differs from its last captured state.")
    ending = album.grade(directory)
    first = (directory / "task.txt").read_text()
    answer = (directory / "reply.txt").read_text()
    if any(b["start_elapsed_seconds"] < a["end_elapsed_seconds"] for a, b in zip(events, events[1:])):
        raise ValueError("Recorded commands overlap within one worker.")
    result = {"user_task": first, "initial_files": album.fixture_files(row["case"]),
              "actions": events, "answer": answer, "oracle": ending}
    # A command can print a working directory or use a path in a reply.
    redacted = re.sub(r"(?:/[^\s\x22']*)?/heldout-album-18/m[0-9]+(?:/work)?", "<workspace>", json.dumps(result))
    return json.loads(redacted.replace(run_id, "<run>")), run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("blind", "replay"))
    parser.add_argument("root", type=Path)
    parser.add_argument("panel", type=Path, nargs="?")
    args = parser.parse_args()
    root = args.root
    schedule = read_json(Path(__file__).with_name("manifest_schedule.json"))["rows"]
    entries = {}
    summaries = {}
    cases = {}
    if args.action == "blind":
        if args.panel is None or (root / "panel-key.json").exists():
            parser.error("Choose an output panel for a run without a sealed grading key.")
        args.panel.mkdir(exist_ok=False)
    else:
        manifest = read_json(root / "panel-key.json")
        by_run = {v["id"]: (k, v["sha256"]) for k, v in manifest.items()}
        grades = read_json(root / "grades.json")
    for row in schedule:
        packet, run = material(root, row)
        matched = tuple(run[k] for k in ("runner_sha256", "workspace_sha256", "prompt_sha256", "baseline_sha256", "budget_seconds"))
        if cases.setdefault(row["case"], matched) != matched:
            raise ValueError("Mismatched case inputs.")
        packet_hash = json_digest(packet)
        if args.action == "blind":
            opaque = "packet-" + secrets.token_hex(8)
            (args.panel / (opaque + ".json")).write_text(json.dumps(packet, indent=2) + "\n")
            entries[opaque] = {"id": row["id"], "sha256": packet_hash}
        else:
            opaque, expected = by_run[row["id"]]
            if expected != packet_hash or expected != grades[opaque]["sha256"]:
                raise ValueError("Packet differs from its graded version.")
            summaries[row["id"]] = {**row, "oracle": packet["oracle"], "grade": grades[opaque],
                                     "commands": len(packet["actions"])}
    if args.action == "blind":
        (root / "panel-key.json").write_text(json.dumps(entries, indent=2) + "\n")
        checksums = {key: value["sha256"] for key, value in entries.items()}
        (args.panel / "checksums.json").write_text(json.dumps(checksums, indent=2) + "\n")
    else:
        print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
