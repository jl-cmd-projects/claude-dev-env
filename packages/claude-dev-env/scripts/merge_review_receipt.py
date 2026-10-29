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

No pull request exists to hold a rulings comment, so an ``open`` pass rules
out its findings with a different ``path:line`` for each, run in the checkout
that holds the head. Each line must exist in the file at that head::

    python3 merge_review_receipt.py owner/name open def5678 2 --ruled-out 2 --rulings a.py:1,b.py:20
        -> CLEAN owner/name open def5678 (2 findings ruled out: a.py:1,b.py:20)

``hooks/blocking/merge_review_gate.py`` allows a merge pinned to the head of
the newest pass only when that pass is clean. It allows a pull request open
whose head has a clean ``open`` pass. It allows a merge pinned to that same
head only when the ``open`` pass found zero findings. Ruled-out findings need
a numbered pass that links the rulings comment on the pull request.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

hooks_directory = str(Path(__file__).resolve().parent.parent / "hooks")
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.merge_review_gate_parts.receipts import (
    is_clean_open_pass,
    is_clean_receipt,
    open_receipt_path,
    receipt_path,
)
from hooks_constants.merge_review_gate_constants import (
    OPEN_RECEIPT_HEAD_PATTERN,
    OPEN_TARGET_WORD,
    RECEIPT_FINDINGS_KEY,
    RECEIPT_HEAD_KEY,
    RECEIPT_RULED_OUT_KEY,
    RECEIPT_RULING_LINES_KEY,
    RECEIPT_RULINGS_KEY,
    REPOSITORY_SLUG_PATTERN,
    RULING_LOOKUP_TIMEOUT_SECONDS,
    RULING_REFERENCE_PATTERN,
    RULING_SEPARATOR,
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
    receipt = _receipt_fields(
        head, finding_count, ruled_out_count, RECEIPT_RULINGS_KEY, rulings
    )
    return _write_receipt(slug, number, receipt)


def record_open_review(
    slug: str, head: str, finding_count: int, all_rulings: Sequence[str] = ()
) -> Path:
    """Write the receipt for one review pass run before the pull request opens.

    Args:
        slug: Repository as ``owner/name``.
        head: The commit the pass reviewed.
        finding_count: How many findings the pass reported.
        all_rulings: One ``path:line`` of evidence for each ruled out finding.
            Run in the checkout that holds ``head``.

    Returns:
        The receipt path written.

    Raises:
        ValueError: A ruling is malformed, repeated, or names a line ``head`` lacks.
    """
    problem = _ruling_problem(head, all_rulings)
    if problem:
        raise ValueError(problem)
    return _write_open_receipt(slug, head, _open_receipt(head, finding_count, all_rulings))


def _write_open_receipt(slug: str, head: str, all_receipt_fields: dict[str, object]) -> Path:
    owner, repo = slug.split("/", 1)
    return _write_receipt_at(open_receipt_path(owner, repo, head), all_receipt_fields)


def _write_receipt(slug: str, number: int, all_receipt_fields: dict[str, object]) -> Path:
    owner, repo = slug.split("/", 1)
    return _write_receipt_at(receipt_path(owner, repo, number), all_receipt_fields)


def _write_receipt_at(path: Path, all_receipt_fields: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(all_receipt_fields) + "\n", encoding="utf-8")
    return path


def _receipt_fields(
    head: str, finding_count: int, ruled_out_count: int, ruling_key: str, ruling_entry: object
) -> dict[str, object]:
    receipt: dict[str, object] = {RECEIPT_HEAD_KEY: head, RECEIPT_FINDINGS_KEY: finding_count}
    if ruled_out_count:
        receipt[RECEIPT_RULED_OUT_KEY] = ruled_out_count
        receipt[ruling_key] = ruling_entry
    return receipt


def _blob_line_count(head: str, file_path: str) -> int:
    try:
        completed = subprocess.run(
            ["git", "cat-file", "blob", f"{head}:{file_path}"],
            capture_output=True,
            timeout=RULING_LOOKUP_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    return _line_count(completed.stdout) if completed.returncode == 0 else 0


def _unproven_rulings(head: str, all_rulings: Sequence[str]) -> list[str]:
    all_line_counts: dict[str, int] = {}
    all_unproven: list[str] = []
    for each_ruling in all_rulings:
        file_path, _, line_number = each_ruling.rpartition(":")
        if file_path not in all_line_counts:
            all_line_counts[file_path] = _blob_line_count(head, file_path)
        if int(line_number) > all_line_counts[file_path]:
            all_unproven.append(each_ruling)
    return all_unproven


def _line_count(content: bytes) -> int:
    if not content:
        return 0
    return content.count(b"\n") + (0 if content.endswith(b"\n") else 1)


def _split_rulings(rulings: str) -> list[str]:
    all_entries = (each_entry.strip() for each_entry in rulings.split(RULING_SEPARATOR))
    return [each_entry for each_entry in all_entries if each_entry]


def _open_receipt(
    head: str, finding_count: int, all_rulings: Sequence[str]
) -> dict[str, object]:
    return _receipt_fields(
        head, finding_count, len(all_rulings), RECEIPT_RULING_LINES_KEY, list(all_rulings)
    )


def _ruling_problem(head: str, all_rulings: Sequence[str]) -> str | None:
    all_malformed = [
        each_ruling
        for each_ruling in all_rulings
        if RULING_REFERENCE_PATTERN.fullmatch(each_ruling) is None
    ]
    if all_malformed:
        return (
            "--rulings needs path:line, with / between folders, no backslash, colon, comma "
            "or . and .. segment in the path, and a line from 1, not "
            f"{RULING_SEPARATOR.join(all_malformed)}"
        )
    if len(set(all_rulings)) != len(all_rulings):
        return "--rulings needs a different path:line for each finding"
    all_unproven = _unproven_rulings(head, all_rulings)
    if all_unproven:
        return (
            f"run this in the checkout that holds {head}; it has no file and line at "
            f"{RULING_SEPARATOR.join(all_unproven)}"
        )
    return None


def _checked_open_rulings(
    parser: argparse.ArgumentParser, parsed: argparse.Namespace
) -> list[str]:
    if parsed.ruled_out < 0 or parsed.ruled_out > parsed.findings:
        parser.error("--ruled-out must be between 0 and the finding count")
    all_rulings = _split_rulings(parsed.rulings)
    if len(all_rulings) != parsed.ruled_out:
        parser.error("--rulings needs one path:line for each finding --ruled-out counts")
    return all_rulings


def _record_open_pass(
    parser: argparse.ArgumentParser, parsed: argparse.Namespace, stdout: TextIO
) -> int:
    if parsed.findings < 0:
        parser.error("findings must be zero or more")
    if not OPEN_RECEIPT_HEAD_PATTERN.fullmatch(parsed.head):
        parser.error(f"an {OPEN_TARGET_WORD} pass needs the full 40 character commit")
    all_rulings = _checked_open_rulings(parser, parsed)
    try:
        record_open_review(parsed.slug, parsed.head, parsed.findings, all_rulings)
    except ValueError as problem:
        parser.error(str(problem))
    if is_clean_open_pass(_open_receipt(parsed.head, parsed.findings, all_rulings)):
        ruled_out_note = (
            f" ({parsed.ruled_out} findings ruled out: {RULING_SEPARATOR.join(all_rulings)})"
            if parsed.ruled_out
            else ""
        )
        stdout.write(f"CLEAN {parsed.slug} {OPEN_TARGET_WORD} {parsed.head}{ruled_out_note}\n")
        return 0
    stdout.write(
        f"REVIEWED {parsed.slug} {OPEN_TARGET_WORD} {parsed.head} {parsed.findings} findings\n"
    )
    return 1


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
    parser.add_argument(
        "--rulings",
        default="",
        help=(
            "Link to the posted rulings. For an open pass, a different path:line for each "
            "ruled out finding, comma separated."
        ),
    )
    parsed = parser.parse_args(all_arguments)
    rulings = parsed.rulings.strip()
    if not REPOSITORY_SLUG_PATTERN.fullmatch(parsed.slug) or ".." in parsed.slug:
        parser.error("slug must be owner/name")
    if parsed.number == OPEN_TARGET_WORD:
        return _record_open_pass(parser, parsed, stdout)
    if not parsed.number.isdigit():
        parser.error(f"number must be a pull request number or {OPEN_TARGET_WORD}")
    parsed.number = int(parsed.number)
    if parsed.ruled_out < 0 or parsed.ruled_out > parsed.findings:
        parser.error("--ruled-out must be between 0 and the finding count")
    if parsed.ruled_out and not rulings:
        parser.error("--ruled-out needs --rulings, a link to the posted rulings")
    if rulings and not parsed.ruled_out:
        parser.error("--rulings needs --ruled-out, the count of findings it rules out")
    receipt = _receipt_fields(
        parsed.head, parsed.findings, parsed.ruled_out, RECEIPT_RULINGS_KEY, rulings
    )
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
