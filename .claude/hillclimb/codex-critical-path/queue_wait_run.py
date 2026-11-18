"""Prepare and verify matched queue wait trials from a recorded console prefix."""

import json
import shlex
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import backlog_case
import backlog_run as runner
import backlog_verify as verify
import queue_wait_case as fixture
from long_run import command_output, run_command, workspace_tree
from proof import json_digest, pinned_baseline
from trial import HERE, digest


CASES = ("independent", "dependent", "restricted")
SCHEDULE = "queue_wait_schedule.json"
PROMPT = "queue_wait_prompt.txt"
UPDATE = "queue_wait_update.txt"
PRELUDE = "prelude.json"
DENIAL = b"Resource not accessible by integration"
INPUTS = (*runner.INPUT_FILES, PRELUDE)
SOURCE = (
    "queue_wait_run.py", "queue_wait_case.py", PROMPT, UPDATE, SCHEDULE,
    "backlog_run.py", "backlog_verify.py", "backlog_case.py", "long_run.py", "proof.py", "trial.py",
)

prepare_backlog = runner.prepare
read_backlog = verify.read_run


def run_prefix(work, case):
    fixture.setup(work, case)
    commands = list(fixture.prelude_commands())
    if not commands or not commands[-1] or commands[-1][0] != "resolve":
        raise ValueError("The prefix must end with the normal resolver command.")
    entries = []
    tree = workspace_tree(work)
    for index, args in enumerate(commands):
        argv = ["python", "queue.py", *args]
        command = shlex.join(argv)
        code, stdout, stderr, timed_out = run_command(work, command, 30)
        last = index == len(commands) - 1
        if timed_out or code != (2 if last else 0) or (last and DENIAL not in stderr):
            raise ValueError(f"Unexpected prefix outcome for {command!r}: exit {code}, stderr {stderr!r}")
        after = workspace_tree(work)
        entry = {
            "argv": argv, "command": command, "exit": code,
            "before_workspace_sha256": json_digest(tree), "after_workspace_sha256": json_digest(after),
        }
        for field, data in (("stdout", stdout), ("stderr", stderr)):
            command_output(entry, field, data)
            entry[f"{field}_sha256"] = digest(data)
        entries.append(entry)
        tree = after
    return entries, tree


def visible_prefix(entries):
    return [
        {field: entry[field] for field in ("command", "exit", "stdout", "stderr")}
        for entry in entries
    ]


def json_bytes(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def material_for(case, entries):
    instructions = pinned_baseline(runner.PIN).encode()
    task = (HERE / PROMPT).read_bytes()
    update = (HERE / UPDATE).read_bytes() if case == "restricted" else b""
    if not task.strip() or (case == "restricted" and not update.strip()):
        raise ValueError("Missing task or user update.")
    opening = instructions.rstrip() + b"\n\nUser task\n\n" + task.rstrip() + b"\n"
    opening += b"\nConsole history from the preceding shift\n\n" + json_bytes(visible_prefix(entries))
    if update:
        opening += b"\nUser update\n\n" + update.rstrip() + b"\n"
    return instructions, {
        "instructions.md": instructions, "task.txt": task, "operator-update.txt": update,
        "opening.txt": opening, PRELUDE: json_bytes(entries),
    }


def prepare(root, ident):
    row, _ = runner.allocated(runner.allocation_rows(runner.read_json(HERE / SCHEDULE)), ident)
    case = row["case"]
    with tempfile.TemporaryDirectory(prefix="queue-wait-prepare-") as temp:
        prefix_work = Path(temp)
        entries, tree = run_prefix(prefix_work, case)
        material = material_for(case, entries)

        def restore_prefix(work, allocated_case):
            if allocated_case != case:
                raise ValueError("The prefix changed its schedule allocation.")
            shutil.copytree(prefix_work, work, dirs_exist_ok=True, symlinks=True)
            verify.require(workspace_tree(work) == tree, "The copied prefix snapshot changed.")

        with patch.object(runner, "expected_material", return_value=material):
            with patch.object(backlog_case, "setup", restore_prefix):
                prepare_backlog(root, ident)


def read_run(directory, row, arm):
    case = row["case"]
    with tempfile.TemporaryDirectory(prefix="queue-wait-replay-") as temp:
        entries, tree = run_prefix(Path(temp), case)
    material = material_for(case, entries)

    def check_prefix(allocated_case, expected):
        verify.require(allocated_case == case and tree == expected,
                       "The archived first workspace differs from the replayed prefix.")

    with patch.object(runner, "expected_material", return_value=material):
        with patch.object(verify, "reconstruct_fixture", check_prefix):
            result, details = read_backlog(directory, row, arm)
    result["initial_inputs"].update(runner.hashes(directory, ("instructions.md", "opening.txt", PRELUDE)))
    details["preceding_shift"] = visible_prefix(entries)
    return result, details


@contextmanager
def queue_harness():
    with patch.multiple(runner, CASES=CASES, SCHEDULE=SCHEDULE, INPUT_FILES=INPUTS,
                        SOURCE_FILES=SOURCE, JOURNAL=fixture.LOG, prepare=prepare):
        with patch.object(verify, "read_run", read_run), patch.object(backlog_case, "score", fixture.score):
            yield


def replay(root, receipt_path=None, blind=None):
    with queue_harness():
        return verify.replay(Path(root).resolve(), receipt_path, blind)


def main():
    with queue_harness():
        return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())
