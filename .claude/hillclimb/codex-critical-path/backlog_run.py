"""Run matched backlog tasks and preserve the workspace and command evidence."""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from long_run import command_output, run_command, run_lock, utc_now, workspace_tree
from proof import directory_name, encode, json_digest, pinned_baseline, read_json
from trial import HERE, append_record, digest, write_json

PIN = "a300d6e78f78568b24b869210cb9595a3b8dc524"
BUDGET_SECONDS = 360
CASES = ("distributed", "anchor", "reprioritized")
ARMS = ("baseline", "candidate")
MODELS = ("gpt-6.2-sol", "gpt-6.1-sol")
SCHEDULE = "backlog_schedule.json"
PROMPT = "backlog_prompt.txt"
UPDATE = "backlog_update.txt"
INSTRUCTION = "backlog_instruction.txt"
SOURCE_FILES = ("backlog_run.py", "backlog_verify.py", "backlog_case.py", PROMPT, UPDATE, INSTRUCTION, SCHEDULE)
INPUT_FILES = ("opening.txt", "instructions.md", "task.txt", "operator-update.txt", "initial-workspace.json")
JOURNAL = "queue-state/events.json"
EXPIRED = "The 360-second active exercise budget expired."


def path_hash(path):
    return digest(path.read_bytes())


def hashes(root, names):
    return {name: path_hash(root / name) for name in names}


def allocation_rows(schedule):
    rows = schedule["rows"]
    if not 1 <= len(rows) <= 6:
        raise ValueError("The study requires one to six matched pairs.")
    ids = []
    for row in rows:
        order = row["order"]
        if row["case"] not in CASES or row["model"] not in MODELS or row.get("reasoning_effort", "high") != "high":
            raise ValueError("Unexpected case or model selectors in the schedule.")
        if tuple(order) not in (ARMS, ARMS[::-1]):
            raise ValueError("Each pair must allocate both arms once.")
        ids.extend(directory_name(row[arm]) for arm in ARMS)
    if len(set(ids)) != len(ids) or "replay" in ids:
        raise ValueError("Worker identifiers must be unique and may not be named replay.")
    if schedule.get("pin", PIN) != PIN or schedule.get("budget_seconds", BUDGET_SECONDS) != BUDGET_SECONDS:
        raise ValueError("The schedule specifies a different baseline or budget.")
    return rows


def launch_rows(root):
    schedule = root / SCHEDULE
    if schedule.read_bytes() != (HERE / SCHEDULE).read_bytes():
        raise ValueError("The archived schedule differs from the frozen schedule.")
    return allocation_rows(read_json(schedule))


def expected_material(case, arm):
    baseline = pinned_baseline(PIN).encode()
    instructions = baseline
    if arm == "candidate":
        delta = (HERE / INSTRUCTION).read_bytes().strip()
        if not delta:
            raise ValueError("Candidate instructions are empty.")
        instructions = baseline.rstrip() + b"\n\n" + delta + b"\n"
    task = (HERE / PROMPT).read_bytes()
    update = (HERE / UPDATE).read_bytes() if case == "reprioritized" else b""
    if not task.strip() or (case == "reprioritized" and not update.strip()):
        raise ValueError("Missing task or user update.")
    opening = instructions.rstrip() + b"\n\nUser task\n\n" + task.rstrip() + b"\n"
    if update:
        opening += b"\nUser update\n\n" + update.rstrip() + b"\n"
    return baseline, {
        "instructions.md": instructions, "task.txt": task, "operator-update.txt": update, "opening.txt": opening,
    }


def prepare(root, ident):
    import backlog_case

    root.mkdir(parents=True, exist_ok=True)
    with run_lock(root):
        archive = root / SCHEDULE
        if not archive.exists():
            shutil.copyfile(HERE / SCHEDULE, archive)
        rows = launch_rows(root)
    row, arm = allocated(rows, ident)
    baseline, material = expected_material(row["case"], arm)
    directory = root / ident
    directory.mkdir()
    try:
        work = directory / "work"
        work.mkdir()
        backlog_case.setup(work, row["case"])
        tree = workspace_tree(work)
        write_json(directory / "initial-workspace.json", tree)
        shutil.copytree(work, directory / "initial", symlinks=True)
        if workspace_tree(directory / "initial") != tree:
            raise ValueError("The opening workspace snapshot changed.")
        for name, content in material.items():
            (directory / name).write_bytes(content)
        (directory / "events.jsonl").touch()
        write_json(directory / "run.json", {
            "case": row["case"], "arm": arm, "pin": PIN, "budget_seconds": BUDGET_SECONDS,
            "model": row["model"], "reasoning_effort": row.get("reasoning_effort", "high"),
            "fork_turns": "none", "baseline_sha256": digest(baseline),
            "original_directory": str(directory),
            "source_sha256": hashes(HERE, SOURCE_FILES),
            "input_sha256": hashes(directory, INPUT_FILES),
            "initial_workspace_sha256": json_digest(tree),
        })
    except BaseException:
        shutil.rmtree(directory)
        raise


def allocated(rows, ident):
    for row in rows:
        for arm in ARMS:
            if row[arm] == ident:
                return row, arm
    raise ValueError(f"Worker {ident} is outside the frozen allocation.")


def start(directory):
    marker = directory / "started.json"
    if marker.exists() or (directory / "end.json").exists():
        raise ValueError("The worker already started.")
    run = read_json(directory / "run.json")
    observed = json_digest(workspace_tree(directory / "work"))
    input_hashes = hashes(directory, INPUT_FILES)
    if (input_hashes != run["input_sha256"] or observed != run["initial_workspace_sha256"]
            or run["original_directory"] != str(directory)
            or hashes(HERE, SOURCE_FILES) != run["source_sha256"]):
        raise ValueError("The frozen instructions, task, source or opening workspace changed.")
    write_json(marker, {
        "monotonic": time.monotonic(), "utc": utc_now(), "input_sha256": input_hashes,
        "initial_workspace_sha256": observed, "opening_sha256": input_hashes["opening.txt"],
    })
    sys.stdout.buffer.write((directory / "opening.txt").read_bytes())


def active_since(directory):
    if (directory / "end.json").exists():
        raise ValueError("The worker already ended.")
    if not (directory / "started.json").exists():
        raise ValueError("The worker has not started.")
    return read_json(directory / "started.json")["monotonic"]


def changes(before, after):
    return {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in sorted(before.keys() | after.keys()) if before.get(key) != after.get(key)
    }


def retain_end(directory, began, outcome, reply):
    work = directory / "work"
    end = directory / "end"
    stamp = time.monotonic()
    utc = utc_now()
    shutil.copytree(work, end, symlinks=True)
    if reply is not None:
        (directory / "reply.txt").write_text(reply + "\n", encoding="utf-8")
    elapsed = stamp - began
    write_json(directory / "end.json", {
        "outcome": outcome, "utc": utc, "monotonic": stamp, "elapsed_seconds": elapsed,
        "within_budget": elapsed <= BUDGET_SECONDS, "workspace_sha256": json_digest(workspace_tree(end)),
        "events_sha256": path_hash(directory / "events.jsonl"),
        "reply_sha256": path_hash(directory / "reply.txt") if reply is not None else None,
    })


def shell(directory, command):
    began = active_since(directory)
    workspace = directory / "work"
    before = workspace_tree(workspace)
    started = time.monotonic()
    started_utc = utc_now()
    available = BUDGET_SECONDS - (started - began)
    if available <= 0:
        retain_end(directory, began, "expired", None)
        raise ValueError(EXPIRED)
    code, stdout, stderr, timed_out = run_command(workspace, command, available)
    finished = time.monotonic()
    finished_utc = utc_now()
    after = workspace_tree(workspace)
    event = {
        "command": command, "command_sha256": digest(command.encode()),
        "exit": code, "timed_out": timed_out, "started_utc": started_utc, "finished_utc": finished_utc,
        "start_seconds": started - began, "end_seconds": finished - began, "seconds": finished - started,
        "before_workspace_sha256": json_digest(before), "after_workspace_sha256": json_digest(after),
        "changes": changes(before, after), "stdout_sha256": digest(stdout), "stderr_sha256": digest(stderr),
    }
    command_output(event, "stdout", stdout)
    command_output(event, "stderr", stderr)
    if JOURNAL in event["changes"] and "sha256" in after.get(JOURNAL, {}):
        event["journal_after_base64"] = encode((workspace / JOURNAL).read_bytes())
    append_record(directory, event)
    sys.stdout.buffer.write(stdout)
    sys.stderr.buffer.write(stderr)
    return code


def finish(directory, reply):
    retain_end(directory, active_since(directory), "submitted", reply)


def expire(directory):
    began = active_since(directory)
    if time.monotonic() - began < BUDGET_SECONDS:
        raise ValueError("The worker still has active time.")
    retain_end(directory, began, "expired", None)


def main():
    if sys.argv[2:3] == ["replay"]:
        import backlog_verify

        return backlog_verify.main(sys.argv[1:2] + sys.argv[3:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("id", type=directory_name)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("prepare")
    actions.add_parser("start")
    actions.add_parser("sh").add_argument("command")
    actions.add_parser("finish").add_argument("reply")
    actions.add_parser("expire")
    actions.add_parser("score")
    args = parser.parse_args()
    root = args.root.resolve()
    directory = root / args.id
    try:
        if args.action == "prepare":
            prepare(root, args.id)
            return 0
        with run_lock(directory):
            if args.action == "start":
                start(directory)
            elif args.action == "sh":
                return shell(directory, args.command)
            elif args.action == "finish":
                finish(directory, args.reply)
            elif args.action == "expire":
                expire(directory)
            else:
                import backlog_verify

                row, arm = allocated(launch_rows(root), args.id)
                result, _ = backlog_verify.read_run(directory, row, arm)
                print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"{error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
