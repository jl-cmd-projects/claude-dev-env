"""Prepare paired workspaces and record shell calls for hosted Codex trials."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from cases import CASES, grade, prepare
from checkpoint import CHECKPOINT_CASE, INITIAL_PROMPT
from side_issue import SIDE_CASE, INITIAL_PROMPT as DIAGNOSTIC_PROMPT


PIN = "3ab5949a8ea9c1ad11280e8e9a524bee2587bb8a"
SOURCE = "packages/claude-dev-env/system-prompts/codex-sol.md"
HERE = Path(__file__).resolve().parent
BUDGET_SECONDS = 360
CASES["checkpoint"] = CHECKPOINT_CASE
CASES["side-issue"] = SIDE_CASE


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def create(directory, case_id, arm, prompt=None):
    directory.mkdir(parents=True, exist_ok=False)
    workspace = directory / "work"
    workspace.mkdir()
    prepare(case_id, workspace)
    baseline = subprocess.check_output(["git", "show", f"{PIN}:{SOURCE}"], cwd=HERE)
    instructions = baseline
    if arm == "candidate":
        anchor = b"\n# Personality\n"
        if baseline.count(anchor) != 1:
            raise ValueError("missing insertion point")
        delta = (HERE / "intervention.txt").read_bytes().strip()
        instructions = baseline.replace(anchor, b"\n" + delta + b"\n" + anchor)
    (directory / "instructions.md").write_bytes(instructions)
    prompt = prompt or CASES[case_id].prompt
    (directory / "task.txt").write_text(prompt, encoding="utf-8")
    inputs = {p: digest((workspace / p).read_bytes()) for p in sorted(CASES[case_id].files)}
    write_json(directory / "run.json", {
        "case": case_id, "arm": arm, "pin": PIN, "budget_seconds": BUDGET_SECONDS,
        "input_files": inputs, "prompt_sha256": digest(prompt.encode()),
        "instructions_sha256": digest(instructions), "baseline_sha256": digest(baseline),
    })


def append_record(directory, record):
    with (directory / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record) + "\n")


def start(directory):
    stamp = directory / "started"
    try:
        with stamp.open("x", encoding="utf-8") as stream:
            stream.write(str(time.monotonic()))
    except FileExistsError:
        raise SystemExit("This session has already started.")
    print((directory / "instructions.md").read_text())
    print("\nUser task\n")
    print((directory / "task.txt").read_text())
    if (directory / "advice.txt").is_file():
        print("\nFresh review of the task and work so far\n")
        print((directory / "advice.txt").read_text())


def available_seconds(directory):
    run = json.loads((directory / "run.json").read_text())
    return run["budget_seconds"] - run.get("reviewer_seconds", 0)


def shell(directory, command):
    started = time.monotonic()
    deadline = float((directory / "started").read_text()) + available_seconds(directory)
    if started >= deadline:
        raise SystemExit("Session budget expired")
    if (directory / "reply.txt").exists():
        raise SystemExit("The session already submitted its reply")
    try:
        result = subprocess.run(
            ["bash", "-c", command], cwd=directory / "work", capture_output=True,
            timeout=deadline - started, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        code, stdout, stderr = 124, error.stdout or b"", error.stderr or b""
    append_record(directory, {
        "command": command, "start": started, "seconds": time.monotonic() - started,
        "exit": code, "stdout": stdout.decode(errors="replace"), "stderr": stderr.decode(errors="replace"),
    })
    sys.stdout.buffer.write(stdout)
    sys.stderr.buffer.write(stderr)
    return code


def finish(directory, reply):
    elapsed = time.monotonic() - float((directory / "started").read_text())
    with (directory / "reply.txt").open("x", encoding="utf-8") as stream:
        stream.write(reply + "\n")
    write_json(directory / "clock.json", {"elapsed_seconds": elapsed, "within_budget": elapsed <= available_seconds(directory)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    actions = parser.add_subparsers(dest="action", required=True)
    new = actions.add_parser("create")
    new.add_argument("case", choices=CASES)
    new.add_argument("arm", choices=("baseline", "candidate"))
    new.add_argument("--prefix", action="store_true")
    actions.add_parser("start")
    actions.add_parser("shell").add_argument("command")
    actions.add_parser("finish").add_argument("reply")
    actions.add_parser("grade")
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.action == "create":
        prefixes = {"checkpoint": INITIAL_PROMPT, "side-issue": DIAGNOSTIC_PROMPT}
        create(directory, args.case, args.arm, prefixes[args.case] if args.prefix else None)
    elif args.action == "start":
        start(directory)
    elif args.action == "shell":
        return shell(directory, args.command)
    elif args.action == "finish":
        finish(directory, args.reply)
    else:
        case_id = json.loads((directory / "run.json").read_text())["case"]
        print(json.dumps(grade(case_id, directory / "work"), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
