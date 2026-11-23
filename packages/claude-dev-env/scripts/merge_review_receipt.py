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
next pass, and recording the same head again keeps its pass. The first record
of a pull request with no receipt, and a record with ``--filed``, also read
GitHub: the pass is never lower than one more than the earlier commits of the
pull request whose Merge review status failed, run by the review workflow for
this repository, pull request number and commit, so the count survives a new
session::

    no receipt, 3 earlier commits with a failing review status -> pass 4
    REVIEWED owner/name#12 def5678 2 findings (pass 4: file these findings ...)

The loop runs
three full passes with fixes. When pass 4 or a later one still reports
findings, they go into one issue in the same repository, and the pass is
recorded with the issue link. Findings it rules out are left out of that
issue::

    python3 merge_review_receipt.py owner/name 12 aaa9999 3 --ruled-out 1 --rulings <url> --filed <issue url>
        -> FILED owner/name#12 aaa9999 (2 findings filed: <issue url>)

Before pass 4, ``--filed`` is refused. The script reads the issue through
the GitHub command-line client and refuses a link that names no issue in
that repository, such as a missing number or a pull request.

One review pass runs before the pull request exists. It names ``open`` in
place of the number and records the head it reviewed. Its findings are fixed
in new commits on top of that head, and the pull request opens with no
second pass::

    python3 merge_review_receipt.py owner/name open def5678 0   -> CLEAN owner/name open def5678
    python3 merge_review_receipt.py owner/name open def5678 2   -> REVIEWED owner/name open def5678 2 findings (fix them ...)
    commit the fixes on top of def5678, then open the pull request

No pull request exists to hold a rulings comment, so an ``open`` pass rules
out its findings with a different ``path:line`` for each, run in the checkout
that holds the head. Each line must exist in the file at that head::

    python3 merge_review_receipt.py owner/name open def5678 2 --ruled-out 2 --rulings a.py:1,b.py:20
        -> CLEAN owner/name open def5678 (2 findings ruled out: a.py:1,b.py:20)

``hooks/blocking/merge_review_gate.py`` allows a merge pinned to the head of
the newest pass only when that pass is clean or filed. It allows a pull request open
whose head has a clean ``open`` pass, or whose head sits on fix commits above the
head of an ``open`` pass recorded on the same branch, under the checks
``merge_review_gate.py`` lists. A pass recorded outside that branch's checkout
names no branch, counts only at its own head, and its verdict line says to
record it again from the checkout. An ``open`` pass does not take ``--filed`` and does
not count toward the three full passes on the pull request. It allows a merge pinned to that same
head only when the ``open`` pass found zero findings. Ruled-out findings need
a numbered pass that links the rulings comment on the pull request.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
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
    ALL_BRANCH_REFERENCE_PREFIXES,
    ALL_CHECKOUT_BRANCH_ARGUMENTS,
    ALL_HOLDING_REFERENCE_ARGUMENTS,
    ALL_STORED_HISTORY_GIT_SETTINGS,
    COMMIT_SHA_KEY,
    COMMIT_STATUSES_API_PATH_TEMPLATE,
    CONTAINS_OPTION_TEMPLATE,
    CREATOR_LOGIN_KEY,
    CREATOR_TYPE_KEY,
    EARLIER_COMMIT_READ_LIMIT,
    FAILED_REVIEW_STATUS_STATE,
    FILED_ISSUE_API_PATH_TEMPLATE,
    FILED_ISSUE_LINK_PATTERN,
    FILED_ISSUE_PAGE_KEY,
    FILED_ISSUE_PULL_REQUEST_KEY,
    FULL_REVIEW_PASS_COUNT,
    GITHUB_API_CLIENT_NAME,
    GITHUB_API_HOST,
    GITHUB_API_HOST_OPTION,
    GITHUB_API_READ_TIMEOUT_SECONDS,
    GITHUB_API_STOP_POLL_SECONDS,
    GITHUB_API_SUBCOMMAND,
    GITHUB_COUNT_DEADLINE_SECONDS,
    LOCAL_BRANCH_REFERENCE_TEMPLATE,
    MERGE_REVIEW_STATUS_CONTEXT,
    OPEN_RECEIPT_HEAD_PATTERN,
    OPEN_TARGET_WORD,
    PULL_REQUEST_COMMITS_API_PATH_TEMPLATE,
    PULL_REQUEST_COMMITS_PAGE_LIMIT,
    PULL_REQUEST_COMMITS_PAGE_SIZE,
    RECEIPT_BRANCH_KEY,
    RECEIPT_FILED_KEY,
    RECEIPT_FINDINGS_KEY,
    RECEIPT_HEAD_KEY,
    RECEIPT_PASS_KEY,
    RECEIPT_RULED_OUT_KEY,
    RECEIPT_RULING_LINES_KEY,
    RECEIPT_RULINGS_KEY,
    REMOTE_TRACKING_REFERENCE_PREFIX,
    REPOSITORY_SLUG_PATTERN,
    REVIEW_RUN_API_PATH_TEMPLATE,
    REVIEW_RUN_COMPLETED_STATUS,
    REVIEW_RUN_SUCCESS_CONCLUSION,
    REVIEW_RUN_TITLE_TEMPLATE,
    REVIEW_RUN_TITLE_HEAD_PATTERN,
    REVIEW_RUNS_API_PATH_TEMPLATE,
    REVIEW_RUNS_KEY,
    REVIEW_RUNS_PAGE_LIMIT,
    REVIEW_RUNS_PAGE_SIZE,
    REVIEW_RUNS_REPOSITORY_ENVIRONMENT_VARIABLE,
    REVIEW_RUNS_REPOSITORY_PATTERN,
    PULL_REQUEST_API_PATH_TEMPLATE,
    PULL_REQUEST_CREATED_AT_KEY,
    ISO_DATE_LENGTH,
    REVIEW_RUN_WORKFLOW_FILE,
    REVIEW_STATUS_APP_LOGIN,
    REVIEW_STATUS_CREATOR_TYPE,
    REVIEW_STATUS_RUN_PAGE_PATTERN,
    RULING_LOOKUP_TIMEOUT_SECONDS,
    RULING_REFERENCE_PATTERN,
    RULING_SEPARATOR,
    RUN_CONCLUSION_KEY,
    RUN_ID_KEY,
    RUN_PATH_KEY,
    RUN_STATUS_KEY,
    RUN_TITLE_KEY,
    STATUS_CONTEXT_KEY,
    STATUS_CREATOR_KEY,
    STATUS_READ_WORKER_COUNT,
    STATUS_STATE_KEY,
    STATUS_TARGET_URL_KEY,
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
        _next_pass_number(slug, number, head, should_read_github=bool(filed.strip())),
    )
    return _write_receipt(slug, number, receipt)


def _next_pass_number(
    slug: str, number: int, head: str, should_read_github: bool = False
) -> int:
    """Return which review pass on the pull request a record of ``head`` is.

    A new head is the next pass. Recording the head the previous receipt names
    again, such as after posting rulings or filing an issue, keeps its pass,
    unless the GitHub count below raises it. A record with no receipt before
    it, and a record that carries ``--filed``, also read GitHub, so a new
    session keeps the count: the pass is never lower than one more than the
    earlier commits of this pull request whose Merge review status GitHub
    shows as failing::

        no receipt, no failing reviews                   -> 1
        previous receipt pass 3 at abc1234, head def5678 -> 4
        previous receipt pass 3 at abc1234, head abc1234 -> 3
        no receipt, 3 earlier failing reviews            -> 4
        --filed, previous receipt pass 1, 3 earlier ones -> 4

    A previous receipt that cannot be read counts as no receipt. A local pass
    past the full pass count already allows a filed pass, so GitHub is not
    read for it.

    Args:
        slug: Repository as ``owner/name``.
        number: Pull request number.
        head: The commit the pass reviewed.
        should_read_github: True when the record carries ``--filed``.

    Returns:
        The pass number, from 1.
    """
    owner, repo = slug.split("/", 1)
    previous_receipt = read_receipt(receipt_path(owner, repo, number))
    local_pass_number = _local_pass_number(previous_receipt, head)
    is_fresh_session = previous_receipt is None
    if not (should_read_github or is_fresh_session) or local_pass_number > FULL_REVIEW_PASS_COUNT:
        return local_pass_number
    reviewed_pass_number = _failed_review_head_count(owner, repo, number, head) + 1
    return max(local_pass_number, reviewed_pass_number)


def _local_pass_number(all_previous_receipt_fields: dict[str, object] | None, head: str) -> int:
    if all_previous_receipt_fields is None:
        return 1
    previous_pass_number = recorded_pass_number(all_previous_receipt_fields)
    previous_head = all_previous_receipt_fields.get(RECEIPT_HEAD_KEY)
    is_same_pass = isinstance(previous_head, str) and bool(previous_head) and same_commit(
        previous_head, head
    )
    return previous_pass_number if is_same_pass else previous_pass_number + 1


def _failed_review_head_count(owner: str, repo: str, number: int, head: str) -> int:
    """Return how many earlier commits of the pull request had a failing review run.

    Earlier commits are the ones the pull request lists before the head. The
    count is 0 when any page of the list cannot be read or the head is not in
    it, so it only ever raises a pass. A commit counts when its newest
    ``Merge review`` status is ``failure``, the review app posted it, and its
    link is a GitHub Actions run of the review workflow that succeeded and is
    titled for this repository, this pull request and that commit. The walk
    starts at the newest earlier commit, reads at most a fixed number of them
    in parallel within one deadline, and stops at the full pass count. Reads
    still running at that point are stopped. Examples::

        commits c1 (failing review run), c2 (none), head -> 1
        commits c1, head, c2 (failing review run)        -> 0
        commit c1 (failure by another app), head         -> 0
        commit c1 (run titled for another pull request)  -> 0
        commit list page 2 unreadable                    -> 0
        head missing from the commit list                -> 0

    Args:
        owner: Repository owner.
        repo: Repository name.
        number: Pull request number.
        head: The commit the pass reviewed, left out of the count.

    Returns:
        The count, from 0 to the full pass count.
    """
    deadline = time.monotonic() + GITHUB_COUNT_DEADLINE_SECONDS
    all_earlier_shas = _commits_before_head(owner, repo, number, head, deadline)
    all_newest_first_shas = list(reversed(all_earlier_shas[-EARLIER_COMMIT_READ_LIMIT:]))
    all_newest_first_shas += [
        each_sha
        for each_sha in _reviewed_heads_by_run_title(owner, repo, number, deadline)
        if not same_commit(each_sha, head)
        and not any(same_commit(each_sha, each_listed) for each_listed in all_newest_first_shas)
    ]
    stop_reading = threading.Event()
    executor = ThreadPoolExecutor(max_workers=STATUS_READ_WORKER_COUNT)
    try:
        all_reads = [
            executor.submit(
                _is_failed_review_commit, owner, repo, number, each_sha, deadline, stop_reading
            )
            for each_sha in all_newest_first_shas
        ]
        return _count_failed_reviews(all_reads)
    finally:
        stop_reading.set()
        executor.shutdown(wait=True, cancel_futures=True)


def _count_failed_reviews(all_reads: list[Future[bool]]) -> int:
    failed_count = 0
    for each_read in as_completed(all_reads):
        failed_count += 1 if each_read.result() else 0
        if failed_count >= FULL_REVIEW_PASS_COUNT:
            return FULL_REVIEW_PASS_COUNT
    return failed_count


def _is_failed_review_commit(
    owner: str, repo: str, number: int, sha: str, deadline: float, stop_reading: threading.Event
) -> bool:
    all_statuses = _github_answer(
        COMMIT_STATUSES_API_PATH_TEMPLATE.format(owner=owner, repo=repo, sha=sha),
        deadline,
        stop_reading,
    )
    return isinstance(all_statuses, list) and _is_review_app_failure(
        all_statuses, f"{owner}/{repo}", number, sha, deadline, stop_reading
    )


def _reviewed_heads_by_run_title(
    owner: str, repo: str, number: int, deadline: float
) -> list[str]:
    """Return the heads that review runs titled for this pull request name.

    The runs live in the repository that the review runs setting names, so
    the heads a rebase dropped from the commit list still count. With the
    setting unset or malformed, or the pull request unreadable, no head is
    added::

        setting unset                                  -> []
        run titled acme/tools#12 <sha> base main       -> [sha]
        run titled acme/tools#13 <sha> base main       -> []
        run titled acme/tools# <sha> base main         -> []

    Args:
        owner: Repository owner.
        repo: Repository name.
        number: Pull request number.
        deadline: The monotonic time after which no read starts.

    Returns:
        The heads, newest run first, each once.
    """
    runs_repository = os.environ.get(REVIEW_RUNS_REPOSITORY_ENVIRONMENT_VARIABLE, "").strip()
    if REVIEW_RUNS_REPOSITORY_PATTERN.fullmatch(runs_repository) is None:
        return []
    pull_request = _github_answer(
        PULL_REQUEST_API_PATH_TEMPLATE.format(owner=owner, repo=repo, number=number), deadline
    )
    created_at = pull_request.get(PULL_REQUEST_CREATED_AT_KEY) if isinstance(pull_request, dict) else None
    if not isinstance(created_at, str) or len(created_at) < ISO_DATE_LENGTH:
        return []
    title_pattern = re.compile(
        REVIEW_RUN_TITLE_TEMPLATE.format(
            repository=re.escape(f"{owner}/{repo}"), number=number, head=REVIEW_RUN_TITLE_HEAD_PATTERN
        ),
        re.IGNORECASE,
    )
    all_heads: list[str] = []
    for each_page in range(1, REVIEW_RUNS_PAGE_LIMIT + 1):
        all_page_runs = _review_runs_page(runs_repository, created_at[:ISO_DATE_LENGTH], each_page, deadline)
        all_heads += [
            each_head
            for each_head in _titled_heads(all_page_runs, title_pattern)
            if each_head not in all_heads
        ]
        if len(all_page_runs) < REVIEW_RUNS_PAGE_SIZE:
            break
    return all_heads


def _review_runs_page(
    runs_repository: str, created_on: str, page: int, deadline: float
) -> list[object]:
    runs_answer = _github_answer(
        REVIEW_RUNS_API_PATH_TEMPLATE.format(
            repository=runs_repository,
            workflow=REVIEW_RUN_WORKFLOW_FILE,
            page=page,
            created_on=created_on,
        ),
        deadline,
    )
    all_page_runs = runs_answer.get(REVIEW_RUNS_KEY) if isinstance(runs_answer, dict) else None
    return all_page_runs if isinstance(all_page_runs, list) else []


def _titled_heads(all_runs: list[object], title_pattern: re.Pattern[str]) -> list[str]:
    all_heads: list[str] = []
    for each_run in all_runs:
        title = each_run.get(RUN_TITLE_KEY) if isinstance(each_run, dict) else None
        title_match = title_pattern.fullmatch(title) if isinstance(title, str) else None
        if title_match is not None:
            all_heads.append(title_match["head"].lower())
    return all_heads


def _commits_before_head(
    owner: str, repo: str, number: int, head: str, deadline: float
) -> list[str]:
    all_earlier_shas: list[str] = []
    for each_page in range(1, PULL_REQUEST_COMMITS_PAGE_LIMIT + 1):
        all_page_commits = _github_answer(
            PULL_REQUEST_COMMITS_API_PATH_TEMPLATE.format(
                owner=owner, repo=repo, number=number, page=each_page
            ),
            deadline,
        )
        if not isinstance(all_page_commits, list):
            return []
        all_page_shas = _commit_shas_in(all_page_commits)
        head_index = next(
            (
                each_index
                for each_index, each_sha in enumerate(all_page_shas)
                if same_commit(each_sha, head)
            ),
            None,
        )
        if head_index is not None:
            return all_earlier_shas + all_page_shas[:head_index]
        all_earlier_shas.extend(all_page_shas)
        if len(all_page_commits) < PULL_REQUEST_COMMITS_PAGE_SIZE:
            return []
    return []


def _commit_shas_in(all_commits: list[object]) -> list[str]:
    return [
        each_commit[COMMIT_SHA_KEY]
        for each_commit in all_commits
        if isinstance(each_commit, dict) and isinstance(each_commit.get(COMMIT_SHA_KEY), str)
    ]


def _review_run_page_of_failure(all_statuses: list[object]) -> re.Match[str] | None:
    newest = next(
        (
            each_status
            for each_status in all_statuses
            if isinstance(each_status, dict)
            and each_status.get(STATUS_CONTEXT_KEY) == MERGE_REVIEW_STATUS_CONTEXT
        ),
        None,
    )
    if newest is None or newest.get(STATUS_STATE_KEY) != FAILED_REVIEW_STATUS_STATE:
        return None
    creator = newest.get(STATUS_CREATOR_KEY)
    if (
        not isinstance(creator, dict)
        or creator.get(CREATOR_TYPE_KEY) != REVIEW_STATUS_CREATOR_TYPE
        or creator.get(CREATOR_LOGIN_KEY) != REVIEW_STATUS_APP_LOGIN
    ):
        return None
    return REVIEW_STATUS_RUN_PAGE_PATTERN.fullmatch(str(newest.get(STATUS_TARGET_URL_KEY, "")))


def _is_review_app_failure(
    all_statuses: list[object],
    repository: str,
    number: int,
    sha: str,
    deadline: float,
    stop_reading: threading.Event,
) -> bool:
    run_page = _review_run_page_of_failure(all_statuses)
    if run_page is None:
        return False
    review_run = _github_answer(
        REVIEW_RUN_API_PATH_TEMPLATE.format(
            repository=run_page["repository"], run_id=run_page["run_id"]
        ),
        deadline,
        stop_reading,
    )
    return _is_successful_review_run_for(
        review_run, int(run_page["run_id"]), repository, number, sha
    )


def _is_successful_review_run_for(
    review_run: object, run_id: int, repository: str, number: int, sha: str
) -> bool:
    if not isinstance(review_run, dict):
        return False
    workflow_path = review_run.get(RUN_PATH_KEY)
    title_pattern = REVIEW_RUN_TITLE_TEMPLATE.format(
        repository=re.escape(repository), number=number, head=re.escape(sha)
    )
    return (
        review_run.get(RUN_ID_KEY) == run_id
        and isinstance(workflow_path, str)
        and workflow_path.split("@", 1)[0].rsplit("/", 1)[-1] == REVIEW_RUN_WORKFLOW_FILE
        and review_run.get(RUN_STATUS_KEY) == REVIEW_RUN_COMPLETED_STATUS
        and review_run.get(RUN_CONCLUSION_KEY) == REVIEW_RUN_SUCCESS_CONCLUSION
        and re.fullmatch(title_pattern, str(review_run.get(RUN_TITLE_KEY, "")), re.IGNORECASE)
        is not None
    )


def _github_answer(
    api_path: str, deadline: float | None = None, stop_reading: threading.Event | None = None
) -> object:
    client_path = shutil.which(GITHUB_API_CLIENT_NAME)
    if client_path is None:
        return None
    timeout_seconds = GITHUB_API_READ_TIMEOUT_SECONDS
    if deadline is not None:
        timeout_seconds = min(timeout_seconds, deadline - time.monotonic())
    if timeout_seconds <= 0:
        return None
    try:
        with subprocess.Popen(
            [
                client_path,
                GITHUB_API_SUBCOMMAND,
                GITHUB_API_HOST_OPTION,
                GITHUB_API_HOST,
                api_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ) as read_process:
            return _read_process_answer(read_process, timeout_seconds, stop_reading)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _read_process_answer(
    read_process: subprocess.Popen[bytes],
    timeout_seconds: float,
    stop_reading: threading.Event | None,
) -> object:
    give_up_at = time.monotonic() + timeout_seconds
    while True:
        if (stop_reading is not None and stop_reading.is_set()) or time.monotonic() >= give_up_at:
            read_process.kill()
            return None
        try:
            answer_bytes, _ = read_process.communicate(timeout=GITHUB_API_STOP_POLL_SECONDS)
        except subprocess.TimeoutExpired:
            continue
        return json.loads(answer_bytes) if read_process.returncode == 0 else None


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

    The receipt names the branch checked out in the current folder when
    ``head`` is that branch's own work, so the gate credits fix commits on top
    of ``head`` only to that branch::

        on feature, no other branch holds head        -> branch: feature
        on second, feature or origin/feature holds it -> no branch
        detached checkout, or a branch read fails     -> no branch

    A receipt with no branch counts only at ``head``.

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
    all_receipt_fields = _open_receipt(head, finding_count, all_rulings)
    branch = _checkout_branch()
    if branch and _is_own_work_of(branch, head):
        all_receipt_fields[RECEIPT_BRANCH_KEY] = branch
    return _write_open_receipt(slug, head, all_receipt_fields)


def _checkout_branch() -> str | None:
    try:
        completed = subprocess.run(
            ["git", *ALL_CHECKOUT_BRANCH_ARGUMENTS],
            capture_output=True,
            text=True,
            timeout=RULING_LOOKUP_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def _is_own_work_of(branch: str, head: str) -> bool:
    try:
        completed = subprocess.run(
            [
                "git",
                *ALL_HOLDING_REFERENCE_ARGUMENTS,
                CONTAINS_OPTION_TEMPLATE.format(commit=head),
                *ALL_BRANCH_REFERENCE_PREFIXES,
            ],
            capture_output=True,
            text=True,
            timeout=RULING_LOOKUP_TIMEOUT_SECONDS,
            check=False,
            env={**os.environ, **ALL_STORED_HISTORY_GIT_SETTINGS},
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if completed.returncode != 0:
        return False
    return all(
        _is_reference_of(each_reference, branch) for each_reference in completed.stdout.split()
    )


def _is_reference_of(reference: str, branch: str) -> bool:
    if reference == LOCAL_BRANCH_REFERENCE_TEMPLATE.format(branch=branch):
        return True
    remote_and_branch = reference.removeprefix(REMOTE_TRACKING_REFERENCE_PREFIX)
    return remote_and_branch != reference and remote_and_branch.partition("/")[2] == branch


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
            f"an {OPEN_TARGET_WORD} pass cannot take --filed: one review pass comes before the "
            "open, so fix its findings in new commits and open the pull request. Findings are "
            f"filed only after {FULL_REVIEW_PASS_COUNT} full passes with fixes on the pull request"
        )
    if not OPEN_RECEIPT_HEAD_PATTERN.fullmatch(parsed.head):
        parser.error(f"an {OPEN_TARGET_WORD} pass needs the full 40 character commit")
    all_rulings = _checked_open_rulings(parser, parsed)
    try:
        receipt_written = record_open_review(parsed.slug, parsed.head, parsed.findings, all_rulings)
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
    if not (read_receipt(receipt_written) or {}).get(RECEIPT_BRANCH_KEY):
        stdout.write(
            f"REVIEWED {parsed.slug} {OPEN_TARGET_WORD} {parsed.head} {parsed.findings} findings, "
            f"recorded with no branch, so the pass counts only at {parsed.head} itself and fix "
            "commits on top of it get no credit yet. This folder has no checkout branch whose own "
            f"work {parsed.head} is: it is another folder, a detached HEAD, or another local or "
            f"remote branch also holds {parsed.head}. Run this command again from the checkout "
            "of the branch you will open, with that branch checked out. When another branch, "
            f"such as a backup copy, holds {parsed.head}, delete that copy first; when it is the "
            "branch this one stacks on, the pass covers that branch, so review this branch's own "
            "commits\n"
        )
        return 1
    stdout.write(
        f"REVIEWED {parsed.slug} {OPEN_TARGET_WORD} {parsed.head} {parsed.findings} findings "
        f"(fix them in new commits on top of {parsed.head}, then open the pull request; "
        "the fix commits need no second pass)\n"
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
    if issue_match is None:
        return False
    served_issue = _github_answer(
        FILED_ISSUE_API_PATH_TEMPLATE.format(owner=owner, repo=repo, number=issue_match["number"])
    )
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
    pass_number = _next_pass_number(
        parsed.slug, parsed.number, parsed.head, should_read_github=bool(parsed.filed.strip())
    )
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
