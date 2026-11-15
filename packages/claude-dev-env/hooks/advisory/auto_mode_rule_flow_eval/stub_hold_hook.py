#!/usr/bin/env python3
"""Calibration stub that always acts.

::

    PermissionDenied -> writes one pending ledger file per refusal, prints nothing
    Stop             -> holds the turn: block decision on stdout, exit 2

It must score 0 on every ``should stay quiet`` case, which shows that no such
case passes when a hook records and holds on every event. It logs each hold
with ``log_hook_block``, which writes under ``HOME`` and never to stdout.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

_hooks_root_directory = str(Path(__file__).resolve().parent.parent.parent)
if _hooks_root_directory not in sys.path:
    sys.path.insert(0, _hooks_root_directory)

from hooks_constants.auto_mode_rule_flow_runner_constants import (
    ALL_LEDGER_RELATIVE_PARTS,
    CONFIG_DIRECTORY_VARIABLE,
    HOLD_EXIT_CODE,
    STOP_EVENT_NAME,
    STUB_HOLD_REASON,
)
from hooks_constants.hook_block_logger import log_hook_block


def main() -> int:
    payload = json.load(sys.stdin)
    if payload.get("hook_event_name") == STOP_EVENT_NAME:
        log_hook_block(Path(__file__).name, STOP_EVENT_NAME, STUB_HOLD_REASON)
        sys.stdout.write(json.dumps({"decision": "block", "reason": STUB_HOLD_REASON}))
        return HOLD_EXIT_CODE
    ledger_directory = Path(os.environ[CONFIG_DIRECTORY_VARIABLE]).joinpath(
        *ALL_LEDGER_RELATIVE_PARTS, str(payload.get("session_id"))
    )
    ledger_directory.mkdir(parents=True, exist_ok=True)
    entry = {"tool_name": payload.get("tool_name"), "answer": None}
    (ledger_directory / f"{uuid.uuid4().hex[:12]}.json").write_text(
        json.dumps(entry), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
