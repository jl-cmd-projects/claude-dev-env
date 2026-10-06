"""Find an open follow-up pull request that already holds a new one's parent findings."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.followup_pr_dedupe_constants import (
    ALL_BODY_FILE_OPTIONS,
    ALL_BODY_OPTIONS,
    ALL_REPOSITORY_OPTIONS,
    CREATE_PULL_REQUEST_TOOL_SUFFIX,
    DUPLICATE_FOLLOWUP_REASON_TEMPLATE,
    FOLLOWUP_PARENT_PATTERN,
    ALL_GH_CREATE_WORDS,
    ALL_GIT_REMOTE_COMMAND_WORDS,
    GITHUB_API_ROOT,
    GITHUB_REMOTE_PATTERN,
    OPEN_PULL_REQUESTS_PATH_TEMPLATE,
    READ_TIMEOUT_SECONDS,
    STANDARD_INPUT_PATH,
)
from hooks_constants.pr_lifecycle_skill_gate_constants import SHELL_TOOL_NAMES
from hooks_constants.pytest_invocation import unquoted_token
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING
from hooks_constants.shell_command_pipeline import pipeline_segments_for_command
from hooks_constants.shell_command_wrappers import (
    all_wrapped_command_texts,
    segment_program_and_arguments,
)


@dataclass(frozen=True)
class PullRequestDraft:
    """The repository and body of a pull request about to be opened."""

    owner: str
    repo: str
    body: str


OpenPullRequestReader = Callable[[str, str], list[Mapping[str, object]]]


def followup_parent_number(body: str) -> int | None:
    """Return the parent number a "Follow-up to #N" line names, or None."""
    match = re.search(FOLLOWUP_PARENT_PATTERN, body, re.IGNORECASE)
    return int(match.group(1)) if match else None


def read_open_pull_requests(owner: str, repo: str) -> list[Mapping[str, object]]:
    """Read one page of a repository's open pull requests from the GitHub API."""
    url = GITHUB_API_ROOT + OPEN_PULL_REQUESTS_PATH_TEMPLATE.format(owner=owner, repo=repo)
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=READ_TIMEOUT_SECONDS) as reply:
        answer = json.loads(reply.read())
    return [each_entry for each_entry in answer if isinstance(each_entry, dict)]


def _option_value(all_arguments: list[str], all_option_names: frozenset[str]) -> str | None:
    for each_index, each_argument in enumerate(all_arguments):
        option_name, separator, inline_value = each_argument.partition("=")
        if option_name not in all_option_names:
            continue
        if separator:
            return unquoted_token(inline_value)
        if each_index + 1 < len(all_arguments):
            return unquoted_token(all_arguments[each_index + 1])
    return None


def body_from_arguments(all_arguments: list[str], working_directory: str) -> str | None:
    """Return the body a gh-style argument list passes, or None when it passes none.

    ``--body`` text comes back as given. A ``--body-file`` path is read from
    the working directory. Standard input and an unreadable file give None.
    """
    inline_body = _option_value(all_arguments, ALL_BODY_OPTIONS)
    if inline_body is not None:
        return inline_body
    body_path = _option_value(all_arguments, ALL_BODY_FILE_OPTIONS)
    if body_path is None or body_path == STANDARD_INPUT_PATH:
        return None
    try:
        return (Path(working_directory) / body_path).read_text(
            encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY
        )
    except OSError:
        return None


def _origin_repository(working_directory: str) -> tuple[str, str] | None:
    try:
        completed = subprocess.run(
            ALL_GIT_REMOTE_COMMAND_WORDS,
            cwd=working_directory or None,
            capture_output=True,
            text=True,
            timeout=READ_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(GITHUB_REMOTE_PATTERN, completed.stdout.strip())
    return (match.group(1), match.group(2)) if match else None


def _repository_from_arguments(
    all_arguments: list[str], working_directory: str
) -> tuple[str, str] | None:
    named_repository = _option_value(all_arguments, ALL_REPOSITORY_OPTIONS)
    if named_repository is None:
        return _origin_repository(working_directory)
    owner, separator, repo = named_repository.rpartition("/")
    owner = owner.rpartition("/")[2]
    return (owner, repo) if separator and owner and repo else None


def _segment_draft(all_segment_tokens: list[str], working_directory: str) -> PullRequestDraft | None:
    program, all_arguments = segment_program_and_arguments(all_segment_tokens)
    if program != "gh" or all_arguments[: len(ALL_GH_CREATE_WORDS)] != ALL_GH_CREATE_WORDS:
        return None
    body = body_from_arguments(all_arguments, working_directory)
    repository = _repository_from_arguments(all_arguments, working_directory)
    if body is None or repository is None:
        return None
    return PullRequestDraft(repository[0], repository[1], body)


def _shell_draft(command: str, working_directory: str) -> PullRequestDraft | None:
    all_drafts = (
        _segment_draft(each_segment, working_directory)
        for each_text in all_wrapped_command_texts(command)
        for each_segment, _each_following_operator in pipeline_segments_for_command(each_text)
    )
    return next((each_draft for each_draft in all_drafts if each_draft is not None), None)


def pull_request_draft(all_payload_fields: Mapping[str, object]) -> PullRequestDraft | None:
    """Return the pull request a PreToolUse payload is about to open, or None."""
    tool_name = all_payload_fields.get("tool_name")
    tool_input = all_payload_fields.get("tool_input")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return None
    if tool_name.endswith(CREATE_PULL_REQUEST_TOOL_SUFFIX):
        owner, repo, body = (tool_input.get(each_key) for each_key in ("owner", "repo", "body"))
        if isinstance(owner, str) and isinstance(repo, str) and isinstance(body, str):
            return PullRequestDraft(owner, repo, body)
        return None
    command = tool_input.get("command")
    if tool_name not in SHELL_TOOL_NAMES or not isinstance(command, str):
        return None
    working_directory = all_payload_fields.get("cwd")
    return _shell_draft(command, working_directory if isinstance(working_directory, str) else "")


def _reason_for_parent(
    parent_number: int, all_open_pull_requests: list[Mapping[str, object]]
) -> str | None:
    all_same_parent = [
        each_pull_request
        for each_pull_request in all_open_pull_requests
        if followup_parent_number(str(each_pull_request.get("body") or "")) == parent_number
    ]
    if not all_same_parent:
        return None
    return DUPLICATE_FOLLOWUP_REASON_TEMPLATE.format(
        open_number=all_same_parent[0].get("number"),
        parent_number=parent_number,
        open_url=all_same_parent[0].get("html_url"),
    )


def duplicate_followup_reason(
    all_payload_fields: Mapping[str, object],
    read_open: OpenPullRequestReader | None = None,
) -> str | None:
    """Return a deny reason when an open pull request already follows up the same parent.

    Any read failure returns None, so the pull request opens.

    Args:
        all_payload_fields: The parsed PreToolUse input.
        read_open: Reads the open pull requests of an owner and repository;
            None reads them from the GitHub API.
    """
    draft = pull_request_draft(all_payload_fields)
    if draft is None:
        return None
    parent_number = followup_parent_number(draft.body)
    if parent_number is None:
        return None
    try:
        all_open_pull_requests = (read_open or read_open_pull_requests)(draft.owner, draft.repo)
    except Exception:
        return None
    return _reason_for_parent(parent_number, all_open_pull_requests)
