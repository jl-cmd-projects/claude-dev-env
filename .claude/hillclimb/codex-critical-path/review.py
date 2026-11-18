"""Record one fresh reviewer's advice and its share of the trial budget."""

import argparse
import time
from pathlib import Path

from trial import digest, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("start")
    actions.add_parser("finish").add_argument("advice")
    args = parser.parse_args()
    request = (args.directory / "request.txt").read_bytes()
    stamp = args.directory / "started"
    if args.action == "start":
        with stamp.open("x", encoding="utf-8") as stream:
            stream.write(str(time.monotonic()))
        print(request.decode())
    else:
        elapsed = time.monotonic() - float(stamp.read_text())
        if (args.directory / "receipt.json").exists():
            raise SystemExit("A review was already submitted")
        write_json(args.directory / "receipt.json", {
            "session": args.directory.name, "request_sha256": digest(request),
            "advice": args.advice, "elapsed_seconds": elapsed,
        })


if __name__ == "__main__":
    main()
