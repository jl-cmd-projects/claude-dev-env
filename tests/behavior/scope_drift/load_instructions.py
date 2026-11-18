"""Deliver the working copy to a native trial and keep a receipt outside it."""

import argparse
import hashlib
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    delivery = parser.add_mutually_exclusive_group()
    delivery.add_argument("--compact", action="store_true")
    delivery.add_argument("--startup", action="store_true")
    args = parser.parse_args()
    if args.startup:
        run = args.work
        startup_content = (run / "startup.txt").read_bytes()
        sys.stdout.buffer.write(startup_content)
        sys.stdout.buffer.flush()
        (run / "startup.sha256").write_text(
            hashlib.sha256(startup_content).hexdigest() + "\n", encoding="ascii"
        )
        return
    if args.compact:
        run = args.work
        paths = [run / "work/AGENTS.md", run / ".session/compact-context.txt"]
        summary = run / ".session/summary.txt"
        if summary.is_file():
            paths.append(summary)
        hashes = {}
        for path in paths:
            source_content = path.read_bytes()
            sys.stdout.buffer.write(source_content + b"\n\n")
            hashes[path.name] = hashlib.sha256(source_content).hexdigest()
        sys.stdout.buffer.flush()
        (run / "delivered.json").write_text(json.dumps(hashes), encoding="ascii")
        return
    instructions = (args.work / "AGENTS.md").read_bytes()
    sys.stdout.buffer.write(instructions)
    sys.stdout.buffer.flush()
    receipt = args.work.parent / (args.work.name + ".loaded")
    receipt.write_text(
        hashlib.sha256(instructions).hexdigest() + "\n", encoding="ascii"
    )


if __name__ == "__main__":
    main()
