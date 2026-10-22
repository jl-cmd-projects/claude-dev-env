#!/usr/bin/env python3
"""Record one review pass on a pull request head for the merge review gate.

The agent loops a code review on its pull request. Each pass is recorded::

    python3 merge_review_receipt.py owner/name 12 abc1234 3   -> REVIEWED owner/name#12 abc1234 3 findings
    fix, push, review the new head
    python3 merge_review_receipt.py owner/name 12 def5678 0   -> CLEAN owner/name#12 def5678

A pass whose every finding is ruled out with file:line evidence counts as
clean once the rulings are posted and linked::

    python3 merge_review_receipt.py owner/name 12 def5678 2 --ruled-out 2 --rulings <url>
        -> CLEAN owner/name#12 def5678 (2 findings ruled out: <url>)

A pass run before the pull request exists names ``open`` in place of the
number, and records the head it reviewed::

    python3 merge_review_receipt.py owner/name open def5678 0   -> CLEAN owner/name open def5678

``hooks/blocking/merge_review_gate.py`` allows a merge pinned to the head of
the newest pass only when that pass is clean. It allows a pull request open
whose head has a clean ``open`` pass, and a merge pinned to that same head.
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

from blocking.merge_review_gate import is_clean_receipt, open_receipt_path, receipt_path
from hooks_constants.merge_review_gate_constants import (
    OPEN_HEAD_PATTERN,
    OPEN_TARGET_WORD,
    RECEIPT_FINDINGS_KEY,
    RECEIPT_HEAD_KEY,
    RECEIPT_RULED_OUT_KEY,
    RECEIPT_RULINGS_KEY,
)


def record_review(
    slug: str,
    number: int,
    head: str,
    finding_count: int,
    ruled_out_count: int = 0,
    rulings: str = "",
) -> Path:
    """Write the receipt for one review pass, replacing the previous pass.

    Args:
        slug: Repository as ``owner/name``.
        number: Pull request number.
        head: The commit the pass reviewed.
        finding_count: How many findings the pass reported.
        ruled_out_count: How many of those findings were ruled out.
        rulings: Link to the posted rulings, empty when none were ruled out.

    Returns:
        The receipt path written.
    """
    receipt = _receipt_fields(head, finding_count, ruled_out_count, rulings)
    return _write_receipt(slug, number, receipt)


def record_open_review(slug: str, head: str, finding_count: int) -> Path:
    """Write the receipt for one review pass run before the pull request opens.

    Args:
        slug: Repository as ``owner/name``.
        head: The commit the pass reviewed.
        finding_count: How many findings the pass reported.

    Returns:
        The receipt path written.
    """
    owner, repo = slug.split("/", 1)
    return _write_receipt_at(
        open_receipt_path(owner, repo, head), _receipt_fields(head, finding_count, 0, "")
    )


def _write_receipt(slug: str, number: int, all_receipt_fields: dict[str, object]) -> Path:
    owner, repo = slug.split("/", 1)
    return _write_receipt_at(receipt_path(owner, repo, number), all_receipt_fields)


def _write_receipt_at(path: Path, all_receipt_fields: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(all_receipt_fields) + "\n", encoding="utf-8")
    return path


def _receipt_fields(
    head: str, finding_count: int, ruled_out_count: int, rulings: str
) -> dict[str, object]:
    receipt: dict[str, object] = {RECEIPT_HEAD_KEY: head, RECEIPT_FINDINGS_KEY: finding_count}
    if ruled_out_count:
        receipt[RECEIPT_RULED_OUT_KEY] = ruled_out_count
        receipt[RECEIPT_RULINGS_KEY] = rulings
    return receipt


def main(all_arguments: Sequence[str], stdout: TextIO = sys.stdout) -> int:
    """Record one pass and print its verdict line.

    Args:
        all_arguments: Command arguments after the program name.
        stdout: Stream that receives the verdict.

    Returns:
        0 for a clean pass, and 1 for a pass with findings still open.
    """
    parser = argparse.ArgumentParser(prog="merge_review_receipt")
    parser.add_argument("slug", help="Repository as owner/name.")
    parser.add_argument(
        "number", help=f"Pull request number, or {OPEN_TARGET_WORD} before the pull request opens."
    )
    parser.add_argument("head", help="The head commit the pass reviewed.")
    parser.add_argument("findings", type=int, help="Findings the pass reported.")
    parser.add_argument(
        "--ruled-out", type=int, default=0, help="Findings ruled out with file:line evidence."
    )
    parser.add_argument("--rulings", default="", help="Link to the posted rulings.")
    parsed = parser.parse_args(all_arguments)
    rulings = parsed.rulings.strip()
    if parsed.number == OPEN_TARGET_WORD:
        if parsed.ruled_out or rulings:
            parser.error(f"an {OPEN_TARGET_WORD} pass is clean only at zero findings")
        if parsed.findings < 0:
            parser.error("findings must be zero or more")
        if not OPEN_HEAD_PATTERN.fullmatch(parsed.head):
            parser.error(f"an {OPEN_TARGET_WORD} pass needs a 7 to 40 character hex commit")
        record_open_review(parsed.slug, parsed.head, parsed.findings)
        verdict = "CLEAN" if parsed.findings == 0 else "REVIEWED"
        count_note = "" if parsed.findings == 0 else f" {parsed.findings} findings"
        stdout.write(f"{verdict} {parsed.slug} {OPEN_TARGET_WORD} {parsed.head}{count_note}\n")
        return 0 if parsed.findings == 0 else 1
    if not parsed.number.isdigit():
        parser.error(f"number must be a pull request number or {OPEN_TARGET_WORD}")
    parsed.number = int(parsed.number)
    if parsed.ruled_out < 0 or parsed.ruled_out > parsed.findings:
        parser.error("--ruled-out must be between 0 and the finding count")
    if parsed.ruled_out and not rulings:
        parser.error("--ruled-out needs --rulings, a link to the posted rulings")
    if rulings and not parsed.ruled_out:
        parser.error("--rulings needs --ruled-out, the count of findings it rules out")
    receipt = _receipt_fields(parsed.head, parsed.findings, parsed.ruled_out, rulings)
    _write_receipt(parsed.slug, parsed.number, receipt)
    owner, repo = parsed.slug.split("/", 1)
    if is_clean_receipt(receipt, owner, repo, parsed.number):
        ruled_out_note = (
            f" ({parsed.ruled_out} findings ruled out: {rulings})" if parsed.ruled_out else ""
        )
        stdout.write(f"CLEAN {parsed.slug}#{parsed.number} {parsed.head}{ruled_out_note}\n")
        return 0
    stdout.write(
        f"REVIEWED {parsed.slug}#{parsed.number} {parsed.head} {parsed.findings} findings\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
