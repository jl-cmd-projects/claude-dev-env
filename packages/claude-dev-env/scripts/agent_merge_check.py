#!/usr/bin/env python3
"""Report whether the agent driving a pull request may merge it now.

An agent that drives a pull request in this repository merges it once the
repository's own gate passes and no review thread is open. This command reads
that state from GitHub and prints one verdict line, so the decision rests on
the pull request's live state rather than on the agent's reading of it.

Usage::

    python3 agent_merge_check.py jl-cmd/claude-dev-env 1442
    -> MERGE jl-cmd/claude-dev-env#1442 ab845eb :: green, no open review
       thread, ready for the agent to merge

Exit status is 0 for MERGE, 1 for HOLD, and 2 when the state could not be
read.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from dev_env_scripts_constants.agent_merge_check_constants import (
    ACCEPT_HEADER,
    ALL_HEAD_COMMIT_NODE_KEYS,
    ALL_HOLD_REASONS_BY_STATE,
    ALL_MERGE_QUEUE_REMOVAL_NODE_KEYS,
    ALL_PASSING_CHECK_CONCLUSIONS,
    ALL_OUTDATED_KEYS,
    ALL_RESOLVED_KEYS,
    ALL_THREAD_NODE_KEYS,
    ALL_TOKEN_ENVIRONMENT_VARIABLES,
    AUTHORIZATION_HEADER,
    BASE_KEY,
    BEARER_PREFIX,
    BEHIND_BY_KEY,
    BEHIND_MERGE_QUEUE_HOLD_TEMPLATE,
    BLOCKED_HOLD_REASON,
    BRANCH_RULES_ENDPOINT_TEMPLATE,
    CHECK_NAME_PARAMETER,
    CHECK_PAGE_SIZE,
    CHECK_RUN_APP_ID_KEY,
    CHECK_RUN_APP_KEY,
    CHECK_RUN_COMPLETED_STATUS,
    CHECK_RUN_CONCLUSION_KEY,
    CHECK_RUN_ID_KEY,
    CHECK_RUN_NAME_KEY,
    CHECK_RUN_STATUS_KEY,
    CHECK_RUNS_ENDPOINT_TEMPLATE,
    CHECK_RUNS_KEY,
    COMBINED_STATUS_ENDPOINT_TEMPLATE,
    COMMAND_DESCRIPTION,
    COMMIT_KEY,
    COMMITTED_DATE_KEY,
    COMPARE_ENDPOINT_TEMPLATE,
    CONTENT_TYPE_HEADER,
    CONTEXT_KEY,
    CREATED_AT_KEY,
    DRAFT_HOLD_REASON,
    DRAFT_KEY,
    ERROR_EXIT_CODE,
    FAILED_CHECKS_REMOVAL_REASON,
    FAILING_REQUIRED_CHECKS_HOLD_TEMPLATE,
    GITHUB_ACCEPT_TYPE,
    GITHUB_API_ROOT,
    GITHUB_GRAPHQL_ENDPOINT,
    HEAD_KEY,
    HOLD_EXIT_CODE,
    HOLD_VERDICT_LABEL,
    INTEGRATION_ID_KEY,
    JSON_CONTENT_TYPE,
    MERGE_EXIT_CODE,
    MERGE_QUEUE_EJECTION_HOLD_TEMPLATE,
    MERGE_QUEUE_REMOVAL_PAGE_SIZE,
    MERGE_QUEUE_REMOVAL_QUERY,
    MERGE_QUEUE_RULE_TYPE,
    MERGE_VERDICT_LABEL,
    MERGEABLE_STATE_BLOCKED,
    MERGEABLE_STATE_CLEAN,
    MERGEABLE_STATE_KEY,
    MERGEABLE_STATE_UNKNOWN,
    MISSING_CHECK_STATE,
    NAME_VARIABLE,
    NO_SIGN_IN_MESSAGE,
    NUMBER_ARGUMENT_HELP,
    NUMBER_KEY,
    NUMBER_VARIABLE,
    OWNER_VARIABLE,
    PAGE_SIZE_VARIABLE,
    PENDING_CHECK_STATE,
    PENDING_STATUS_STATE,
    PER_PAGE_PARAMETER,
    PULL_REQUEST_ENDPOINT_TEMPLATE,
    QUERY_KEY,
    READY_DETAIL,
    REF_KEY,
    REMOVAL_REASON_KEY,
    REQUIRED_CHECK_SEPARATOR,
    REQUIRED_CHECK_STATE_TEMPLATE,
    REQUIRED_STATUS_CHECKS_KEY,
    REQUIRED_STATUS_CHECKS_RULE_TYPE,
    REQUEST_TIMEOUT_SECONDS,
    REVIEW_THREAD_PAGE_SIZE,
    REVIEW_THREADS_ENDPOINT_TEMPLATE,
    RULE_PARAMETERS_KEY,
    RULE_TYPE_KEY,
    SETTLE_ATTEMPT_COUNT,
    SETTLE_WAIT_SECONDS,
    SHA_KEY,
    SHORT_SHA_LENGTH,
    SLUG_ARGUMENT_HELP,
    SLUG_SEPARATOR,
    STATUS_STATE_KEY,
    STATUSES_KEY,
    SUCCESS_STATUS_STATE,
    UNKNOWN_STATE_HOLD_TEMPLATE,
    UNRESOLVED_THREAD_QUERY,
    UNRESOLVED_THREADS_HOLD_TEMPLATE,
    UTF8_ENCODING,
    VARIABLES_KEY,
    VERDICT_LINE_TEMPLATE,
)


class MergeCheckError(Exception):
    """Raised when the pull request state could not be read."""


@dataclass(frozen=True)
class RequiredContext:
    """One status check a branch rule requires before a merge.

    Attributes:
        context: The check name the rule requires.
        integration_id: The app that must report it, or None for any app.
    """

    context: str
    integration_id: int | None


@dataclass(frozen=True)
class BlockedEvidence:
    """What GitHub reports behind a ``blocked`` merge state.

    Attributes:
        all_unmet_checks: Each required check not passing on the head, as
            its name and state, such as ``Ruff (failure)``.
        behind_by: How many base commits the head lacks.
        has_merge_queue: Whether a branch rule sends merges through a queue.
    """

    all_unmet_checks: tuple[str, ...]
    behind_by: int
    has_merge_queue: bool


def blocked_hold_reason(evidence: BlockedEvidence) -> str:
    """Name what blocks a pull request GitHub reports as ``blocked``.

    Args:
        evidence: The required checks, the distance behind the base, and the
            merge queue rule read for the pull request.

    Returns:
        The failing required checks by name when any is not passing. The
        behind reason when every required check passes and a merge queue
        refuses a head that lacks base commits. The generic blocked reason
        otherwise.
    """
    if evidence.all_unmet_checks:
        return FAILING_REQUIRED_CHECKS_HOLD_TEMPLATE.format(
            checks=REQUIRED_CHECK_SEPARATOR.join(evidence.all_unmet_checks)
        )
    if evidence.has_merge_queue and evidence.behind_by > 0:
        return BEHIND_MERGE_QUEUE_HOLD_TEMPLATE.format(count=evidence.behind_by)
    return BLOCKED_HOLD_REASON


def hold_reason(
    all_pull_request_fields: Mapping[str, object],
    unresolved_thread_count: int,
    blocked_evidence: BlockedEvidence | None = None,
    is_ejected_from_merge_queue: bool = False,
) -> str | None:
    """Return why this pull request stays open, or None when it may merge.

    Args:
        all_pull_request_fields: The pull request as the GitHub API reports
            it, carrying its draft flag and its merge state.
        unresolved_thread_count: How many review threads are open on it.
        blocked_evidence: What was read behind a ``blocked`` merge state, or
            None when nothing was read.
        is_ejected_from_merge_queue: Whether the merge queue ejected the
            current head for failed checks.

    Returns:
        The reason text for a draft, for a merge state other than clean, for
        a head the merge queue ejected, and for an open review thread. None
        when the pull request is ready for the agent that drives it to merge
        it.
    """
    if all_pull_request_fields.get(DRAFT_KEY):
        return DRAFT_HOLD_REASON
    merge_state = all_pull_request_fields.get(MERGEABLE_STATE_KEY)
    if merge_state == MERGEABLE_STATE_BLOCKED and blocked_evidence is not None:
        return blocked_hold_reason(blocked_evidence)
    if merge_state != MERGEABLE_STATE_CLEAN:
        return ALL_HOLD_REASONS_BY_STATE.get(
            merge_state,
            UNKNOWN_STATE_HOLD_TEMPLATE.format(state=merge_state),
        )
    if is_ejected_from_merge_queue:
        return MERGE_QUEUE_EJECTION_HOLD_TEMPLATE.format(
            base=_optional_nested_field(all_pull_request_fields, BASE_KEY, REF_KEY),
            number=all_pull_request_fields.get(NUMBER_KEY),
        )
    if unresolved_thread_count > 0:
        return UNRESOLVED_THREADS_HOLD_TEMPLATE.format(count=unresolved_thread_count)
    return None


def _optional_nested_field(
    all_fields: Mapping[str, object],
    outer_key: str,
    inner_key: str,
) -> object:
    all_inner_fields = all_fields.get(outer_key)
    if not isinstance(all_inner_fields, Mapping):
        return None
    return all_inner_fields.get(inner_key)


def required_contexts(all_rules: Sequence[object]) -> tuple[RequiredContext, ...]:
    """Collect each status check the branch rules require, once, in order.

    Args:
        all_rules: The rules GitHub reports as active on the base branch.

    Returns:
        The required checks across every required status checks rule.
    """
    all_contexts: dict[RequiredContext, None] = {}
    for each_rule in _rules_of_type(all_rules, REQUIRED_STATUS_CHECKS_RULE_TYPE):
        for each_check in _required_check_records(each_rule):
            all_contexts[_required_context(each_check)] = None
    return tuple(all_contexts)


def has_merge_queue_rule(all_rules: Sequence[object]) -> bool:
    """Report whether a branch rule sends merges through a merge queue.

    Args:
        all_rules: The rules GitHub reports as active on the base branch.

    Returns:
        True when any rule is a merge queue rule.
    """
    return any(_rules_of_type(all_rules, MERGE_QUEUE_RULE_TYPE))


def _rules_of_type(
    all_rules: Sequence[object],
    rule_type: str,
) -> list[Mapping[str, object]]:
    return [
        each_rule
        for each_rule in all_rules
        if isinstance(each_rule, Mapping) and each_rule.get(RULE_TYPE_KEY) == rule_type
    ]


def _required_check_records(
    all_rule_fields: Mapping[str, object],
) -> list[Mapping[str, object]]:
    all_parameters = all_rule_fields.get(RULE_PARAMETERS_KEY)
    if not isinstance(all_parameters, Mapping):
        return []
    all_checks = all_parameters.get(REQUIRED_STATUS_CHECKS_KEY)
    if not isinstance(all_checks, list):
        return []
    return [
        each_check
        for each_check in all_checks
        if isinstance(each_check, Mapping) and each_check.get(CONTEXT_KEY)
    ]


def _required_context(all_check_fields: Mapping[str, object]) -> RequiredContext:
    integration_id = all_check_fields.get(INTEGRATION_ID_KEY)
    return RequiredContext(
        context=str(all_check_fields[CONTEXT_KEY]),
        integration_id=integration_id if isinstance(integration_id, int) else None,
    )


def unmet_check_state(
    required: RequiredContext,
    all_check_runs: Sequence[object],
    all_statuses: Sequence[object],
) -> str | None:
    """Return the state of a required check that is not passing on the head.

    Args:
        required: The check the branch rule requires.
        all_check_runs: The check runs reported on the head commit.
        all_statuses: The latest commit status per context on the head.

    Returns:
        None when the newest matching check run, or failing that the commit
        status of that name, passes. Otherwise its conclusion, ``pending``,
        or ``missing`` when nothing of that name reported.
    """
    newest_run = _newest_matching_run(required, all_check_runs)
    if newest_run is not None:
        return _check_run_state(newest_run)
    status = _matching_status(required.context, all_statuses)
    if status is not None:
        return _status_state(status)
    return MISSING_CHECK_STATE


def _newest_matching_run(
    required: RequiredContext,
    all_check_runs: Sequence[object],
) -> Mapping[str, object] | None:
    all_matching_runs = [
        each_run
        for each_run in all_check_runs
        if isinstance(each_run, Mapping)
        and each_run.get(CHECK_RUN_NAME_KEY) == required.context
        and required.integration_id in (None, _check_run_app_id(each_run))
    ]
    if not all_matching_runs:
        return None
    return max(all_matching_runs, key=_check_run_id)


def _check_run_id(all_run_fields: Mapping[str, object]) -> int:
    run_id = all_run_fields.get(CHECK_RUN_ID_KEY)
    return run_id if isinstance(run_id, int) else 0


def _check_run_app_id(all_run_fields: Mapping[str, object]) -> object:
    all_app_fields = all_run_fields.get(CHECK_RUN_APP_KEY)
    if not isinstance(all_app_fields, Mapping):
        return None
    return all_app_fields.get(CHECK_RUN_APP_ID_KEY)


def _check_run_state(all_run_fields: Mapping[str, object]) -> str | None:
    if all_run_fields.get(CHECK_RUN_STATUS_KEY) != CHECK_RUN_COMPLETED_STATUS:
        return PENDING_CHECK_STATE
    conclusion = all_run_fields.get(CHECK_RUN_CONCLUSION_KEY)
    if conclusion in ALL_PASSING_CHECK_CONCLUSIONS:
        return None
    return str(conclusion)


def _matching_status(
    context: str,
    all_statuses: Sequence[object],
) -> Mapping[str, object] | None:
    for each_status in all_statuses:
        if isinstance(each_status, Mapping) and each_status.get(CONTEXT_KEY) == context:
            return each_status
    return None


def _status_state(all_status_fields: Mapping[str, object]) -> str | None:
    state = all_status_fields.get(STATUS_STATE_KEY)
    if state == SUCCESS_STATUS_STATE:
        return None
    if state == PENDING_STATUS_STATE:
        return PENDING_CHECK_STATE
    return str(state)


def verdict_line(
    slug: str,
    all_pull_request_fields: Mapping[str, object],
    reason: str | None,
) -> str:
    """Build the one line this command prints for a pull request.

    Args:
        slug: The repository as ``owner/name``.
        all_pull_request_fields: The pull request the verdict describes.
        reason: The hold reason, or None for a pull request that may merge.

    Returns:
        A line naming the verdict, the pull request, its head commit, and
        either the hold reason or the ready detail.
    """
    all_head_fields = all_pull_request_fields.get(HEAD_KEY, {})
    head_sha = ""
    if isinstance(all_head_fields, Mapping):
        head_sha = str(all_head_fields.get(SHA_KEY, ""))[:SHORT_SHA_LENGTH]
    return VERDICT_LINE_TEMPLATE.format(
        label=HOLD_VERDICT_LABEL if reason else MERGE_VERDICT_LABEL,
        slug=slug,
        number=all_pull_request_fields.get(NUMBER_KEY),
        sha=head_sha,
        detail=reason or READY_DETAIL,
    )


def count_unresolved_threads(all_thread_records: Sequence[object]) -> int:
    """Count the review threads that still wait on an answer.

    Args:
        all_thread_records: The review threads GitHub reports for the pull
            request.

    Returns:
        How many of them are unresolved and still point at live code. An
        outdated thread names code the pull request has since replaced, so it
        holds nothing back.
    """
    return sum(
        1
        for each_thread in all_thread_records
        if isinstance(each_thread, Mapping)
        and not _any_flag(each_thread, ALL_RESOLVED_KEYS)
        and not _any_flag(each_thread, ALL_OUTDATED_KEYS)
    )


def _is_ejected_on_head(
    all_removal_records: Sequence[object],
    head_committed_at: str,
) -> bool:
    """Report whether a ``failed_checks`` removal is newer than the head.

    A commit that lands after the merge queue ejected the pull request
    carries a fix the queue has not seen yet, so an older removal holds
    nothing back.
    """
    all_failed_check_times = [
        str(each_removal.get(CREATED_AT_KEY))
        for each_removal in all_removal_records
        if isinstance(each_removal, Mapping)
        and each_removal.get(REMOVAL_REASON_KEY) == FAILED_CHECKS_REMOVAL_REASON
    ]
    return (
        bool(all_failed_check_times) and max(all_failed_check_times) > head_committed_at
    )


def _any_flag(all_thread_fields: Mapping[str, object], all_keys: Sequence[str]) -> bool:
    return any(all_thread_fields.get(each_key) for each_key in all_keys)


def _github_token() -> str:
    for each_variable in ALL_TOKEN_ENVIRONMENT_VARIABLES:
        token = os.environ.get(each_variable)
        if token:
            return token
    raise MergeCheckError(NO_SIGN_IN_MESSAGE)


def _request_json(
    url: str,
    token: str,
    all_payload_fields: Mapping[str, object] | None,
) -> object:
    request = urllib.request.Request(url)
    request.add_header(ACCEPT_HEADER, GITHUB_ACCEPT_TYPE)
    request.add_header(AUTHORIZATION_HEADER, BEARER_PREFIX + token)
    body = None
    if all_payload_fields is not None:
        request.add_header(CONTENT_TYPE_HEADER, JSON_CONTENT_TYPE)
        body = json.dumps(all_payload_fields).encode(UTF8_ENCODING)
    try:
        with urllib.request.urlopen(
            request,
            data=body,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as answer:
            return json.loads(answer.read().decode(UTF8_ENCODING))
    except (urllib.error.URLError, ValueError) as failure:
        raise MergeCheckError(str(failure)) from failure


def read_pull_request(slug: str, number: int, token: str) -> Mapping[str, object]:
    """Read one pull request from the GitHub REST API.

    Args:
        slug: The repository as ``owner/name``.
        number: The pull request number.
        token: The GitHub token the request authenticates with.

    Returns:
        The pull request fields, carrying its draft flag, its merge state,
        and its head commit.

    Raises:
        MergeCheckError: The API call failed, or answered with something
            other than a pull request object.
    """
    document = _request_json(
        PULL_REQUEST_ENDPOINT_TEMPLATE.format(
            api_root=GITHUB_API_ROOT,
            slug=slug,
            number=number,
        ),
        token,
        None,
    )
    if not isinstance(document, Mapping):
        raise MergeCheckError(str(document))
    return document


def read_blocked_evidence(
    slug: str,
    all_pull_request_fields: Mapping[str, object],
    token: str,
) -> BlockedEvidence:
    """Read what stands behind a ``blocked`` merge state.

    Args:
        slug: The repository as ``owner/name``.
        all_pull_request_fields: The pull request, carrying its base branch
            and its head commit.
        token: The GitHub token the requests authenticate with.

    Returns:
        The required checks not passing on the head, how far the head is
        behind the base, and whether a merge queue rule applies.

    Raises:
        MergeCheckError: A read failed, or answered with another shape.
    """
    base_ref = urllib.parse.quote(
        str(_nested_field(all_pull_request_fields, BASE_KEY, REF_KEY))
    )
    head_sha = str(_nested_field(all_pull_request_fields, HEAD_KEY, SHA_KEY))
    all_rules = _read_branch_rules(slug, base_ref, token)
    return BlockedEvidence(
        all_unmet_checks=_read_unmet_checks(slug, head_sha, all_rules, token),
        behind_by=_read_behind_by(slug, base_ref, head_sha, token),
        has_merge_queue=has_merge_queue_rule(all_rules),
    )


def _read_branch_rules(slug: str, base_ref: str, token: str) -> list[object]:
    return _request_list(
        BRANCH_RULES_ENDPOINT_TEMPLATE.format(
            api_root=GITHUB_API_ROOT, slug=slug, branch=base_ref
        ),
        token,
    )


def _read_unmet_checks(
    slug: str,
    head_sha: str,
    all_rules: Sequence[object],
    token: str,
) -> tuple[str, ...]:
    all_statuses = _request_list_field(
        COMBINED_STATUS_ENDPOINT_TEMPLATE.format(
            api_root=GITHUB_API_ROOT,
            slug=slug,
            sha=head_sha,
            query=urllib.parse.urlencode({PER_PAGE_PARAMETER: CHECK_PAGE_SIZE}),
        ),
        token,
        STATUSES_KEY,
    )
    all_unmet_checks: list[str] = []
    for each_required in required_contexts(all_rules):
        all_check_runs = _read_check_runs(slug, head_sha, each_required.context, token)
        state = unmet_check_state(each_required, all_check_runs, all_statuses)
        if state is not None:
            all_unmet_checks.append(
                REQUIRED_CHECK_STATE_TEMPLATE.format(
                    context=each_required.context, state=state
                )
            )
    return tuple(all_unmet_checks)


def _read_check_runs(
    slug: str,
    head_sha: str,
    context: str,
    token: str,
) -> list[object]:
    query = urllib.parse.urlencode(
        {CHECK_NAME_PARAMETER: context, PER_PAGE_PARAMETER: CHECK_PAGE_SIZE}
    )
    return _request_list_field(
        CHECK_RUNS_ENDPOINT_TEMPLATE.format(
            api_root=GITHUB_API_ROOT, slug=slug, sha=head_sha, query=query
        ),
        token,
        CHECK_RUNS_KEY,
    )


def _read_behind_by(slug: str, base_ref: str, head_sha: str, token: str) -> int:
    behind_by = _request_field(
        COMPARE_ENDPOINT_TEMPLATE.format(
            api_root=GITHUB_API_ROOT, slug=slug, base=base_ref, head=head_sha
        ),
        token,
        BEHIND_BY_KEY,
    )
    return behind_by if isinstance(behind_by, int) else 0


def _nested_field(
    all_fields: Mapping[str, object],
    outer_key: str,
    inner_key: str,
) -> object:
    all_inner_fields = all_fields.get(outer_key)
    if not isinstance(all_inner_fields, Mapping) or not all_inner_fields.get(inner_key):
        raise MergeCheckError(f"The pull request carries no {outer_key}.{inner_key}.")
    return all_inner_fields[inner_key]


def _request_list(url: str, token: str) -> list[object]:
    document = _request_json(url, token, None)
    if not isinstance(document, list):
        raise MergeCheckError(str(document))
    return document


def _request_field(url: str, token: str, key: str) -> object:
    document = _request_json(url, token, None)
    if not isinstance(document, Mapping) or key not in document:
        raise MergeCheckError(str(document))
    return document[key]


def _request_list_field(url: str, token: str, key: str) -> list[object]:
    all_records = _request_field(url, token, key)
    if not isinstance(all_records, list):
        raise MergeCheckError(str(all_records))
    return all_records


def read_unresolved_thread_count(slug: str, number: int, token: str) -> int:
    """Read how many review threads on a pull request stay open.

    Two routes carry the same fact. A Claude Code session reaches GitHub
    through a proxy that refuses GraphQL and serves the review threads over a
    REST route of its own, so this reads that route first and falls back to
    the GraphQL query every other caller has.

    Args:
        slug: The repository as ``owner/name``.
        number: The pull request number.
        token: The GitHub token the request authenticates with.

    Returns:
        The count of unresolved, current review threads.

    Raises:
        MergeCheckError: Both routes failed, or both answered with a shape
            that carries no review threads.
    """
    all_thread_records = _thread_records_over_rest(slug, number, token)
    if all_thread_records is None:
        return _read_unresolved_thread_count_over_graphql(slug, number, token)
    return count_unresolved_threads(all_thread_records)


def _thread_records_over_rest(
    slug: str,
    number: int,
    token: str,
) -> list[object] | None:
    try:
        document = _request_json(
            REVIEW_THREADS_ENDPOINT_TEMPLATE.format(
                api_root=GITHUB_API_ROOT,
                slug=slug,
                number=number,
            ),
            token,
            None,
        )
    except MergeCheckError:
        return None
    return document if isinstance(document, list) else None


def _pull_request_query_payload(
    query: str,
    page_size: int,
    slug: str,
    number: int,
) -> dict[str, object]:
    owner, _, name = slug.partition(SLUG_SEPARATOR)
    return {
        QUERY_KEY: query,
        VARIABLES_KEY: {
            OWNER_VARIABLE: owner,
            NAME_VARIABLE: name,
            NUMBER_VARIABLE: number,
            PAGE_SIZE_VARIABLE: page_size,
        },
    }


def _read_unresolved_thread_count_over_graphql(
    slug: str,
    number: int,
    token: str,
) -> int:
    document = _request_json(
        GITHUB_GRAPHQL_ENDPOINT,
        token,
        _pull_request_query_payload(
            UNRESOLVED_THREAD_QUERY, REVIEW_THREAD_PAGE_SIZE, slug, number
        ),
    )
    all_thread_records = functools.reduce(
        functools.partial(_field_at, document),
        ALL_THREAD_NODE_KEYS,
        document,
    )
    if not isinstance(all_thread_records, Sequence):
        raise MergeCheckError(str(document))
    return count_unresolved_threads(all_thread_records)


def _field_at(document: object, all_fields: object, key: str) -> object:
    if not isinstance(all_fields, Mapping):
        raise MergeCheckError(str(document))
    return all_fields.get(key)


def read_merge_queue_ejection(slug: str, number: int, token: str) -> bool:
    """Read whether the merge queue ejected the pull request's current head.

    Only GraphQL reports why a pull request left the merge queue. A
    repository with no merge queue reports no removal events.

    Args:
        slug: The repository as ``owner/name``.
        number: The pull request number.
        token: The GitHub token the request authenticates with.

    Returns:
        True when a ``failed_checks`` removal is newer than the head commit.

    Raises:
        MergeCheckError: The query failed, or answered with another shape.
    """
    document = _request_json(
        GITHUB_GRAPHQL_ENDPOINT,
        token,
        _pull_request_query_payload(
            MERGE_QUEUE_REMOVAL_QUERY, MERGE_QUEUE_REMOVAL_PAGE_SIZE, slug, number
        ),
    )
    return _is_ejected_on_head(
        _list_along(document, ALL_MERGE_QUEUE_REMOVAL_NODE_KEYS),
        _head_committed_at(document),
    )


def _list_along(document: object, all_keys: Sequence[str]) -> list[object]:
    all_records = functools.reduce(
        functools.partial(_field_at, document), all_keys, document
    )
    if not isinstance(all_records, list):
        raise MergeCheckError(str(document))
    return all_records


def _head_committed_at(document: object) -> str:
    all_head_commits = _list_along(document, ALL_HEAD_COMMIT_NODE_KEYS)
    if not all_head_commits:
        raise MergeCheckError(str(document))
    head_committed_at = functools.reduce(
        functools.partial(_field_at, document),
        (COMMIT_KEY, COMMITTED_DATE_KEY),
        all_head_commits[-1],
    )
    if not isinstance(head_committed_at, str):
        raise MergeCheckError(str(document))
    return head_committed_at


def read_settled_pull_request(
    slug: str,
    number: int,
    token: str,
    sleep: Callable[[float], None],
) -> Mapping[str, object]:
    """Read a pull request whose merge state GitHub has worked out.

    GitHub reports ``unknown`` while it computes mergeability after a push,
    so this reads again until the state settles.

    Args:
        slug: The repository as ``owner/name``.
        number: The pull request number.
        token: The GitHub token the request authenticates with.
        sleep: How the caller waits between reads.

    Returns:
        The fields the last read reported.

    Raises:
        MergeCheckError: A read failed.
    """
    for each_attempt in range(SETTLE_ATTEMPT_COUNT):
        all_pull_request_fields = read_pull_request(slug, number, token)
        if all_pull_request_fields.get(MERGEABLE_STATE_KEY) != MERGEABLE_STATE_UNKNOWN:
            return all_pull_request_fields
        if each_attempt + 1 < SETTLE_ATTEMPT_COUNT:
            sleep(SETTLE_WAIT_SECONDS)
    return all_pull_request_fields


def main(all_arguments: Sequence[str]) -> int:
    """Print the merge verdict for one pull request.

    Args:
        all_arguments: The command line, without the program name.

    Returns:
        Zero when the pull request may merge, one when it holds, and two
        when its state could not be read.
    """
    parser = argparse.ArgumentParser(description=COMMAND_DESCRIPTION)
    parser.add_argument("slug", help=SLUG_ARGUMENT_HELP)
    parser.add_argument("number", type=int, help=NUMBER_ARGUMENT_HELP)
    parsed = parser.parse_args(all_arguments)
    try:
        token = _github_token()
        all_pull_request_fields = read_settled_pull_request(
            parsed.slug, parsed.number, token, time.sleep
        )
        unresolved_thread_count = read_unresolved_thread_count(
            parsed.slug, parsed.number, token
        )
        is_ejected_from_merge_queue = read_merge_queue_ejection(
            parsed.slug, parsed.number, token
        )
    except MergeCheckError as failure:
        print(failure, file=sys.stderr)
        return ERROR_EXIT_CODE
    blocked_evidence = None
    if all_pull_request_fields.get(MERGEABLE_STATE_KEY) == MERGEABLE_STATE_BLOCKED:
        try:
            blocked_evidence = read_blocked_evidence(
                parsed.slug, all_pull_request_fields, token
            )
        except MergeCheckError as failure:
            print(failure, file=sys.stderr)
    reason = hold_reason(
        all_pull_request_fields,
        unresolved_thread_count,
        blocked_evidence,
        is_ejected_from_merge_queue,
    )
    print(verdict_line(parsed.slug, all_pull_request_fields, reason))
    return HOLD_EXIT_CODE if reason else MERGE_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
