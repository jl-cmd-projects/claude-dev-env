"""Resume an archived pre-dispatch support decision with the operator's visible evidence."""

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

import pressure_run as console
from long_run import run_lock
from proof import read_json
from trial import HERE, digest, write_json


def presentation(prefix, arm):
    original = (prefix / "instructions.md").read_bytes()
    extra = (HERE / "draft_intervention.txt").read_bytes().strip() if arm == "candidate" else None
    instructions = console.instructions_for(original, extra)
    parts = [instructions, b"\n\n", (prefix / "task.txt").read_bytes(),
             b"\n\nPrevious support console calls, in order:\n"]
    for line in (prefix / "events.jsonl").read_text().splitlines():
        event = json.loads(line)
        parts.append(("\n" + event["shell"] + "> " + event["command"] + "\n").encode())
        parts.append(event["stdout"].encode())
        parts.append(event["stderr"].encode())
        parts.append(f'\n[exit {event["exit"]}]\n'.encode())
    parts.extend([b"\nPending operator reply:\n", (prefix / "reply.txt").read_bytes()])
    return b"".join(parts), instructions


def create(root, sources):
    schedule = read_json(HERE / "draft_schedule.json")
    root.mkdir(exist_ok=False)
    for row in schedule["rows"]:
        directory = root / row["id"]
        source = sources / row["source"]
        for name, expected in schedule["source_digests"][row["source"]].items():
            if digest((source / name).read_bytes()) != expected:
                raise ValueError(f"Archived source mismatch for {source.name}/{name}")
        console.recover(source, directory)
        content, instructions = presentation(directory / "prefix", row["arm"])
        (directory / "presentation.md").write_bytes(content)
        extra = (HERE / "draft_intervention.txt").read_bytes().strip()
        write_json(directory / "overlay.json", {
            "source": row["source"], "arm": row["arm"], "presentation_sha256": digest(content),
            "presented_instructions_sha256": digest(instructions),
            "background_sha256": digest((source / "instructions.md").read_bytes()),
            "intervention_sha256": digest(extra) if row["arm"] == "candidate" else None,
            "runner_sha256": digest(Path(__file__).read_bytes()),
        })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("prepare").add_argument("sources", type=Path)
    for name in ("start", "send-draft"):
        commands.add_parser(name)
    commands.add_parser("ps").add_argument("command")
    commands.add_parser("finish").add_argument("reply")
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.action == "prepare":
        create(directory, args.sources.resolve())
        return
    with run_lock(directory):
        if args.action == "start":
            checked = read_json(directory / "overlay.json")
            data = (directory / "presentation.md").read_bytes()
            if digest(data) != checked["presentation_sha256"]:
                raise ValueError("The recorded handoff and presentation disagree.")
            with contextlib.redirect_stdout(io.StringIO()):
                console.start(directory, resume=True)
            write_json(directory / "issued.json", {
                "presentation_sha256": digest(data), "started_utc": read_json(directory / "started.json")["utc"],
            })
            sys.stdout.buffer.write(data)
        elif args.action == "ps":
            return console.shell(directory, "powershell", args.command)
        else:
            reply = (directory / "prefix" / "reply.txt").read_text() if args.action == "send-draft" else args.reply
            console.finish(directory, reply)


if __name__ == "__main__":
    sys.exit(main())
