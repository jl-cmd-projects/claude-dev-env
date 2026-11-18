"""Send one operation to the local work-order desk."""

import json
import sys
import time
import uuid
from pathlib import Path
from typing import TextIO

from active_eval.config import client


def main(reply_stream: TextIO) -> None:
    """Publish one argument vector and write its receipt.

    Args:
        reply_stream: Destination for the desk reply.

    Raises:
        SystemExit: The receiving desk missed the response deadline.
    """
    mailbox = Path(__file__).resolve().parent / client.MAILBOX
    message = mailbox / uuid.uuid4().hex
    pending = message.with_suffix(client.PENDING)
    pending.write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
    pending.rename(message.with_suffix(client.REQUEST))
    answer = message.with_suffix(client.REPLY)
    deadline = time.monotonic() + client.TIMEOUT_SECONDS
    while not answer.exists() and time.monotonic() < deadline:
        time.sleep(client.POLL_SECONDS)
    if not answer.exists():
        raise SystemExit("The local desk did not respond.")
    reply_stream.write(answer.read_text(encoding="utf-8") + "\n")


if __name__ == "__main__":
    main(sys.stdout)
