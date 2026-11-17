"""Constants for `.github/ci/restack_after_merge.py` and its transport module: the
GraphQL listing of open pull requests, the label and comment text left on a stack
level that could not be restacked, and the git refs the script fetches into."""

NEEDS_REBASE_LABEL: str = "status: needs-rebase"
RESTACK_COMMENT_MARKER_TEMPLATE: str = "<!-- restack-after-merge:%s -->"

DEFAULT_REMOTE_NAME: str = "origin"
REMOTE_TRACKING_REF_TEMPLATE: str = "refs/remotes/%s/%s"
ALL_BRANCHES_FETCH_REFSPEC_TEMPLATE: str = "+refs/heads/*:refs/remotes/%s/*"
MERGED_HEAD_FETCH_REFSPEC_TEMPLATE: str = "+refs/pull/%s/head:refs/restack/merged-head"

OPEN_PULL_REQUESTS_QUERY: str = (
    """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(states: OPEN, first: 100, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        headRefName
        baseRefName
        isCrossRepository
        labels(first: 100) { nodes { name } }
        timelineItems(itemTypes: [BASE_REF_CHANGED_EVENT, AUTOMATIC_BASE_CHANGE_SUCCEEDED_EVENT], last: 1) {
          nodes {
            __typename
            ... on BaseRefChangedEvent { previousRefName }
            ... on AutomaticBaseChangeSucceededEvent { oldBase }
          }
        }
      }
    }
  }
}
"""
)

MANUAL_RESTACK_COMMENT_TEMPLATE: str = """%(marker)s
Merging #%(merged_number)s left this pull request stacked on commits that are not on its new base any more, and the automatic restack stopped: %(reason)s.

Restack it by hand from a clone of this repository:

```bash
git fetch %(remote)s %(onto_branch)s %(head_ref)s
git switch -C %(head_ref)s %(remote_head_ref)s
git rebase --onto %(remote_onto_branch)s %(fork_sha)s
git push %(lease_flag)s %(remote)s %(head_ref)s
gh pr edit %(child_number)s --repo %(repository)s --base %(onto_branch)s
gh pr edit %(child_number)s --remove-label %(label)s
```

When the rebase stops on a change the merged pull request already landed, run `git rebase --skip`. When it stops on a commit of this pull request, fix the files, `git add` them, and run `git rebase --continue`. Then run the push, base, and label commands.

Pull requests stacked on this one were left as they are. Restack each onto the new head of this pull request's branch the same way, with the fork point `git merge-base <its branch> %(seen_sha)s`.
"""

REASON_REBASE_CONFLICT: str = "the rebase hit a conflict"
REASON_PUSH_REJECTED: str = (
    "the force push was refused. The cause may be a lease mismatch, because the branch moved after"
    " the run fetched it, a branch rule, or a change to a workflow file, which the app token cannot"
    " push without the workflows permission"
)
REASON_NOT_STACKED: str = "the branch carries none of the merged pull request's commits, so it may not be a stack level"
STEP_FAILURES_SEPARATOR: str = "; "

ISSUE_COMMENTS_ENDPOINT_TEMPLATE: str = "repos/%s/issues/%s/comments"
BRANCH_ENDPOINT_TEMPLATE: str = "repos/%s/branches/%s"
BRANCH_PROTECTED_JQ_FILTER: str = ".protected"
BRANCH_RULES_ENDPOINT_TEMPLATE: str = "repos/%s/rules/branches/%s"
RULE_TYPES_JQ_FILTER: str = ".[].type"
ALL_HISTORY_GUARDING_RULE_TYPES: frozenset[str] = frozenset({"non_fast_forward", "update", "deletion"})
FORCE_WITH_LEASE_FLAG_TEMPLATE: str = "--force-with-lease=%s:%s"
FORCE_WITH_LEASE_ON_TRACKING_REF_TEMPLATE: str = "--force-with-lease=%s"
REMOTE_BRANCH_TEMPLATE: str = "%s/%s"
PUSH_TO_BRANCH_REFSPEC_TEMPLATE: str = "%s:refs/heads/%s"
COMMENT_BODIES_JQ_FILTER: str = ".[].body"
ALL_REBASE_ABORT_ARGUMENTS: tuple[str, ...] = ("git", "rebase", "--abort")
ALL_HEAD_COMMIT_ARGUMENTS: tuple[str, ...] = ("git", "rev-parse", "HEAD")
ALL_UNMERGED_PATHS_ARGUMENTS: tuple[str, ...] = ("git", "diff", "--name-only", "--diff-filter=U")
PULL_REQUEST_BASE_JQ_FILTER: str = ".baseRefName"
BRANCH_FETCH_REFSPEC_TEMPLATE: str = "+refs/heads/%s:refs/remotes/%s/%s"
