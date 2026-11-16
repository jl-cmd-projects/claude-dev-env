#!/usr/bin/env python3
"""Calibration stub that never acts: no output, no ledger file, exit 0.

The case runner feeds it both PermissionDenied and Stop events. It must score
0 on every ``should act`` case, which shows that no such case passes when a
hook does nothing.
"""

from __future__ import annotations

import sys


def main() -> int:
    sys.stdin.read()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
