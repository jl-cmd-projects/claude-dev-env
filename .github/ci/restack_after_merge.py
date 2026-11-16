"""Restack the open pull requests stacked on a pull request that just merged.

::

    before:  main -- L1(squashed as M)      L1 -- L2 -- L3   (L2 base L1, L3 base L2)
    after:   main -- M -- L2' -- L3'        (L2' base main, L3' base L2)

Main merges by squash, so the levels above a merged level still carry its
original commits. This script replays only each level's own commits onto the
new base and force-pushes with a lease on the head it fetched. A level that
conflicts, whose push is refused, or that carries none of the stack's commits
gets the `status: needs-rebase` label and one comment with the commands to
restack it by hand. The levels above it stay as they are. A level whose head
is the default branch, or a branch whose protection or rulesets guard its
history, is never rewritten.
"""

import argparse
import shlex
import sys
from collections import deque
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

_repo_root_path = str(Path(__file__).resolve().parents[2])
if _repo_root_path not in sys.path:
    sys.path.insert(0, _repo_root_path)

from restack_after_merge_model import (
    MergedPullRequest,
    OpenPullRequest,
    RestackedLevel,
    RestackOutcome,
    RestackTarget,
    parse_open_pull_request,
)
from restack_after_merge_transport import (
    RestackRunFatal,
    carries_stack_commit,
    fetch_stack_refs,
    find_merge_base,
    flag_for_manual_restack,
    is_ancestor,
    list_open_pull_request_nodes,
    may_rewrite_branch,
    push_with_lease,
    rebase_onto,
    resolve_remote_branch,
    set_pull_request_base,
    shares_commit_missing_from_base,
)

from config.restack_after_merge_constants import (
    DEFAULT_REMOTE_NAME,
    FORCE_WITH_LEASE_FLAG_TEMPLATE,
    MANUAL_RESTACK_COMMENT_TEMPLATE,
    NEEDS_REBASE_LABEL,
    REASON_NOT_STACKED,
    REASON_PUSH_REJECTED,
    REASON_REBASE_CONFLICT,
    REMOTE_BRANCH_TEMPLATE,
    RESTACK_COMMENT_MARKER_TEMPLATE,
)


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
    return shares_commit_missing_from_base(
        remote_name, open_pull_request.head_ref, merged_pull_request.head_sha, merged_pull_request.base_ref
    )


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
        Every value pasted into a shell command is quoted, since git allows `$(...)`
        in a branch name.
    """
    fork_sha = find_merge_base(seen_sha, target.upstream_sha) or target.upstream_sha
    head_ref = target.pull_request.head_ref
    all_shell_arguments_by_placeholder = {
        "onto_branch": target.onto_branch,
        "remote": remote_name,
        "head_ref": head_ref,
        "remote_head_ref": REMOTE_BRANCH_TEMPLATE % (remote_name, head_ref),
        "remote_onto_branch": REMOTE_BRANCH_TEMPLATE % (remote_name, target.onto_branch),
        "lease_flag": FORCE_WITH_LEASE_FLAG_TEMPLATE % (head_ref, seen_sha),
        "fork_sha": fork_sha,
        "seen_sha": seen_sha,
        "child_number": str(target.pull_request.number),
        "label": NEEDS_REBASE_LABEL,
    }
    return MANUAL_RESTACK_COMMENT_TEMPLATE % {
        "marker": RESTACK_COMMENT_MARKER_TEMPLATE % merged_pull_request.number,
        "merged_number": merged_pull_request.number,
        "reason": reason,
        **{
            each_placeholder: shlex.quote(each_argument)
            for each_placeholder, each_argument in all_shell_arguments_by_placeholder.items()
        },
    }


def _rewrite_level(
    target: RestackTarget, repository: str, remote_name: str, seen_sha: str
) -> RestackedLevel:
    if not carries_stack_commit(seen_sha, target.upstream_sha, target.onto_sha):
        return RestackedLevel(RestackOutcome.NOT_STACKED, seen_sha, None)
    restacked_sha = rebase_onto(target.onto_sha, target.upstream_sha, seen_sha)
    if restacked_sha is None:
        return RestackedLevel(RestackOutcome.REBASE_CONFLICT, seen_sha, None)
    if target.pull_request.base_ref != target.onto_branch:
        set_pull_request_base(repository, target.pull_request.number, target.onto_branch)
    if push_with_lease(remote_name, target.pull_request.head_ref, seen_sha, restacked_sha):
        return RestackedLevel(RestackOutcome.RESTACKED, seen_sha, restacked_sha)
    return RestackedLevel(RestackOutcome.PUSH_REJECTED, seen_sha, None)


def _restack_one_level(
    target: RestackTarget, repository: str, merged_pull_request: MergedPullRequest, remote_name: str, default_branch: str
) -> RestackedLevel:
    head_ref = target.pull_request.head_ref
    if head_ref == default_branch:
        return RestackedLevel(RestackOutcome.DEFAULT_BRANCH_REFUSED, None, None)
    seen_sha = resolve_remote_branch(remote_name, head_ref)
    if seen_sha is None:
        return RestackedLevel(RestackOutcome.BRANCH_MISSING, None, None)
    if is_ancestor(target.settled_sha, seen_sha):
        return RestackedLevel(RestackOutcome.ALREADY_RESTACKED, seen_sha, seen_sha)
    if not may_rewrite_branch(repository, head_ref):
        return RestackedLevel(RestackOutcome.PROTECTED_BRANCH_REFUSED, seen_sha, None)
    restacked_level = _rewrite_level(target, repository, remote_name, seen_sha)
    failure_reason = {
        RestackOutcome.NOT_STACKED: REASON_NOT_STACKED,
        RestackOutcome.REBASE_CONFLICT: REASON_REBASE_CONFLICT,
        RestackOutcome.PUSH_REJECTED: REASON_PUSH_REJECTED,
    }.get(restacked_level.outcome)
    if failure_reason is not None:
        comment_body = build_manual_restack_comment(
            target, merged_pull_request, seen_sha, failure_reason, remote_name
        )
        flag_for_manual_restack(repository, target.pull_request.number, comment_body)
    return restacked_level


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
    default_branch: str,
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
        default_branch: The repository's default branch, which is never rewritten.
        report_stream: Where one line per visited level is written.

    Returns:
        Each visited pull request number with its outcome, in the order visited.

    Raises:
        RestackRunFatal: When the fetch, the open pull request listing, or a gh edit fails.
    """
    base_head_sha = fetch_stack_refs(
        remote_name, merged_pull_request.number, merged_pull_request.head_sha, merged_pull_request.base_ref
    )
    all_open_pull_requests = [
        parse_open_pull_request(each_node) for each_node in list_open_pull_request_nodes(repository)
    ]
    pending_targets = deque(
        _direct_child_targets(all_open_pull_requests, merged_pull_request, remote_name, base_head_sha)
    )
    all_outcomes: list[tuple[int, RestackOutcome]] = []
    while pending_targets:
        target = pending_targets.popleft()
        restacked_level = _restack_one_level(target, repository, merged_pull_request, remote_name, default_branch)
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
    argument_parser.add_argument("--default-branch", required=True, help="the repository default branch")
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
        restack_after_merge(
            parsed_arguments.repo,
            merged_pull_request,
            parsed_arguments.remote,
            parsed_arguments.default_branch,
        )
    except RestackRunFatal as run_fatal:
        error_stream.write(f"::error::{run_fatal}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
