"""Restack the open pull requests stacked on a pull request that just merged.

::

    before:  main -- L1(squashed as M)      L1 -- L2 -- L3   (L2 base L1, L3 base L2)
    after:   main -- M -- L2' -- L3'        (L2' base main, L3' base L2)

Main merges by squash, so the levels above a merged level still carry its
original commits. This script replays only each level's own commits onto the
new base and force-pushes with a lease on the head it fetched. A level that
conflicts, or whose push is refused, gets the `status: needs-rebase` label and
one comment with the commands to restack it by hand. The levels above it stay
as they are.
"""

import argparse
import json
import shlex
import subprocess
import sys
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TextIO

_repo_root_path = str(Path(__file__).resolve().parents[2])
if _repo_root_path not in sys.path:
    sys.path.insert(0, _repo_root_path)

from config.restack_after_merge_constants import (
    ALL_BRANCHES_FETCH_REFSPEC_TEMPLATE,
    ALL_HEAD_COMMIT_ARGUMENTS,
    ALL_REBASE_ABORT_ARGUMENTS,
    COMMENT_BODIES_JQ_FILTER,
    DEFAULT_REMOTE_NAME,
    FORCE_WITH_LEASE_FLAG_TEMPLATE,
    ISSUE_COMMENTS_ENDPOINT_TEMPLATE,
    MANUAL_RESTACK_COMMENT_TEMPLATE,
    MERGED_HEAD_FETCH_REFSPEC_TEMPLATE,
    NEEDS_REBASE_LABEL,
    OPEN_PULL_REQUESTS_QUERY,
    PUSH_TO_BRANCH_REFSPEC_TEMPLATE,
    REASON_PUSH_REJECTED,
    REASON_REBASE_CONFLICT,
    REMOTE_TRACKING_REF_TEMPLATE,
    RESTACK_COMMENT_MARKER_TEMPLATE,
)


@dataclass(frozen=True)
class MergedPullRequest:
    """The pull request whose merge starts the restack, as the event payload names it."""

    number: int
    head_ref: str
    head_sha: str
    merge_commit_sha: str
    base_ref: str


@dataclass(frozen=True)
class OpenPullRequest:
    """One open pull request, with the base it had before its most recent base change."""

    number: int
    head_ref: str
    base_ref: str
    previous_base_ref: str | None
    is_cross_repository: bool


@dataclass(frozen=True)
class RestackTarget:
    """One stack level to move.

    ::

        replay:   upstream_sha..<level head>   onto onto_sha
        settled:  the level head already contains settled_sha -> nothing to do

    Args:
        pull_request: The level to move.
        onto_branch: The branch the level ends up on, also its required base.
        onto_sha: The commit the level's own commits are replayed onto.
        upstream_sha: Commits reachable from it are not replayed.
        settled_sha: A level whose head contains this commit is already restacked.
    """

    pull_request: OpenPullRequest
    onto_branch: str
    onto_sha: str
    upstream_sha: str
    settled_sha: str


class RestackOutcome(Enum):
    """How one stack level ended."""

    RESTACKED = "restacked"
    ALREADY_RESTACKED = "already restacked"
    BRANCH_MISSING = "branch missing"
    REBASE_CONFLICT = "rebase conflict"
    PUSH_REJECTED = "push rejected"


@dataclass(frozen=True)
class RestackedLevel:
    """How one level ended, with its head before and after the run."""

    outcome: RestackOutcome
    seen_sha: str | None
    restacked_sha: str | None


class RestackRunFatal(Exception):
    """A git or gh step that every stack level depends on failed."""


def _run_command(all_arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(all_arguments), capture_output=True, text=True, check=False)


def _run_required_command(all_arguments: Sequence[str]) -> str:
    completed_process = _run_command(all_arguments)
    if completed_process.returncode != 0:
        raise RestackRunFatal(
            f"{shlex.join(all_arguments)} failed: {completed_process.stderr.strip()}"
        )
    return completed_process.stdout.strip()


def parse_open_pull_request(pull_request_node: dict) -> OpenPullRequest:
    """Turn one GraphQL pull request node into an OpenPullRequest.

    Args:
        pull_request_node: A node from the open pull requests query.

    Returns:
        The pull request, with previous_base_ref from its last base change event, or None.
    """
    previous_base_ref = None
    for each_event in pull_request_node["timelineItems"]["nodes"]:
        previous_base_ref = each_event.get("previousRefName") or each_event.get("oldBase")
    return OpenPullRequest(
        number=pull_request_node["number"],
        head_ref=pull_request_node["headRefName"],
        base_ref=pull_request_node["baseRefName"],
        previous_base_ref=previous_base_ref,
        is_cross_repository=pull_request_node["isCrossRepository"],
    )


def _list_open_pull_requests(repository: str) -> list[OpenPullRequest]:
    owner, name = repository.split("/", 1)
    all_open_pull_requests: list[OpenPullRequest] = []
    page_cursor: str | None = None
    while True:
        all_query_arguments = [
            "gh", "api", "graphql",
            "-f", f"query={OPEN_PULL_REQUESTS_QUERY}",
            "-f", f"owner={owner}",
            "-f", f"name={name}",
        ]
        if page_cursor:
            all_query_arguments += ["-f", f"cursor={page_cursor}"]
        open_pull_requests_payload = json.loads(_run_required_command(all_query_arguments))
        pull_requests_page = open_pull_requests_payload["data"]["repository"]["pullRequests"]
        all_open_pull_requests += [
            parse_open_pull_request(each_node) for each_node in pull_requests_page["nodes"]
        ]
        if not pull_requests_page["pageInfo"]["hasNextPage"]:
            return all_open_pull_requests
        page_cursor = pull_requests_page["pageInfo"]["endCursor"]


def _is_ancestor(ancestor_sha: str, descendant_sha: str) -> bool:
    is_ancestor_arguments = ["git", "merge-base", "--is-ancestor", ancestor_sha, descendant_sha]
    return _run_command(is_ancestor_arguments).returncode == 0


def _find_merge_base(first_sha: str, second_sha: str) -> str | None:
    completed_process = _run_command(["git", "merge-base", first_sha, second_sha])
    return completed_process.stdout.strip() if completed_process.returncode == 0 else None


def _resolve_remote_branch(remote_name: str, branch_name: str) -> str | None:
    tracking_ref = REMOTE_TRACKING_REF_TEMPLATE % (remote_name, branch_name)
    completed_process = _run_command(["git", "rev-parse", "--verify", "--quiet", tracking_ref])
    return completed_process.stdout.strip() if completed_process.returncode == 0 else None


def is_direct_child(
    open_pull_request: OpenPullRequest, merged_pull_request: MergedPullRequest, remote_name: str
) -> bool:
    """Say whether an open pull request sat directly on the merged one.

    ::

        child:  base is the merged head branch
        child:  base was moved off the merged head branch (GitHub retargets on branch delete)
        child:  base is the merged pull request's base, and the pull request shares a
                commit with the merged head that this base does not have
        not:    a pull request from a fork

    Args:
        open_pull_request: The candidate.
        merged_pull_request: The pull request that merged.
        remote_name: The git remote holding the branches.

    Returns:
        True for a direct child.
    """
    if open_pull_request.is_cross_repository:
        return False
    all_stacked_bases = (open_pull_request.base_ref, open_pull_request.previous_base_ref)
    if merged_pull_request.head_ref in all_stacked_bases:
        return True
    if open_pull_request.base_ref != merged_pull_request.base_ref:
        return False
    child_head_sha = _resolve_remote_branch(remote_name, open_pull_request.head_ref)
    base_head_sha = _resolve_remote_branch(remote_name, merged_pull_request.base_ref)
    if child_head_sha is None or base_head_sha is None:
        return False
    fork_sha = _find_merge_base(child_head_sha, merged_pull_request.head_sha)
    return fork_sha is not None and not _is_ancestor(fork_sha, base_head_sha)


def build_manual_restack_comment(
    target: RestackTarget,
    merged_pull_request: MergedPullRequest,
    seen_sha: str,
    reason: str,
    remote_name: str,
) -> str:
    """Write the comment that tells an agent how to restack one level by hand.

    Args:
        target: The level that could not be restacked.
        merged_pull_request: The pull request whose merge started the run.
        seen_sha: The level's head when the run fetched it.
        reason: Why the automatic restack stopped.
        remote_name: The git remote holding the branches.

    Returns:
        The comment body, opening with a marker unique to the merged pull request.
    """
    fork_sha = _find_merge_base(seen_sha, target.upstream_sha) or target.upstream_sha
    return MANUAL_RESTACK_COMMENT_TEMPLATE % {
        "marker": RESTACK_COMMENT_MARKER_TEMPLATE % merged_pull_request.number,
        "merged_number": merged_pull_request.number,
        "onto_branch": target.onto_branch,
        "reason": reason,
        "remote": remote_name,
        "head_ref": target.pull_request.head_ref,
        "fork_sha": fork_sha,
        "seen_sha": seen_sha,
        "child_number": target.pull_request.number,
        "label": NEEDS_REBASE_LABEL,
    }


def _flag_for_manual_restack(repository: str, target: RestackTarget, comment_body: str) -> None:
    pull_request_number = str(target.pull_request.number)
    _run_required_command(
        ["gh", "pr", "edit", pull_request_number, "--repo", repository, "--add-label", NEEDS_REBASE_LABEL]
    )
    comments_endpoint = ISSUE_COMMENTS_ENDPOINT_TEMPLATE % (repository, pull_request_number)
    existing_comment_bodies = _run_required_command(
        ["gh", "api", "--paginate", comments_endpoint, "--jq", COMMENT_BODIES_JQ_FILTER]
    )
    comment_marker = comment_body.splitlines()[0]
    if comment_marker in existing_comment_bodies:
        return
    _run_required_command(
        ["gh", "pr", "comment", pull_request_number, "--repo", repository, "--body", comment_body]
    )


def _rebase_level(target: RestackTarget, seen_sha: str) -> str | None:
    rebase_arguments = ["git", "rebase", "--onto", target.onto_sha, target.upstream_sha, seen_sha]
    if _run_command(rebase_arguments).returncode != 0:
        _run_command(ALL_REBASE_ABORT_ARGUMENTS)
        return None
    return _run_required_command(ALL_HEAD_COMMIT_ARGUMENTS)


def _push_with_lease(remote_name: str, head_ref: str, seen_sha: str, restacked_sha: str) -> bool:
    lease_flag = FORCE_WITH_LEASE_FLAG_TEMPLATE % (head_ref, seen_sha)
    push_refspec = PUSH_TO_BRANCH_REFSPEC_TEMPLATE % (restacked_sha, head_ref)
    return _run_command(["git", "push", lease_flag, remote_name, push_refspec]).returncode == 0


def _restack_one_level(
    target: RestackTarget, repository: str, merged_pull_request: MergedPullRequest, remote_name: str
) -> RestackedLevel:
    head_ref = target.pull_request.head_ref
    seen_sha = _resolve_remote_branch(remote_name, head_ref)
    if seen_sha is None:
        return RestackedLevel(RestackOutcome.BRANCH_MISSING, None, None)
    if _is_ancestor(target.settled_sha, seen_sha):
        return RestackedLevel(RestackOutcome.ALREADY_RESTACKED, seen_sha, seen_sha)
    restacked_sha = _rebase_level(target, seen_sha)
    if restacked_sha is None:
        failure = RestackedLevel(RestackOutcome.REBASE_CONFLICT, seen_sha, None)
        failure_reason = REASON_REBASE_CONFLICT
    else:
        if target.pull_request.base_ref != target.onto_branch:
            _run_required_command(
                ["gh", "pr", "edit", str(target.pull_request.number), "--repo", repository, "--base", target.onto_branch]
            )
        if _push_with_lease(remote_name, head_ref, seen_sha, restacked_sha):
            return RestackedLevel(RestackOutcome.RESTACKED, seen_sha, restacked_sha)
        failure = RestackedLevel(RestackOutcome.PUSH_REJECTED, seen_sha, None)
        failure_reason = REASON_PUSH_REJECTED
    comment_body = build_manual_restack_comment(
        target, merged_pull_request, seen_sha, failure_reason, remote_name
    )
    _flag_for_manual_restack(repository, target, comment_body)
    return failure


def _fetch_stack_refs(merged_pull_request: MergedPullRequest, remote_name: str) -> str:
    _run_required_command(
        [
            "git", "fetch", "--no-tags", remote_name,
            ALL_BRANCHES_FETCH_REFSPEC_TEMPLATE % remote_name,
            MERGED_HEAD_FETCH_REFSPEC_TEMPLATE % merged_pull_request.number,
        ]
    )
    _run_required_command(["git", "cat-file", "-e", f"{merged_pull_request.head_sha}^{{commit}}"])
    base_head_sha = _resolve_remote_branch(remote_name, merged_pull_request.base_ref)
    if base_head_sha is None:
        raise RestackRunFatal(f"{remote_name} has no branch {merged_pull_request.base_ref}")
    return base_head_sha


def _direct_child_targets(
    all_open_pull_requests: list[OpenPullRequest],
    merged_pull_request: MergedPullRequest,
    remote_name: str,
    base_head_sha: str,
) -> list[RestackTarget]:
    return [
        RestackTarget(
            pull_request=each_pull_request,
            onto_branch=merged_pull_request.base_ref,
            onto_sha=base_head_sha,
            upstream_sha=merged_pull_request.head_sha,
            settled_sha=merged_pull_request.merge_commit_sha,
        )
        for each_pull_request in all_open_pull_requests
        if is_direct_child(each_pull_request, merged_pull_request, remote_name)
    ]


def _targets_stacked_on(
    all_open_pull_requests: list[OpenPullRequest], parent_branch: str, parent_level: RestackedLevel
) -> list[RestackTarget]:
    if parent_level.outcome is not RestackOutcome.RESTACKED:
        return []
    if parent_level.seen_sha is None or parent_level.restacked_sha is None:
        return []
    return [
        RestackTarget(
            pull_request=each_pull_request,
            onto_branch=parent_branch,
            onto_sha=parent_level.restacked_sha,
            upstream_sha=parent_level.seen_sha,
            settled_sha=parent_level.restacked_sha,
        )
        for each_pull_request in all_open_pull_requests
        if each_pull_request.base_ref == parent_branch and not each_pull_request.is_cross_repository
    ]


def restack_after_merge(
    repository: str,
    merged_pull_request: MergedPullRequest,
    remote_name: str,
    report_stream: TextIO = sys.stdout,
) -> list[tuple[int, RestackOutcome]]:
    """Restack every open level stacked on the merged pull request, parents before children.

    ::

        direct child:  replay <merged head>..<child>  onto <merged base>
        level above a restacked level P:
                       replay <P head before>..<level> onto <P head after>

    A level that failed, or that was already restacked, is not followed further.

    Args:
        repository: The owner/name of the repository.
        merged_pull_request: The pull request that merged.
        remote_name: The git remote holding the branches.
        report_stream: Where one line per visited level is written.

    Returns:
        Each visited pull request number with its outcome, in the order visited.

    Raises:
        RestackRunFatal: When the fetch, the open pull request listing, or a gh edit fails.
    """
    base_head_sha = _fetch_stack_refs(merged_pull_request, remote_name)
    all_open_pull_requests = _list_open_pull_requests(repository)
    pending_targets = deque(
        _direct_child_targets(all_open_pull_requests, merged_pull_request, remote_name, base_head_sha)
    )
    all_outcomes: list[tuple[int, RestackOutcome]] = []
    while pending_targets:
        target = pending_targets.popleft()
        restacked_level = _restack_one_level(target, repository, merged_pull_request, remote_name)
        all_outcomes.append((target.pull_request.number, restacked_level.outcome))
        report_stream.write(
            f"#{target.pull_request.number} {target.pull_request.head_ref}: "
            f"{restacked_level.outcome.value} {restacked_level.seen_sha} -> {restacked_level.restacked_sha}\n"
        )
        pending_targets.extend(
            _targets_stacked_on(all_open_pull_requests, target.pull_request.head_ref, restacked_level)
        )
    return all_outcomes


def parse_command_line_arguments(all_argv: Sequence[str]) -> argparse.Namespace:
    """Parse the restack flags, which carry the merged pull request from the event payload.

    Args:
        all_argv: The argument vector, excluding the program name.

    Returns:
        The parsed namespace.
    """
    argument_parser = argparse.ArgumentParser(
        description="Restack open pull requests stacked on a merged pull request."
    )
    argument_parser.add_argument("--repo", required=True, help="owner/name of the repository")
    argument_parser.add_argument("--merged-pr", required=True, type=int, help="merged pull request number")
    argument_parser.add_argument("--merged-head-ref", required=True, help="merged head branch")
    argument_parser.add_argument("--merged-head-sha", required=True, help="merged head commit")
    argument_parser.add_argument("--merge-commit-sha", required=True, help="commit the merge made")
    argument_parser.add_argument("--base-ref", required=True, help="branch the pull request merged into")
    argument_parser.add_argument("--remote", default=DEFAULT_REMOTE_NAME, help="git remote")
    return argument_parser.parse_args(all_argv)


def main(all_argv: Sequence[str], error_stream: TextIO = sys.stderr) -> int:
    """Restack the stack above one merged pull request.

    ::

        ok:    every level restacked, already restacked, or flagged -> 0
        flag:  a fetch, listing, or gh step every level needs fails -> 1

    Args:
        all_argv: The argument vector, excluding the program name.
        error_stream: Where the error for a failed run is written.

    Returns:
        0 when the run finished, 1 when a step every level depends on failed.
    """
    parsed_arguments = parse_command_line_arguments(all_argv)
    merged_pull_request = MergedPullRequest(
        number=parsed_arguments.merged_pr,
        head_ref=parsed_arguments.merged_head_ref,
        head_sha=parsed_arguments.merged_head_sha,
        merge_commit_sha=parsed_arguments.merge_commit_sha,
        base_ref=parsed_arguments.base_ref,
    )
    try:
        restack_after_merge(parsed_arguments.repo, merged_pull_request, parsed_arguments.remote)
    except RestackRunFatal as run_fatal:
        error_stream.write(f"::error::{run_fatal}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
