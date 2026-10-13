#!/usr/bin/env python3
"""Record one review pass on a pull request head for the merge review gate.

The agent loops a code review on its pull request. Each pass is recorded::

    python3 merge_review_receipt.py owner/name 12 abc1234 3   -> REVIEWED owner/name#12 abc1234 3 findings
    fix, push, review the new head
    python3 merge_review_receipt.py owner/name 12 def5678 0   -> CLEAN owner/name#12 def5678

``hooks/blocking/merge_review_gate.py`` allows a merge pinned to the head of
the newest pass only when that pass counted zero findings.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

hooks_directory = str(Path(__file__).resolve().parent.parent / "hooks")
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.merge_review_gate import receipt_path
from hooks_constants.merge_review_gate_constants import (
    RECEIPT_FINDINGS_KEY,
    RECEIPT_HEAD_KEY,
)


def record_review(slug: str, number: int, head: str, finding_count: int) -> Path:
    """Write the receipt for one review pass, replacing the previous pass.

    Args:
        slug: Repository as ``owner/name``.
        number: Pull request number.
        head: The commit the pass reviewed.
        finding_count: How many findings the pass reported.

    Returns:
        The receipt path written.
    """
    owner, repo = slug.split("/", 1)
    path = receipt_path(owner, repo, number)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({RECEIPT_HEAD_KEY: head, RECEIPT_FINDINGS_KEY: finding_count})
        + "\n",
        encoding="utf-8",
    )
    return path


def main(all_arguments: Sequence[str], stdout: TextIO = sys.stdout) -> int:
    """Record one pass and print its verdict line.

    Args:
        all_arguments: Command arguments after the program name.
        stdout: Stream that receives the verdict.

    Returns:
        0 for a clean pass, and 1 for a pass with findings.
    """
    parser = argparse.ArgumentParser(prog="merge_review_receipt")
    parser.add_argument("slug", help="Repository as owner/name.")
    parser.add_argument("number", type=int, help="Pull request number.")
    parser.add_argument("head", help="The head commit the pass reviewed.")
    parser.add_argument("findings", type=int, help="Findings the pass reported.")
    parsed = parser.parse_args(all_arguments)
    record_review(parsed.slug, parsed.number, parsed.head, parsed.findings)
    if parsed.findings == 0:
        stdout.write(f"CLEAN {parsed.slug}#{parsed.number} {parsed.head}\n")
        return 0
    stdout.write(
        f"REVIEWED {parsed.slug}#{parsed.number} {parsed.head} {parsed.findings} findings\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
