"""Read the pull request open a PreToolUse payload asks for, and the head it opens with."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.merge_review_gate_constants import (
    ALL_CURRENT_BRANCH_ARGUMENTS,
    ALL_NON_INTERACTIVE_GIT_SETTINGS,
    ALL_ORIGIN_URL_ARGUMENTS,
    ALL_REMOTE_URL_CONFIG_ARGUMENTS,
    ALL_SHELL_TOOL_NAMES,
    ALL_SSH_COMMAND_CONFIG_ARGUMENTS,
    CHANGE_FOLDER_PATTERN,
    CREATE_TEXT_OPTION_PATTERN,
    CREATE_TOOL_SUFFIX,
    CURRENT_HEAD_REFERENCE,
    CWD_FIELD,
    DEFAULT_SSH_COMMAND,
    GH_PR_CREATE_PATTERN,
    GITHUB_REMOTE_URL_PATTERN,
    GITHUB_REMOTE_URL_TEMPLATE,
    GIT_TIMEOUT_SECONDS,
    HEAD_BRANCH_FIELD,
    HEAD_OPTION_PATTERN,
    HTTPS_SCHEME,
    LS_REMOTE_FIELD_SEPARATOR,
    ORIGIN_URL_PATTERN,
    OWNER_FIELD,
    PREFERRED_REMOTE_NAME,
    PULL_REQUEST_SCRIPT_CREATE_PATTERN,
    REMOTE_BRANCH_PREFIX,
    REMOTE_BRANCH_REFERENCE_TEMPLATE,
    REMOTE_LOOKUP_TIMEOUT_SECONDS,
    REMOTE_URL_LINE_PATTERN,
    REPO_FIELD,
    REPO_OPTION_PATTERN,
    SSH_BATCH_OPTION,
    SSH_COMMAND_VARIABLE,
    SSH_PROGRAM_VARIABLE,
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


@dataclass(frozen=True)
class _CheckoutRemote:
    name: str
    url: str
    owner: str
    repo: str


def open_request_from(all_payload_fields: dict[str, object]) -> OpenRequest | None:
    """Read the pull request open a PreToolUse payload asks for.

    ::

        mcp__github__create_pull_request {owner, repo, head}
        gh pr create --repo o/r --head branch
        python pull_request.py create --repo o/r --head branch

    A branch resolves to the commit GitHub lists for it. The lookup reads the
    https or SSH github.com URL of a remote of the payload's folder or a ``cd``
    target that names the same owner and repository, else
    https://github.com. A fork head ``user:branch`` reads a remote URL of that
    owner, the one named like the base repository first, else the fork named
    like the base repository. Other remote URLs are ignored. When GitHub lists
    no such branch, the checkout's local branch, then ``origin/<branch>``,
    resolves it. A failed lookup reads no head. No head means the current
    branch, or the checked-out commit when HEAD is detached; no repository,
    ``origin``.

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
    all_arguments: list[str],
    folder: str | None,
    timeout_seconds: int = GIT_TIMEOUT_SECONDS,
    all_extra_settings: dict[str, str] | None = None,
) -> str | None:
    with tempfile.TemporaryFile() as output:
        try:
            completed = subprocess.run(
                ["git", *all_arguments],
                cwd=folder,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=timeout_seconds,
                check=False,
                env={**os.environ, **ALL_NON_INTERACTIVE_GIT_SETTINGS, **(all_extra_settings or {})},
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if completed.returncode != 0:
            return None
        output.seek(0)
        return output.read().decode("utf-8", "replace").strip()


def _branch_commit(branch: str, folder: str | None, owner: str, repo: str) -> str | None:
    if ":" in branch:
        return _fork_branch_commit(branch, folder, repo)
    if branch == CURRENT_HEAD_REFERENCE:
        current_branch = _run_git(list(ALL_CURRENT_BRANCH_ARGUMENTS), folder)
        if not current_branch or not owner or not repo:
            return _local_commit(branch, folder)
        branch = current_branch
    if not owner or not repo:
        return _local_branch_commit(branch, folder)
    listing = _github_listing(owner, repo, branch, folder, matches_any_repository=False)
    if listing is None:
        return None
    return _listed_commit(listing, branch) or _local_branch_commit(branch, folder)


def _fork_branch_commit(branch: str, folder: str | None, repo: str) -> str | None:
    fork_owner, _, fork_branch = branch.partition(":")
    if not fork_owner or not repo:
        return None
    listing = _github_listing(fork_owner, repo, fork_branch, folder, matches_any_repository=True)
    return _listed_commit(listing or "", fork_branch)


def _local_branch_commit(branch: str, folder: str | None) -> str | None:
    return _local_commit(branch, folder) or _local_commit(REMOTE_BRANCH_PREFIX + branch, folder)


def _local_commit(reference: str, folder: str | None) -> str | None:
    return _run_git(["rev-parse", "--verify", "--quiet", f"{reference}^{{commit}}"], folder)


def _github_listing(
    owner: str, repo: str, branch_name: str, folder: str | None, matches_any_repository: bool
) -> str | None:
    remote_url = _checkout_remote_url(owner, repo, folder, matches_any_repository)
    if remote_url is None:
        remote_url = GITHUB_REMOTE_URL_TEMPLATE.format(owner=owner, repo=repo)
    reference = REMOTE_BRANCH_REFERENCE_TEMPLATE.format(branch=branch_name)
    return _run_git(
        ["ls-remote", "--", remote_url, reference],
        None,
        REMOTE_LOOKUP_TIMEOUT_SECONDS,
        _non_interactive_ssh_settings(remote_url),
    )


def _non_interactive_ssh_settings(remote_url: str) -> dict[str, str]:
    if remote_url.startswith(HTTPS_SCHEME):
        return {}
    if SSH_PROGRAM_VARIABLE in os.environ and SSH_COMMAND_VARIABLE not in os.environ:
        return {}
    ssh_command = (
        os.environ.get(SSH_COMMAND_VARIABLE)
        or _run_git(list(ALL_SSH_COMMAND_CONFIG_ARGUMENTS), None)
        or DEFAULT_SSH_COMMAND
    )
    return {SSH_COMMAND_VARIABLE: f"{ssh_command} {SSH_BATCH_OPTION}"}


def _checkout_remote_url(
    owner: str, repo: str, folder: str | None, matches_any_repository: bool
) -> str | None:
    all_candidates = [
        each_remote
        for each_remote in _checkout_remotes(folder)
        if each_remote.owner.casefold() == owner.casefold()
        and (matches_any_repository or each_remote.repo.casefold() == repo.casefold())
    ]
    best_candidate = min(
        all_candidates,
        key=lambda each_remote: (
            each_remote.repo.casefold() != repo.casefold(),
            each_remote.name != PREFERRED_REMOTE_NAME,
        ),
        default=None,
    )
    return best_candidate.url if best_candidate else None


def _checkout_remotes(folder: str | None) -> list[_CheckoutRemote]:
    config = _run_git(list(ALL_REMOTE_URL_CONFIG_ARGUMENTS), folder)
    all_remotes: list[_CheckoutRemote] = []
    for each_line in (config or "").splitlines():
        line_match = REMOTE_URL_LINE_PATTERN.fullmatch(each_line)
        url_match = GITHUB_REMOTE_URL_PATTERN.fullmatch(line_match["url"]) if line_match else None
        if line_match and url_match:
            all_remotes.append(
                _CheckoutRemote(
                    name=line_match["name"],
                    url=line_match["url"],
                    owner=url_match["owner"],
                    repo=url_match["repo"],
                )
            )
    return all_remotes


def _listed_commit(listing: str, branch_name: str) -> str | None:
    reference = REMOTE_BRANCH_REFERENCE_TEMPLATE.format(branch=branch_name)
    for each_line in listing.splitlines():
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
