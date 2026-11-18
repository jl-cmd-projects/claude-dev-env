"""Local receiving client supplied to each disposable workspace."""

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["status", "deliver"])
    parser.add_argument("key", nargs="?")
    parser.add_argument("value", nargs="?")
    args = parser.parse_args()
    if args.operation == "deliver" and (not args.key or not args.value):
        parser.error("deliver needs a receiver key and its replacement text")
    mailbox = Path(__file__).parent / ".desk"
    request = mailbox / uuid4().hex
    pending = request.with_suffix(".pending")
    pending.write_text(json.dumps(vars(args)), encoding="utf-8")
    pending.rename(request.with_suffix(".request"))
    reply = request.with_suffix(".reply")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if reply.is_file():
            answer = json.loads(reply.read_text(encoding="utf-8"))
            print(json.dumps(answer))
            return 0 if answer["status"] in {"ok", "received"} else 1
        time.sleep(0.05)
    parser.exit(2, "Receiver did not acknowledge the request.\n")


if __name__ == "__main__":
    raise SystemExit(main())
