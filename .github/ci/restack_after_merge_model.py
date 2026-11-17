"""The pull requests and stack levels `restack_after_merge.py` works on.

::

    MergedPullRequest   the merge that starts the run, from the event payload
    OpenPullRequest     one open pull request, parsed from the GraphQL listing
    RestackTarget       one level to move: replay upstream..head onto a new base
    RestackedLevel      how that level ended, with its head before and after
"""

from dataclasses import dataclass
from enum import Enum


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
    all_label_names: frozenset[str] = frozenset()


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
    DEFAULT_BRANCH_REFUSED = "default branch refused"
    PROTECTED_BRANCH_REFUSED = "protected branch refused"
    NOT_STACKED = "carries no stack commit"
    STEP_FAILED = "a git or gh step failed"


@dataclass(frozen=True)
class RestackedLevel:
    """How one level ended, with its head before and after the run.

    step_failure names a git or gh step that failed for this level alone. The run
    goes on with the other levels and exits nonzero at the end.
    """

    outcome: RestackOutcome
    seen_sha: str | None
    restacked_sha: str | None
    step_failure: str | None = None


def parse_open_pull_request(pull_request_node: dict) -> OpenPullRequest:
    """Turn one GraphQL pull request node into an OpenPullRequest.

    Args:
        pull_request_node: A node from the open pull requests query.

    Returns:
        The pull request, with previous_base_ref from its last base change event, or None,
        and the names of its labels.
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
        all_label_names=frozenset(
            each_label["name"] for each_label in pull_request_node["labels"]["nodes"]
        ),
    )
