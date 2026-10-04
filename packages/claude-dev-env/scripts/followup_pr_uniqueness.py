"""Fail a follow-up pull request when an earlier open one already names its parent.

Usage::

    python followup_pr_uniqueness.py OWNER/REPO NUMBER

Only pull requests opened at or after the rule start take part, so follow-up
groups opened before the rule existed stay green.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping, Sequence

from dev_env_scripts_constants.followup_pr_uniqueness_constants import (
    DUPLICATE_EXIT_CODE,
    DUPLICATE_FOLLOWUP_MESSAGE_TEMPLATE,
    ERROR_EXIT_CODE,
    FOLLOWUP_PARENT_PATTERN,
    OPEN_PULL_REQUESTS_ENDPOINT_TEMPLATE,
    PASS_EXIT_CODE,
    PASS_MESSAGE,
    RULE_START_TIMESTAMP,
)
from dev_env_scripts_constants.review_closure_constants import GET_METHOD, GITHUB_API_ROOT
from pr_verification.github_parsing import GitHubError
from review_closure_github import github_token, read_pull_request, request_json


def followup_parent_number(body: object) -> int | None:
    """Read the parent number a "Follow-up to #N" line names.

    Args:
        body: The pull request body, or any other value GitHub sent.

    Returns:
        The parent number, or None when the body names no parent.
    """
    if not isinstance(body, str):
        return None
    match = re.search(FOLLOWUP_PARENT_PATTERN, body, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _is_under_rule(all_pull_request_fields: Mapping[str, object]) -> bool:
    created_at = all_pull_request_fields.get("created_at")
    return isinstance(created_at, str) and created_at >= RULE_START_TIMESTAMP


def _earlier_followups(
    own_number: int, parent_number: int, all_open_pull_requests: Sequence[Mapping[str, object]]
) -> list[Mapping[str, object]]:
    return [
        each_open
        for each_open in all_open_pull_requests
        if isinstance(each_open.get("number"), int)
        and each_open["number"] < own_number
        and _is_under_rule(each_open)
        and followup_parent_number(each_open.get("body")) == parent_number
    ]


def duplicate_message(
    all_pull_request_fields: Mapping[str, object],
    all_open_pull_requests: Sequence[Mapping[str, object]],
) -> str | None:
    """Return the failure message when an earlier open follow-up names the same parent.

    Args:
        all_pull_request_fields: The pull request under test.
        all_open_pull_requests: The repository's open pull requests.

    Returns:
        The failure message, or None when this pull request may stay open.
    """
    parent_number = followup_parent_number(all_pull_request_fields.get("body"))
    own_number = all_pull_request_fields.get("number")
    if parent_number is None or not isinstance(own_number, int) or not _is_under_rule(all_pull_request_fields):
        return None
    all_earlier_followups = _earlier_followups(own_number, parent_number, all_open_pull_requests)
    if not all_earlier_followups:
        return None
    first_followup = min(all_earlier_followups, key=lambda entry: entry["number"])
    return DUPLICATE_FOLLOWUP_MESSAGE_TEMPLATE.format(
        open_number=first_followup["number"],
        parent_number=parent_number,
        open_url=first_followup.get("html_url"),
    )


def _open_pull_requests(slug: str, token: str) -> list[Mapping[str, object]]:
    document = request_json(
        GET_METHOD,
        OPEN_PULL_REQUESTS_ENDPOINT_TEMPLATE.format(api_root=GITHUB_API_ROOT, slug=slug),
        token,
        None,
    )
    if not isinstance(document, list):
        raise GitHubError(str(document))
    return [each_entry for each_entry in document if isinstance(each_entry, Mapping)]


def main(all_arguments: Sequence[str]) -> int:
    """Print the verdict for one pull request and return its exit code.

    Args:
        all_arguments: The command line, without the program name.

    Returns:
        Zero when no earlier follow-up names the parent, one on a duplicate,
        and two when GitHub could not be read.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    parser.add_argument("number", type=int)
    parsed = parser.parse_args(all_arguments)
    try:
        token = github_token()
        pull_request = read_pull_request(parsed.slug, parsed.number, token)
        message = duplicate_message(pull_request, _open_pull_requests(parsed.slug, token))
    except GitHubError as failure:
        print(failure, file=sys.stderr)
        return ERROR_EXIT_CODE
    print(message or PASS_MESSAGE)
    return PASS_EXIT_CODE if message is None else DUPLICATE_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
