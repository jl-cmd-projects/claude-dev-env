"""Build matched continuations from one observed workspace and its shell trace."""

import argparse
import json
import shutil
from pathlib import Path

from checkpoint import CSV_PATH, FOLLOWUP_PROMPT, OPPOSITE_SCOPE_PROMPT
from side_issue import MANIFEST
from trial import create, digest, write_json

LATEST = {"csv": FOLLOWUP_PROMPT, "both": OPPOSITE_SCOPE_PROMPT, "dispatch": "Continue with the warehouse handoff."}


def checkpoint_request(prefix, latest):
    events = [json.loads(line) for line in (prefix / "events.jsonl").read_text().splitlines()]
    history = [{"command": row["command"], "exit": row["exit"],
                "stdout": row["stdout"], "stderr": row["stderr"]} for row in events]
    paths = {"checkpoint": CSV_PATH, "side-issue": MANIFEST}
    case_id = json.loads((prefix / "run.json").read_text())["case"]
    artifact_path = paths[case_id]
    path = prefix / "work" / artifact_path
    artifact = path.read_text() if path.is_file() else "(absent)"
    return (
        "Original user request\n" + (prefix / "task.txt").read_text() +
        "\n\nWork already performed in this checkout\n" + json.dumps(history, indent=2) +
        "\n\nWorker's checkpoint summary\n" + (prefix / "reply.txt").read_text() +
        "\n\nCurrent " + artifact_path + "\n" + artifact + "\n\nLatest user request\n" + latest
    )


def fork(prefix, destination, scope, arm, review=None):
    task = checkpoint_request(prefix, LATEST[scope])
    if arm == "reviewer" and review is None:
        raise ValueError("reviewer arm needs its recorded review")
    case_id = json.loads((prefix / "run.json").read_text())["case"]
    create(destination, case_id, arm, task)
    shutil.copytree(prefix / "work", destination / "work", dirs_exist_ok=True)
    manifest = json.loads((destination / "run.json").read_text())
    manifest.update(scope=scope, prefix_trace_sha256=digest((prefix / "events.jsonl").read_bytes()))
    if review is not None:
        receipt = json.loads(review.read_text())
        if receipt["request_sha256"] != digest(task.encode()):
            raise ValueError("review received a different goal or checkpoint")
        (destination / "advice.txt").write_text(receipt["advice"], encoding="utf-8")
        manifest["reviewer_seconds"] = receipt["elapsed_seconds"]
        manifest["reviewer_id"] = receipt["session"]
    write_json(destination / "run.json", manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", type=Path)
    parser.add_argument("scope", choices=LATEST)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--arm", choices=("baseline", "candidate", "reviewer"), default="baseline")
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    if args.destination:
        fork(args.prefix, args.destination, args.scope, args.arm, args.review)
    else:
        print(checkpoint_request(args.prefix, LATEST[args.scope]), end="")


if __name__ == "__main__":
    main()
