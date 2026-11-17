"""Git and gh calls for `restack_after_merge.py`.

::

    git:  fetch, ancestry, merge base, stack-commit check, rebase, push with lease
    gh:   list open pull requests, read branch protection and rules, set a
          base, add or remove a label, comment once

Every subprocess the restack makes lives here, so the stack logic in
`restack_after_merge.py` reads as decisions only.
"""

import json
import shlex
import subprocess
import sys
import urllib.parse
from collections.abc import Sequence
from pathlib import Path

_repo_root_path = str(Path(__file__).resolve().parents[2])
if _repo_root_path not in sys.path:
    sys.path.insert(0, _repo_root_path)

from config.restack_after_merge_constants import (
    ALL_BRANCHES_FETCH_REFSPEC_TEMPLATE,
    ALL_HEAD_COMMIT_ARGUMENTS,
    ALL_HISTORY_GUARDING_RULE_TYPES,
    ALL_REBASE_ABORT_ARGUMENTS,
    BRANCH_ENDPOINT_TEMPLATE,
    BRANCH_PROTECTED_JQ_FILTER,
    BRANCH_RULES_ENDPOINT_TEMPLATE,
    COMMENT_BODIES_JQ_FILTER,
    FORCE_WITH_LEASE_FLAG_TEMPLATE,
    ISSUE_COMMENTS_ENDPOINT_TEMPLATE,
    MERGED_HEAD_FETCH_REFSPEC_TEMPLATE,
    NEEDS_REBASE_LABEL,
    OPEN_PULL_REQUESTS_QUERY,
    PUSH_TO_BRANCH_REFSPEC_TEMPLATE,
    REMOTE_TRACKING_REF_TEMPLATE,
    RULE_TYPES_JQ_FILTER,
)


class RestackRunFatal(Exception):
    """A git or gh step that every stack level depends on failed."""


def run_command(all_arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run one command without raising on a nonzero exit.

    Args:
        all_arguments: The program and its arguments.

    Returns:
        The finished process, with its stdout and stderr as text.
    """
    return subprocess.run(list(all_arguments), capture_output=True, text=True, check=False)


def run_required_command(all_arguments: Sequence[str]) -> str:
    """Run one command that every stack level depends on.

    Args:
        all_arguments: The program and its arguments.

    Returns:
        The command's stdout, stripped.

    Raises:
        RestackRunFatal: When the command exits nonzero.
    """
    completed_process = run_command(all_arguments)
    if completed_process.returncode != 0:
        raise RestackRunFatal(
            f"{shlex.join(all_arguments)} failed: {completed_process.stderr.strip()}"
        )
    return completed_process.stdout.strip()


def list_open_pull_request_nodes(repository: str) -> list[dict]:
    """Read every page of the open pull requests GraphQL listing.

    Args:
        repository: The owner/name of the repository.

    Returns:
        Every pull request node, across all pages.
    """
    owner, name = repository.split("/", 1)
    all_nodes: list[dict] = []
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
        open_pull_requests_payload = json.loads(run_required_command(all_query_arguments))
        pull_requests_page = open_pull_requests_payload["data"]["repository"]["pullRequests"]
        all_nodes += pull_requests_page["nodes"]
        if not pull_requests_page["pageInfo"]["hasNextPage"]:
            return all_nodes
        page_cursor = pull_requests_page["pageInfo"]["endCursor"]


def is_ancestor(ancestor_sha: str, descendant_sha: str) -> bool:
    """Say whether one commit is reachable from another.

    Args:
        ancestor_sha: The commit that may be in the history.
        descendant_sha: The commit whose history is searched.

    Returns:
        True when ancestor_sha is reachable from descendant_sha.
    """
    is_ancestor_arguments = ["git", "merge-base", "--is-ancestor", ancestor_sha, descendant_sha]
    return run_command(is_ancestor_arguments).returncode == 0


def find_merge_base(first_sha: str, second_sha: str) -> str | None:
    """Find the best common ancestor of two commits.

    Args:
        first_sha: One commit.
        second_sha: The other commit.

    Returns:
        The common ancestor, or None when the two share no history.
    """
    completed_process = run_command(["git", "merge-base", first_sha, second_sha])
    return completed_process.stdout.strip() if completed_process.returncode == 0 else None


def resolve_remote_branch(remote_name: str, branch_name: str) -> str | None:
    """Read the fetched head of a remote branch.

    Args:
        remote_name: The git remote holding the branch.
        branch_name: The branch name.

    Returns:
        The head commit, or None when the remote has no such branch.
    """
    tracking_ref = REMOTE_TRACKING_REF_TEMPLATE % (remote_name, branch_name)
    completed_process = run_command(["git", "rev-parse", "--verify", "--quiet", tracking_ref])
    return completed_process.stdout.strip() if completed_process.returncode == 0 else None


def shares_commit_missing_from_base(
    remote_name: str, branch_name: str, merged_head_sha: str, base_head_sha: str
) -> bool:
    """Say whether a branch shares a commit with the merged head that the base branch lacks.

    Args:
        remote_name: The git remote holding the branches.
        branch_name: The candidate branch.
        merged_head_sha: The head of the pull request that merged.
        base_head_sha: The head of the branch it merged into, as the run fetched it.

    Returns:
        True when the fork point of the branch and the merged head is not on the base.
    """
    branch_head_sha = resolve_remote_branch(remote_name, branch_name)
    if branch_head_sha is None:
        return False
    fork_sha = find_merge_base(branch_head_sha, merged_head_sha)
    return fork_sha is not None and not is_ancestor(fork_sha, base_head_sha)


def fetch_stack_refs(remote_name: str, merged_number: int, merged_head_sha: str, base_ref: str) -> str:
    """Fetch every branch and the merged pull request's head.

    Args:
        remote_name: The git remote holding the branches.
        merged_number: The merged pull request's number.
        merged_head_sha: The merged pull request's head commit.
        base_ref: The branch it merged into.

    Returns:
        The head of base_ref after the fetch.

    Raises:
        RestackRunFatal: When the fetch fails, the merged head is missing, or the base is gone.
    """
    run_required_command(
        [
            "git", "fetch", "--no-tags", remote_name,
            ALL_BRANCHES_FETCH_REFSPEC_TEMPLATE % remote_name,
            MERGED_HEAD_FETCH_REFSPEC_TEMPLATE % merged_number,
        ]
    )
    run_required_command(["git", "cat-file", "-e", f"{merged_head_sha}^{{commit}}"])
    base_head_sha = resolve_remote_branch(remote_name, base_ref)
    if base_head_sha is None:
        raise RestackRunFatal(f"{remote_name} has no branch {base_ref}")
    return base_head_sha


def carries_stack_commit(seen_sha: str, upstream_sha: str, onto_sha: str) -> bool:
    """Say whether a branch holds a stack commit, by hash or by identical patch.

    ::

        stack commits:  onto_sha..upstream_sha, merges left out as `git cherry` does
        carries:        one of them is in seen_sha, or has a twin patch there
        not:            a branch that shares only the default branch's history
        none to find:   the merged level is already on the new base, as after a
                        merge commit, so the branch counts as stacked

    An amended parent still counts, because its old commit's patch matches.

    Args:
        seen_sha: The branch head to check.
        upstream_sha: The stack head the branch was built on.
        onto_sha: The new base, whose history is not a stack commit.

    Returns:
        True when at least one stack commit is in the branch.
    """
    all_stack_commits = run_required_command(
        ["git", "rev-list", "--no-merges", f"{onto_sha}..{upstream_sha}"]
    ).split()
    if not all_stack_commits:
        return True
    all_cherry_lines = run_required_command(["git", "cherry", seen_sha, upstream_sha, onto_sha]).splitlines()
    unmatched_count = sum(each_line.startswith("+") for each_line in all_cherry_lines)
    return len(all_stack_commits) > unmatched_count


def rebase_onto(onto_sha: str, upstream_sha: str, seen_sha: str) -> str | None:
    """Replay upstream_sha..seen_sha onto onto_sha, aborting on a conflict.

    Args:
        onto_sha: The new base.
        upstream_sha: Commits reachable from it are not replayed.
        seen_sha: The branch head to replay.

    Returns:
        The new head, or None when the rebase hit a conflict.
    """
    rebase_arguments = ["git", "rebase", "--onto", onto_sha, upstream_sha, seen_sha]
    if run_command(rebase_arguments).returncode != 0:
        run_command(ALL_REBASE_ABORT_ARGUMENTS)
        return None
    return run_required_command(ALL_HEAD_COMMIT_ARGUMENTS)


def push_with_lease(remote_name: str, head_ref: str, seen_sha: str, restacked_sha: str) -> bool:
    """Force-push a restacked head while the remote head is still the one fetched.

    Args:
        remote_name: The git remote holding the branch.
        head_ref: The branch to update.
        seen_sha: The head the run fetched, which the lease requires.
        restacked_sha: The new head.

    Returns:
        True when the push landed.
    """
    lease_flag = FORCE_WITH_LEASE_FLAG_TEMPLATE % (head_ref, seen_sha)
    push_refspec = PUSH_TO_BRANCH_REFSPEC_TEMPLATE % (restacked_sha, head_ref)
    return run_command(["git", "push", lease_flag, remote_name, push_refspec]).returncode == 0


def may_rewrite_branch(repository: str, branch_name: str) -> bool:
    """Say whether GitHub lets the restack rewrite a branch's history.

    ::

        refuse:  branch protection reports the branch protected
        refuse:  a ruleset applies non_fast_forward, update, or deletion to it
        refuse:  either read fails
        allow:   no protection, and only other rule types such as status checks

    Args:
        repository: The owner/name of the repository.
        branch_name: The branch the restack would force-push.

    Returns:
        True only when both reads succeed and neither guards the branch's history.
    """
    quoted_branch = urllib.parse.quote(branch_name, safe="/")
    protection_read = run_command(
        ["gh", "api", BRANCH_ENDPOINT_TEMPLATE % (repository, quoted_branch), "--jq", BRANCH_PROTECTED_JQ_FILTER]
    )
    if protection_read.returncode != 0 or protection_read.stdout.strip() != "false":
        return False
    rules_read = run_command(
        [
            "gh", "api", "--paginate",
            BRANCH_RULES_ENDPOINT_TEMPLATE % (repository, quoted_branch),
            "--jq", RULE_TYPES_JQ_FILTER,
        ]
    )
    all_rule_types = set(rules_read.stdout.split())
    return rules_read.returncode == 0 and not all_rule_types & ALL_HISTORY_GUARDING_RULE_TYPES


def set_pull_request_base(repository: str, pull_request_number: int, base_branch: str) -> None:
    """Point a pull request at a new base branch.

    Args:
        repository: The owner/name of the repository.
        pull_request_number: The pull request to edit.
        base_branch: Its new base.
    """
    run_required_command(
        ["gh", "pr", "edit", str(pull_request_number), "--repo", repository, "--base", base_branch]
    )


def remove_needs_rebase_label(repository: str, pull_request_number: int) -> None:
    """Take the needs-rebase label off a pull request the restack moved.

    Args:
        repository: The owner/name of the repository.
        pull_request_number: The pull request to edit.
    """
    run_required_command(
        [
            "gh", "pr", "edit", str(pull_request_number), "--repo", repository,
            "--remove-label", NEEDS_REBASE_LABEL,
        ]
    )


def flag_for_manual_restack(repository: str, pull_request_number: int, comment_body: str) -> None:
    """Add the needs-rebase label, and post the comment unless its marker line is already there.

    Args:
        repository: The owner/name of the repository.
        pull_request_number: The pull request to flag.
        comment_body: The comment, whose first line is its marker.
    """
    number_text = str(pull_request_number)
    run_required_command(
        ["gh", "pr", "edit", number_text, "--repo", repository, "--add-label", NEEDS_REBASE_LABEL]
    )
    comments_endpoint = ISSUE_COMMENTS_ENDPOINT_TEMPLATE % (repository, number_text)
    existing_comment_bodies = run_required_command(
        ["gh", "api", "--paginate", comments_endpoint, "--jq", COMMENT_BODIES_JQ_FILTER]
    )
    comment_marker = comment_body.splitlines()[0]
    if comment_marker in existing_comment_bodies:
        return
    run_required_command(
        ["gh", "pr", "comment", number_text, "--repo", repository, "--body", comment_body]
    )
