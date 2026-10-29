"""Read the pull request open a PreToolUse payload asks for, and the head it opens with."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.merge_review_gate_constants import (
    ALL_ORIGIN_URL_ARGUMENTS,
    ALL_SHELL_TOOL_NAMES,
    CHANGE_FOLDER_PATTERN,
    CREATE_TEXT_OPTION_PATTERN,
    CREATE_TOOL_SUFFIX,
    CURRENT_HEAD_REFERENCE,
    CWD_FIELD,
    GH_PR_CREATE_PATTERN,
    GITHUB_REMOTE_URL_TEMPLATE,
    GIT_TERMINAL_PROMPT_DISABLED,
    GIT_TERMINAL_PROMPT_VARIABLE,
    GIT_TIMEOUT_SECONDS,
    HEAD_BRANCH_FIELD,
    HEAD_OPTION_PATTERN,
    LS_REMOTE_FIELD_SEPARATOR,
    ORIGIN_URL_PATTERN,
    OWNER_FIELD,
    PULL_REQUEST_SCRIPT_CREATE_PATTERN,
    REMOTE_BRANCH_PREFIX,
    REMOTE_BRANCH_REFERENCE_TEMPLATE,
    REMOTE_LOOKUP_TIMEOUT_SECONDS,
    REPO_FIELD,
    REPO_OPTION_PATTERN,
)


@dataclass(frozen=True)
class OpenRequest:
    """One pull request a tool call asks to open.

    Attributes:
        owner: Repository owner, or empty when it could not be read.
        repo: Repository name, or empty when it could not be read.
        head: The commit the pull request would open with, or None.
    """

    owner: str
    repo: str
    head: str | None

    @property
    def slug(self) -> str:
        """Return ``owner/repo``."""
        return f"{self.owner}/{self.repo}"


def open_request_from(all_payload_fields: dict[str, object]) -> OpenRequest | None:
    """Read the pull request open a PreToolUse payload asks for.

    ::

        mcp__github__create_pull_request {owner, repo, head}
        gh pr create --repo o/r --head branch
        python pull_request.py create --repo o/r --head branch

    A branch resolves in the payload's folder or a ``cd`` target, as
    ``origin/<branch>`` first. When no checkout holds it, GitHub's branch on the
    named repository resolves it, or on the fork in ``user:branch``. No head
    means ``HEAD``; no repository, ``origin``.

    Args:
        all_payload_fields: The parsed PreToolUse input.

    Returns:
        The open request, or None when the call opens no pull request.
    """
    tool_name = all_payload_fields.get("tool_name")
    tool_input = all_payload_fields.get("tool_input")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return None
    working_folder = all_payload_fields.get(CWD_FIELD)
    folder = working_folder if isinstance(working_folder, str) and working_folder else None
    if tool_name.endswith(CREATE_TOOL_SUFFIX):
        return _tool_open_request(tool_input, folder)
    command = tool_input.get("command")
    if tool_name not in ALL_SHELL_TOOL_NAMES or not isinstance(command, str):
        return None
    return _shell_open_request(command, folder)


def _tool_open_request(all_tool_input: dict[object, object], folder: str | None) -> OpenRequest:
    owner = str(all_tool_input.get(OWNER_FIELD, ""))
    repo = str(all_tool_input.get(REPO_FIELD, ""))
    branch = all_tool_input.get(HEAD_BRANCH_FIELD)
    if not isinstance(branch, str) or not branch:
        return OpenRequest(owner=owner, repo=repo, head=None)
    return OpenRequest(owner=owner, repo=repo, head=_branch_commit(branch, folder, owner, repo))


def _shell_open_request(command: str, folder: str | None) -> OpenRequest | None:
    options_only = CREATE_TEXT_OPTION_PATTERN.sub(" ", command)
    create_match = GH_PR_CREATE_PATTERN.search(
        options_only
    ) or PULL_REQUEST_SCRIPT_CREATE_PATTERN.search(options_only)
    if not create_match:
        return None
    folder = _folder_after_changes(options_only[: create_match.start()], folder)
    rest = create_match["rest"]
    repo_match = REPO_OPTION_PATTERN.search(rest)
    owner, repo = (
        (repo_match["owner"], repo_match["repo"]) if repo_match else _origin_repository(folder)
    )
    head_match = HEAD_OPTION_PATTERN.search(rest)
    branch = head_match["head"] if head_match else CURRENT_HEAD_REFERENCE
    return OpenRequest(owner=owner, repo=repo, head=_branch_commit(branch, folder, owner, repo))


def _folder_after_changes(command_before_create: str, folder: str | None) -> str | None:
    all_changes = list(CHANGE_FOLDER_PATTERN.finditer(command_before_create))
    if not all_changes:
        return folder
    target = Path(os.path.expanduser(all_changes[-1]["folder"].strip("\"'")))
    if not target.is_absolute() and folder:
        target = Path(folder) / target
    return str(target)


def _run_git(
    all_arguments: list[str], folder: str | None, timeout_seconds: int = GIT_TIMEOUT_SECONDS
) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *all_arguments],
            cwd=folder,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env={**os.environ, GIT_TERMINAL_PROMPT_VARIABLE: GIT_TERMINAL_PROMPT_DISABLED},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _branch_commit(branch: str, folder: str | None, owner: str, repo: str) -> str | None:
    if ":" in branch:
        fork_owner, _, fork_branch = branch.partition(":")
        return _remote_branch_commit(fork_owner, repo, fork_branch)
    all_references = (
        (branch,) if branch == CURRENT_HEAD_REFERENCE else (REMOTE_BRANCH_PREFIX + branch, branch)
    )
    for each_reference in all_references:
        commit = _run_git(
            ["rev-parse", "--verify", "--quiet", f"{each_reference}^{{commit}}"], folder
        )
        if commit:
            return commit
    if branch == CURRENT_HEAD_REFERENCE:
        return None
    return _remote_branch_commit(owner, repo, branch)


def _remote_branch_commit(owner: str, repo: str, branch_name: str) -> str | None:
    if not owner or not repo:
        return None
    remote_url = GITHUB_REMOTE_URL_TEMPLATE.format(owner=owner, repo=repo)
    reference = REMOTE_BRANCH_REFERENCE_TEMPLATE.format(branch=branch_name)
    listing = _run_git(["ls-remote", remote_url, reference], None, REMOTE_LOOKUP_TIMEOUT_SECONDS)
    for each_line in (listing or "").splitlines():
        commit, separator, listed_reference = each_line.partition(LS_REMOTE_FIELD_SEPARATOR)
        if separator and listed_reference == reference:
            return commit
    return None


def _origin_repository(folder: str | None) -> tuple[str, str]:
    origin_url = _run_git(list(ALL_ORIGIN_URL_ARGUMENTS), folder)
    origin_match = ORIGIN_URL_PATTERN.search(origin_url) if origin_url else None
    if not origin_match:
        return "", ""
    return origin_match["owner"], origin_match["repo"]
