"""Local receiving client supplied to each disposable workspace."""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import TextIO
from uuid import uuid4

from completion_eval.config import desk as protocol


def main(reply_stream: TextIO) -> int:
    """Send one request and write its reply to stdout.

    Args:
        reply_stream: Destination for the JSON reply.

    Returns:
        The receiving operation's exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["status", "deliver"])
    parser.add_argument("key", nargs="?")
    parser.add_argument("value", nargs="?")
    args = parser.parse_args()
    if args.operation == "deliver" and (not args.key or not args.value):
        parser.error("deliver needs a receiver key and its replacement text")
    mailbox = Path(__file__).parent / protocol.MAILBOX
    request = mailbox / uuid4().hex
    pending = request.with_suffix(protocol.PENDING)
    pending.write_text(json.dumps(vars(args)), encoding="utf-8")
    pending.rename(request.with_suffix(protocol.REQUEST))
    reply = request.with_suffix(protocol.REPLY)
    deadline = time.monotonic() + protocol.REPLY_TIMEOUT
    while time.monotonic() < deadline:
        if reply.is_file():
            answer = json.loads(reply.read_text(encoding="utf-8"))
            reply_stream.write(json.dumps(answer) + "\n")
            return 0 if answer["status"] in {"ok", "received"} else 1
        time.sleep(protocol.POLL_SECONDS)
    parser.exit(protocol.TIMEOUT_EXIT, "Receiver did not acknowledge the request.\n")


if __name__ == "__main__":
    raise SystemExit(main(sys.stdout))
