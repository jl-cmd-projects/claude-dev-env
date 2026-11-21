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

Each numbered receipt counts its pass on the pull request. A new head is the
next pass, and recording the same head again keeps its pass. The loop runs
three full passes with fixes. When pass 4 or a later one still reports
findings, they go into one issue in the same repository, and the pass is
recorded with the issue link. Findings it rules out are left out of that
issue::

    python3 merge_review_receipt.py owner/name 12 aaa9999 3 --ruled-out 1 --rulings <url> --filed <issue url>
        -> FILED owner/name#12 aaa9999 (2 findings filed: <issue url>)

Before pass 4, ``--filed`` is refused. The script reads the issue through
the GitHub command-line client and refuses a link that names no issue in
that repository, such as a missing number or a pull request.

A pass run before the pull request exists names ``open`` in place of the
number, and records the head it reviewed::

    python3 merge_review_receipt.py owner/name open def5678 0   -> CLEAN owner/name open def5678

No pull request exists to hold a rulings comment, so an ``open`` pass rules
out its findings with a different ``path:line`` for each, run in the checkout
that holds the head. Each line must exist in the file at that head::

    python3 merge_review_receipt.py owner/name open def5678 2 --ruled-out 2 --rulings a.py:1,b.py:20
        -> CLEAN owner/name open def5678 (2 findings ruled out: a.py:1,b.py:20)

``hooks/blocking/merge_review_gate.py`` allows a merge pinned to the head of
the newest pass only when that pass is clean or filed. It allows a pull request open
whose head has a clean ``open`` pass. It allows a merge pinned to that same
head only when the ``open`` pass found zero findings. Ruled-out findings need
a numbered pass that links the rulings comment on the pull request.
"""

from __future__ import annotations

import argparse
import json
import shutil
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
    is_filed_receipt,
    is_issue_link_in,
    is_past_full_passes,
    open_receipt_path,
    read_receipt,
    receipt_path,
    recorded_pass_number,
    same_commit,
)
from hooks_constants.merge_review_gate_constants import (
    FILED_ISSUE_API_PATH_TEMPLATE,
    FILED_ISSUE_API_SUBCOMMAND,
    FILED_ISSUE_CLIENT_NAME,
    FILED_ISSUE_LINK_PATTERN,
    FILED_ISSUE_LOOKUP_TIMEOUT_SECONDS,
    FILED_ISSUE_PAGE_KEY,
    FILED_ISSUE_PULL_REQUEST_KEY,
    FULL_REVIEW_PASS_COUNT,
    OPEN_RECEIPT_HEAD_PATTERN,
    OPEN_TARGET_WORD,
    RECEIPT_FILED_KEY,
    RECEIPT_FINDINGS_KEY,
    RECEIPT_HEAD_KEY,
    RECEIPT_PASS_KEY,
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
    filed: str = "",
) -> Path:
    """Write the receipt for one review pass, replacing the previous pass.

    Args:
        slug: Repository as ``owner/name``.
        number: Pull request number.
        head: The commit the pass reviewed.
        finding_count: How many findings the pass reported.
        ruled_out_count: How many of those findings were ruled out.
        rulings: Link to the posted rulings, empty when none were ruled out.
        filed: Link to the issue that lists the findings left open, empty when none were filed.

    Returns:
        The receipt path written.
    """
    receipt = _numbered_receipt(
        head,
        finding_count,
        ruled_out_count,
        rulings,
        filed,
        _next_pass_number(slug, number, head),
    )
    return _write_receipt(slug, number, receipt)


def _next_pass_number(slug: str, number: int, head: str) -> int:
    """Return which review pass on the pull request a record of ``head`` is.

    A new head is the next pass. Recording the head the previous receipt names
    again, such as after posting rulings or filing an issue, keeps its pass::

        no receipt yet                         -> 1
        previous receipt pass 3 at abc1234, head def5678 -> 4
        previous receipt pass 3 at abc1234, head abc1234 -> 3

    A previous receipt that cannot be read counts as no receipt.

    Args:
        slug: Repository as ``owner/name``.
        number: Pull request number.
        head: The commit the pass reviewed.

    Returns:
        The pass number, from 1.
    """
    owner, repo = slug.split("/", 1)
    previous_receipt = read_receipt(receipt_path(owner, repo, number))
    if previous_receipt is None:
        return 1
    previous_pass_number = recorded_pass_number(previous_receipt)
    previous_head = previous_receipt.get(RECEIPT_HEAD_KEY)
    is_same_pass = isinstance(previous_head, str) and bool(previous_head) and same_commit(
        previous_head, head
    )
    return previous_pass_number if is_same_pass else previous_pass_number + 1


def _numbered_receipt(
    head: str,
    finding_count: int,
    ruled_out_count: int,
    rulings: str,
    filed: str,
    pass_number: int,
) -> dict[str, object]:
    receipt = _receipt_fields(head, finding_count, ruled_out_count, RECEIPT_RULINGS_KEY, rulings)
    receipt[RECEIPT_PASS_KEY] = pass_number
    if filed:
        receipt[RECEIPT_FILED_KEY] = filed
    return receipt


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
    if parsed.filed.strip():
        parser.error(
            f"an {OPEN_TARGET_WORD} pass cannot take --filed: findings are filed only after "
            f"{FULL_REVIEW_PASS_COUNT} full passes with fixes on the pull request"
        )
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
        0 for a clean pass or a pass whose open findings were filed after three full
        passes, and 1 for a pass with findings still open.
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
    parser.add_argument(
        "--filed",
        default="",
        help=(
            "Link to the one issue in this repository that lists the findings this pass "
            f"left open. Only from pass {FULL_REVIEW_PASS_COUNT + 1}, after "
            f"{FULL_REVIEW_PASS_COUNT} full passes with fixes."
        ),
    )
    parsed = parser.parse_args(all_arguments)
    if not REPOSITORY_SLUG_PATTERN.fullmatch(parsed.slug) or ".." in parsed.slug:
        parser.error("slug must be owner/name")
    if parsed.number == OPEN_TARGET_WORD:
        return _record_open_pass(parser, parsed, stdout)
    if not parsed.number.isdigit():
        parser.error(f"number must be a pull request number or {OPEN_TARGET_WORD}")
    parsed.number = int(parsed.number)
    return _record_numbered_pass(parser, parsed, stdout)


def _checked_filed_link(
    parser: argparse.ArgumentParser, parsed: argparse.Namespace, pass_number: int
) -> str:
    filed = parsed.filed.strip()
    if not filed:
        return filed
    owner, repo = parsed.slug.split("/", 1)
    if not is_issue_link_in(filed, owner, repo, parsed.number):
        parser.error(
            f"--filed needs the link of an issue in {parsed.slug}, and not this pull request's own number"
        )
    if parsed.findings - parsed.ruled_out < 1:
        parser.error("--filed needs findings left after --ruled-out to file")
    if not is_past_full_passes(pass_number):
        parser.error(
            f"--filed is for pass {FULL_REVIEW_PASS_COUNT + 1} or later, and this is pass "
            f"{pass_number}. The first {FULL_REVIEW_PASS_COUNT} full passes with fixes come "
            "first: fix and push every finding, then review the new head."
        )
    if not _is_served_issue(filed, owner, repo):
        parser.error(
            f"--filed {filed} is not an issue GitHub serves in {parsed.slug}: file the issue "
            "first and pass its link, and check that gh can read the repository"
        )
    return filed


def _is_served_issue(link: str, owner: str, repo: str) -> bool:
    """Return whether GitHub serves the link as an issue of this repository.

    The link must name an issue that exists, that is not a pull request, and
    whose page GitHub gives in this same repository::

        issue 40 exists in acme/tools                 -> served
        no issue 40, or gh cannot read the repository -> not served
        40 is a pull request                          -> not served
        GitHub answers with acme/elsewhere issue 7    -> not served

    Args:
        link: The issue link the pass names, already matched to this repository.
        owner: Repository owner.
        repo: Repository name.

    Returns:
        True when the GitHub API answers with that same issue.
    """
    issue_match = FILED_ISSUE_LINK_PATTERN.fullmatch(link)
    client_path = shutil.which(FILED_ISSUE_CLIENT_NAME)
    if issue_match is None or client_path is None:
        return False
    api_path = FILED_ISSUE_API_PATH_TEMPLATE.format(
        owner=owner, repo=repo, number=issue_match["number"]
    )
    try:
        completed = subprocess.run(
            [client_path, FILED_ISSUE_API_SUBCOMMAND, api_path],
            capture_output=True,
            text=True,
            timeout=FILED_ISSUE_LOOKUP_TIMEOUT_SECONDS,
            check=False,
        )
        served_issue = json.loads(completed.stdout) if completed.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return (
        isinstance(served_issue, dict)
        and FILED_ISSUE_PULL_REQUEST_KEY not in served_issue
        and str(served_issue.get(FILED_ISSUE_PAGE_KEY, "")).casefold() == link.casefold()
    )


def _checked_rulings_link(parser: argparse.ArgumentParser, parsed: argparse.Namespace) -> str:
    rulings = parsed.rulings.strip()
    if parsed.ruled_out < 0 or parsed.ruled_out > parsed.findings:
        parser.error("--ruled-out must be between 0 and the finding count")
    if parsed.ruled_out and not rulings:
        parser.error("--ruled-out needs --rulings, a link to the posted rulings")
    if rulings and not parsed.ruled_out:
        parser.error("--rulings needs --ruled-out, the count of findings it rules out")
    return rulings


def _record_numbered_pass(
    parser: argparse.ArgumentParser, parsed: argparse.Namespace, stdout: TextIO
) -> int:
    rulings = _checked_rulings_link(parser, parsed)
    pass_number = _next_pass_number(parsed.slug, parsed.number, parsed.head)
    filed = _checked_filed_link(parser, parsed, pass_number)
    receipt = _numbered_receipt(
        parsed.head, parsed.findings, parsed.ruled_out, rulings, filed, pass_number
    )
    _write_receipt(parsed.slug, parsed.number, receipt)
    owner, repo = parsed.slug.split("/", 1)
    target = f"{parsed.slug}#{parsed.number} {parsed.head}"
    if is_clean_receipt(receipt, owner, repo, parsed.number):
        ruled_out_note = (
            f" ({parsed.ruled_out} findings ruled out: {rulings})" if parsed.ruled_out else ""
        )
        stdout.write(f"CLEAN {target}{ruled_out_note}\n")
        return 0
    if is_filed_receipt(receipt, owner, repo, parsed.number):
        stdout.write(f"FILED {target} ({parsed.findings - parsed.ruled_out} findings filed: {filed})\n")
        return 0
    unfiled_note = _unfiled_note(pass_number, filed, rulings)
    stdout.write(f"REVIEWED {target} {parsed.findings} findings{unfiled_note}\n")
    return 1


def _unfiled_note(pass_number: int, filed: str, rulings: str) -> str:
    if not is_past_full_passes(pass_number):
        return ""
    if filed and rulings:
        return (
            f" (pass {pass_number}: not filed, because --rulings {rulings} is not an issue "
            "comment link (#issuecomment-) on this pull request; post the rulings as a comment "
            "on this pull request and record this pass again with that link)"
        )
    return (
        f" (pass {pass_number}: {FULL_REVIEW_PASS_COUNT} full passes are done, so file "
        "these findings in one issue and record this pass again with --filed <issue url>; "
        "fix a security finding in this pull request instead)"
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
