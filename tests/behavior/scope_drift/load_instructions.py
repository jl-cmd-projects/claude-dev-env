"""Deliver the working copy to a native trial and keep a receipt outside it."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__:
    from .config import recall as protocol
else:
    from config import recall as protocol


def main() -> None:
    """Write the selected trial input to stdout and record its digest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    delivery = parser.add_mutually_exclusive_group()
    delivery.add_argument("--compact", action="store_true")
    delivery.add_argument("--startup", action="store_true")
    args = parser.parse_args()
    if args.startup:
        run = args.work
        startup_content = (run / protocol.STARTUP).read_bytes()
        sys.stdout.buffer.write(startup_content)
        sys.stdout.buffer.flush()
        (run / protocol.STARTUP_RECEIPT).write_text(
            hashlib.sha256(startup_content).hexdigest() + "\n", encoding="ascii"
        )
        return
    if args.compact:
        run = args.work
        session = run / protocol.SESSION
        paths = [run / "work" / protocol.INSTRUCTIONS, session / protocol.CONTEXT]
        summary = session / protocol.SUMMARY
        if summary.is_file():
            paths.append(summary)
        hashes = {}
        for each_path in paths:
            source_content = each_path.read_bytes()
            sys.stdout.buffer.write(source_content + b"\n\n")
            hashes[each_path.name] = hashlib.sha256(source_content).hexdigest()
        sys.stdout.buffer.flush()
        (run / protocol.NAMED_RECEIPT).write_text(json.dumps(hashes), encoding="ascii")
        return
    instructions = (args.work / protocol.INSTRUCTIONS).read_bytes()
    sys.stdout.buffer.write(instructions)
    sys.stdout.buffer.flush()
    receipt = args.work.parent / (args.work.name + protocol.LOADED_RECEIPT_SUFFIX)
    receipt.write_text(
        hashlib.sha256(instructions).hexdigest() + "\n", encoding="ascii"
    )


if __name__ == "__main__":
    main()
