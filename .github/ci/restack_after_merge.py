"""Restack the open pull requests stacked on a pull request that just merged.

::

    before:  main -- L1(squashed as M)      L1 -- L2 -- L3   (L2 base L1, L3 base L2)
    after:   main -- M -- L2' -- L3'        (L2' base main, L3' base L2)

Main merges by squash, so the levels above a merged level still carry its
original commits. This script replays only each level's own commits onto the
new base and force-pushes with a lease on the head it fetched. A level that
conflicts, whose push is refused, or that carries none of the stack's commits
gets a comment with the commands to restack it by hand, then the
`status: needs-rebase` label, and the levels above it stay as they are. A
refused push puts back the base the run set, unless something changed it
since. A level found already restacked, before or after its refused push, gets
its base and label settled and its levels above followed. The default branch,
and a branch whose protection or rulesets guard its history, is never
rewritten. A git or gh step that fails for one level leaves that level as it
is, and the run goes on with the others and exits nonzero at the end.
"""

import argparse
import shlex
import sys
from collections import deque
from collections.abc import Sequence
from dataclasses import replace
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
    fetch_remote_branch,
    fetch_stack_refs,
    find_merge_base,
    flag_for_manual_restack,
    is_ancestor,
    list_open_pull_request_nodes,
    may_rewrite_branch,
    push_with_lease,
    read_pull_request_base,
    rebase_onto,
    remove_needs_rebase_label,
    resolve_remote_branch,
    set_pull_request_base,
    shares_commit_missing_from_base,
)

from config.restack_after_merge_constants import (
    DEFAULT_REMOTE_NAME,
    FORCE_WITH_LEASE_ON_TRACKING_REF_TEMPLATE,
    MANUAL_RESTACK_COMMENT_TEMPLATE,
    NEEDS_REBASE_LABEL,
    REASON_NOT_STACKED,
    REASON_PUSH_REJECTED,
    REASON_REBASE_CONFLICT,
    REMOTE_BRANCH_TEMPLATE,
    RESTACK_COMMENT_MARKER_TEMPLATE,
    STEP_FAILURES_SEPARATOR,
)


def is_direct_child(
    open_pull_request: OpenPullRequest, merged_pull_request: MergedPullRequest, remote_name: str,
    default_branch: str, base_head_sha: str,
) -> bool:
    """Say whether an open pull request sat directly on the merged one.

    ::

        child:  base is the merged head branch
        child:  base is the default branch, and was the merged head branch before
                (GitHub retargets on branch delete)
        child:  base is the merged pull request's base, and the pull request shares a
                commit with the merged head that this base does not have
        not:    a pull request from a fork
        not:    a pull request moved from the merged head branch to another branch

    Args:
        open_pull_request: The candidate.
        merged_pull_request: The pull request that merged.
        remote_name: The git remote holding the branches.
        default_branch: The repository's default branch.
        base_head_sha: The head of the merged pull request's base, as the run fetched it.

    Returns:
        True for a direct child.
    """
    if open_pull_request.is_cross_repository:
        return False
    if open_pull_request.base_ref == merged_pull_request.head_ref:
        return True
    was_retargeted_on_delete = (
        open_pull_request.base_ref == default_branch
        and open_pull_request.previous_base_ref == merged_pull_request.head_ref
    )
    if was_retargeted_on_delete:
        return True
    if open_pull_request.base_ref != merged_pull_request.base_ref:
        return False
    return shares_commit_missing_from_base(
        remote_name, open_pull_request.head_ref, merged_pull_request.head_sha, base_head_sha
    )


def build_manual_restack_comment(
    target: RestackTarget, merged_pull_request: MergedPullRequest, seen_sha: str, reason: str,
    remote_name: str, repository: str,
) -> str:
    """Write the comment that tells an agent how to restack one level by hand.

    Args:
        target: The level that could not be restacked.
        merged_pull_request: The pull request whose merge started the run.
        seen_sha: The level's head when the run fetched it.
        reason: Why the automatic restack stopped.
        remote_name: The git remote holding the branches.
        repository: The owner/name of the repository, for the base retarget command.

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
        "lease_flag": FORCE_WITH_LEASE_ON_TRACKING_REF_TEMPLATE % head_ref,
        "fork_sha": fork_sha,
        "seen_sha": seen_sha,
        "child_number": str(target.pull_request.number),
        "label": NEEDS_REBASE_LABEL,
        "repository": repository,
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


def _retarget_base(target: RestackTarget, repository: str) -> bool:
    if target.pull_request.base_ref == target.onto_branch:
        return False
    set_pull_request_base(repository, target.pull_request.number, target.onto_branch)
    return True


def _rewrite_level(
    target: RestackTarget, repository: str, remote_name: str, seen_sha: str
) -> RestackedLevel:
    pull_request = target.pull_request
    head_ref = pull_request.head_ref
    if is_ancestor(target.settled_sha, seen_sha):
        _retarget_base(target, repository)
        return RestackedLevel(RestackOutcome.ALREADY_RESTACKED, seen_sha, seen_sha)
    if not may_rewrite_branch(repository, head_ref):
        return RestackedLevel(RestackOutcome.PROTECTED_BRANCH_REFUSED, seen_sha, None)
    if not carries_stack_commit(seen_sha, target.upstream_sha, target.onto_sha):
        return RestackedLevel(RestackOutcome.NOT_STACKED, seen_sha, None)
    restacked_sha = rebase_onto(target.onto_sha, target.upstream_sha, seen_sha)
    if restacked_sha is None:
        return RestackedLevel(RestackOutcome.REBASE_CONFLICT, seen_sha, None)
    has_retargeted = _retarget_base(target, repository)
    if push_with_lease(remote_name, head_ref, seen_sha, restacked_sha):
        return RestackedLevel(RestackOutcome.RESTACKED, seen_sha, restacked_sha)
    refetched_sha = fetch_remote_branch(remote_name, head_ref)
    if refetched_sha is not None and is_ancestor(target.settled_sha, refetched_sha):
        return RestackedLevel(RestackOutcome.ALREADY_RESTACKED, refetched_sha, refetched_sha)
    if has_retargeted and read_pull_request_base(repository, pull_request.number) == target.onto_branch:
        set_pull_request_base(repository, pull_request.number, pull_request.base_ref)
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
    try:
        restacked_level = _rewrite_level(target, repository, remote_name, seen_sha)
    except RestackRunFatal as level_fatal:
        return RestackedLevel(RestackOutcome.STEP_FAILED, seen_sha, None, str(level_fatal))
    try:
        _label_level(target, repository, merged_pull_request, remote_name, restacked_level, seen_sha)
    except RestackRunFatal as level_fatal:
        return replace(restacked_level, step_failure=str(level_fatal))
    return restacked_level


def _label_level(
    target: RestackTarget, repository: str, merged_pull_request: MergedPullRequest, remote_name: str,
    restacked_level: RestackedLevel, seen_sha: str,
) -> None:
    pull_request = target.pull_request
    if restacked_level.is_settled:
        if NEEDS_REBASE_LABEL in pull_request.all_label_names:
            remove_needs_rebase_label(repository, pull_request.number)
        return
    failure_reason = {
        RestackOutcome.NOT_STACKED: REASON_NOT_STACKED,
        RestackOutcome.REBASE_CONFLICT: REASON_REBASE_CONFLICT,
        RestackOutcome.PUSH_REJECTED: REASON_PUSH_REJECTED,
    }.get(restacked_level.outcome)
    if failure_reason is not None:
        comment_body = build_manual_restack_comment(
            target, merged_pull_request, seen_sha, failure_reason, remote_name, repository
        )
        flag_for_manual_restack(repository, pull_request.number, comment_body)


def _direct_child_targets(
    all_open_pull_requests: list[OpenPullRequest], merged_pull_request: MergedPullRequest, remote_name: str,
    default_branch: str, base_head_sha: str,
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
        if is_direct_child(each_pull_request, merged_pull_request, remote_name, default_branch, base_head_sha)
    ]


def _targets_stacked_on(
    all_open_pull_requests: list[OpenPullRequest], parent_target: RestackTarget, parent_level: RestackedLevel
) -> list[RestackTarget]:
    if not parent_level.is_settled or parent_level.seen_sha is None or parent_level.restacked_sha is None:
        return []
    parent_branch = parent_target.pull_request.head_ref
    is_moved_by_this_run = parent_level.outcome is RestackOutcome.RESTACKED
    return [
        RestackTarget(
            pull_request=each_pull_request,
            onto_branch=parent_branch,
            onto_sha=parent_level.restacked_sha,
            upstream_sha=parent_level.seen_sha if is_moved_by_this_run else parent_target.upstream_sha,
            settled_sha=parent_level.restacked_sha,
        )
        for each_pull_request in all_open_pull_requests
        if each_pull_request.base_ref == parent_branch and not each_pull_request.is_cross_repository
    ]


def restack_after_merge(
    repository: str, merged_pull_request: MergedPullRequest, remote_name: str, default_branch: str,
    report_stream: TextIO = sys.stdout,
) -> list[tuple[int, RestackOutcome]]:
    """Restack every open level stacked on the merged pull request, parents before children.

    ::

        direct child:  replay <merged head>..<child>  onto <merged base>
        level above a restacked level P:
                       replay <P head before>..<level> onto <P head after>
        level above an already restacked level P:
                       replay <P upstream>..<level> onto <P head>, which drops
                       P's old commits as empty

    A level that failed is not followed further, and each branch is visited once.

    Args:
        repository: The owner/name of the repository.
        merged_pull_request: The pull request that merged.
        remote_name: The git remote holding the branches.
        default_branch: The repository's default branch, which is never rewritten.
        report_stream: Where one line per visited level is written.

    Returns:
        Each visited pull request number with its outcome, in the order visited.

    Raises:
        RestackRunFatal: When the fetch or the open pull request listing fails, or,
            after every level ran, when a git or gh step failed for any level.
    """
    base_head_sha = fetch_stack_refs(
        remote_name, merged_pull_request.number, merged_pull_request.head_sha, merged_pull_request.base_ref
    )
    all_open_pull_requests = [parse_open_pull_request(each) for each in list_open_pull_request_nodes(repository)]
    pending_targets = deque(
        _direct_child_targets(all_open_pull_requests, merged_pull_request, remote_name, default_branch, base_head_sha)
    )
    all_visited_levels: list[tuple[RestackTarget, RestackedLevel]] = []
    all_visited_head_refs: set[str] = set()
    while pending_targets:
        target = pending_targets.popleft()
        if target.pull_request.head_ref in all_visited_head_refs:
            continue
        all_visited_head_refs.add(target.pull_request.head_ref)
        restacked_level = _restack_one_level(target, repository, merged_pull_request, remote_name, default_branch)
        all_visited_levels.append((target, restacked_level))
        _write_level_report(report_stream, target, restacked_level)
        pending_targets.extend(_targets_stacked_on(all_open_pull_requests, target, restacked_level))
    _raise_on_step_failures(all_visited_levels)
    return [(each_target.pull_request.number, each_level.outcome) for each_target, each_level in all_visited_levels]


def _write_level_report(report_stream: TextIO, target: RestackTarget, restacked_level: RestackedLevel) -> None:
    report_stream.write(
        f"#{target.pull_request.number} {target.pull_request.head_ref}: "
        f"{restacked_level.outcome.value} {restacked_level.seen_sha} -> {restacked_level.restacked_sha}\n"
    )


def _raise_on_step_failures(all_visited_levels: list[tuple[RestackTarget, RestackedLevel]]) -> None:
    all_step_failures = [
        f"#{each_target.pull_request.number}: {each_level.step_failure}"
        for each_target, each_level in all_visited_levels
        if each_level.step_failure is not None
    ]
    if all_step_failures:
        raise RestackRunFatal(STEP_FAILURES_SEPARATOR.join(all_step_failures))


def parse_command_line_arguments(all_argv: Sequence[str]) -> argparse.Namespace:
    """Parse the restack flags, which carry the merged pull request from the event payload.

    Args:
        all_argv: The argument vector, excluding the program name.

    Returns:
        The parsed namespace.
    """
    argument_parser = argparse.ArgumentParser(description="Restack each stack level above a merged pull request.")
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
        flag:  a fetch or listing every level needs fails -> 1
        flag:  a git or gh step fails for one level, after the others ran -> 1

    Args:
        all_argv: The argument vector, excluding the program name.
        error_stream: Where the error for a failed run is written.

    Returns:
        0 when the run finished, 1 when a step every level depends on failed or a
        step failed for one level.
    """
    parsed_arguments = parse_command_line_arguments(all_argv)
    merged_pull_request = MergedPullRequest(
        number=parsed_arguments.merged_pr, head_ref=parsed_arguments.merged_head_ref,
        head_sha=parsed_arguments.merged_head_sha, merge_commit_sha=parsed_arguments.merge_commit_sha,
        base_ref=parsed_arguments.base_ref,
    )
    try:
        restack_after_merge(
            parsed_arguments.repo, merged_pull_request, parsed_arguments.remote, parsed_arguments.default_branch
        )
    except RestackRunFatal as run_fatal:
        error_stream.write(f"::error::{run_fatal}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
