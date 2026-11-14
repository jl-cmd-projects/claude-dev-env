"""Read each pull request open a PreToolUse payload asks for, and the head each opens with."""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.followup_pr_dedupe import named_repository, option_value
from blocking.merge_review_gate_parts.create_folders import PlacedCreate, all_placed_creates
from blocking.gate_run_reads import (
    ReadSlice,
    answer_once,
    child_stdout,
)
from hooks_constants.merge_review_gate_constants import (
    ALL_NON_INTERACTIVE_GIT_SETTINGS,
    ALL_ORIGIN_URL_ARGUMENTS,
    ALL_REPOSITORY_OPTIONS,
    ALL_SHELL_TOOL_NAMES,
    ALL_VALUELESS_LONG_CREATE_OPTIONS,
    ALL_VALUELESS_SHORT_CREATE_LETTERS,
    CHANGE_FOLDER_PATTERN,
    CREATE_TEXT_OPTION_PATTERN,
    CREATE_TOOL_SUFFIX,
    CURRENT_HEAD_REFERENCE,
    CWD_FIELD,
    GH_PR_CREATE_PATTERN,
    GH_PROGRAM_NAME,
    GITHUB_REMOTE_URL_TEMPLATE,
    GIT_TIMEOUT_SECONDS,
    HEAD_BRANCH_FIELD,
    HEAD_OPTION_PATTERN,
    HEAD_SHORT_LETTER,
    LONG_HEAD_OPTION,
    LONG_OPTION_PREFIX,
    LONG_REPOSITORY_OPTION,
    LS_REMOTE_FIELD_SEPARATOR,
    OPTION_AND_VALUE_WIDTH,
    OPTION_VALUE_SEPARATOR,
    ORIGIN_URL_PATTERN,
    ORIGIN_URL_QUESTION,
    OWNER_FIELD,
    PULL_REQUEST_SCRIPT_CREATE_PATTERN,
    REMOTE_BRANCH_PREFIX,
    REMOTE_BRANCH_REFERENCE_TEMPLATE,
    REMOTE_LOOKUP_TIMEOUT_SECONDS,
    REPO_FIELD,
    REPO_OPTION_PATTERN,
    REPOSITORY_SHORT_LETTER,
    SHORT_HEAD_OPTION,
    SHORT_OPTION_PREFIX,
)
from hooks_constants.pytest_invocation import unquoted_token
from hooks_constants.shell_command_wrappers import segment_program_and_arguments


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
class ToolOpenCall:
    """A create pull request tool call, before the gate reads its head.

    Attributes:
        owner: Repository owner the call names, or empty.
        repo: Repository name the call names, or empty.
        branch: The head branch the call names, or None.
        folder: The payload's folder, or None.
    """

    owner: str
    repo: str
    branch: str | None
    folder: str | None


@dataclass(frozen=True)
class ShellOpenCall:
    """One create in a shell command, before the gate reads its repository and head.

    Attributes:
        repository: The ``(owner, repo)`` its ``--repo``, root ``-R`` or ``GH_REPO`` names, or None to read ``origin``.
        branch: The branch its ``--head`` names, or ``HEAD``.
        folder: The folder in effect at the create, after each folder change before it.
        is_folder_followed: False when a folder change before it could not be followed.
    """

    repository: tuple[str, str] | None
    branch: str
    folder: str | None
    is_folder_followed: bool = True


OpenCall = ToolOpenCall | ShellOpenCall


def open_calls_from(all_payload_fields: dict[str, object]) -> list[OpenCall]:
    """Return every pull request open a PreToolUse payload asks for, in command order.

    This reads the payload only. No git or GitHub read runs here::

        mcp__github__create_pull_request {owner, repo, head}   -> [ToolOpenCall]
        gh pr create --head a && cd x && pull_request.py create -> [ShellOpenCall a, ShellOpenCall HEAD in x]
        gh pr merge 12                                          -> []

    Each walked create gives one call per head it names, in its own folder.
    The pattern reading of the first create adds one call no walk call equals.

    Args:
        all_payload_fields: The parsed PreToolUse input.

    Returns:
        One call per create, empty when the call opens no pull request.
    """
    tool_name = all_payload_fields.get("tool_name")
    tool_input = all_payload_fields.get("tool_input")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return []
    folder = _payload_folder(all_payload_fields)
    if tool_name.endswith(CREATE_TOOL_SUFFIX):
        return [_tool_open_call(tool_input, folder)]
    command = tool_input.get("command")
    if tool_name not in ALL_SHELL_TOOL_NAMES or not isinstance(command, str):
        return []
    return _shell_open_calls(command, folder)


def _payload_folder(all_payload_fields: dict[str, object]) -> str | None:
    working_folder = all_payload_fields.get(CWD_FIELD)
    return working_folder if isinstance(working_folder, str) and working_folder else None


def open_request_for(call: OpenCall) -> OpenRequest:
    """Read the repository and the head commit one open would use.

    A tool call reads its head branch from GitHub first::

        ToolOpenCall acme/tools, head feature pushed at abc123 -> OpenRequest(acme, tools, abc123)
        ShellOpenCall, no --repo, origin names acme/tools      -> OpenRequest(acme, tools, <HEAD commit>)
        a read that failed or ran out of time                  -> that part empty, or head None
        ShellOpenCall whose folder change was not followed     -> head None, no read

    A fork head ``user:branch`` reads the repository of ``user``. A branch
    GitHub does not list, and every branch of a shell create, resolves in the
    call's folder as ``origin/<branch>`` first.

    Args:
        call: One open from ``open_calls_from``.

    Returns:
        The open request with the commit it would open with.
    """
    if isinstance(call, ToolOpenCall):
        return _tool_open_request(call)
    return _shell_open_request(call)


def _tool_open_request(call: ToolOpenCall) -> OpenRequest:
    head = (
        _pushed_commit(call.owner, call.repo, call.branch)
        or _branch_commit(call.branch, call.folder)
        if call.branch
        else None
    )
    return OpenRequest(owner=call.owner, repo=call.repo, head=head)


def _shell_open_request(call: ShellOpenCall) -> OpenRequest:
    if not call.is_folder_followed:
        owner, repo = call.repository or ("", "")
        return OpenRequest(owner=owner, repo=repo, head=None)
    owner, repo = call.repository or _origin_repository(call.folder)
    return OpenRequest(owner=owner, repo=repo, head=_branch_commit(call.branch, call.folder))


def _tool_open_call(all_tool_input: dict[object, object], folder: str | None) -> ToolOpenCall:
    branch = all_tool_input.get(HEAD_BRANCH_FIELD)
    return ToolOpenCall(
        owner=str(all_tool_input.get(OWNER_FIELD, "")),
        repo=str(all_tool_input.get(REPO_FIELD, "")),
        branch=branch if isinstance(branch, str) and branch else None,
        folder=folder,
    )


def _shell_open_calls(command: str, folder: str | None) -> list[OpenCall]:
    all_calls: list[OpenCall] = []
    for each_create in all_placed_creates(command, folder):
        all_calls.extend(_placed_open_calls(each_create))
    floor_call = _floor_open_call(command, folder)
    if floor_call is not None:
        all_calls.append(floor_call)
    return list(dict.fromkeys(all_calls))


def _placed_open_calls(placed_create: PlacedCreate) -> list[ShellOpenCall]:
    return [
        ShellOpenCall(
            repository=_placed_repository(placed_create),
            branch=each_head,
            folder=placed_create.folder,
            is_folder_followed=placed_create.is_folder_followed,
        )
        for each_head in _placed_heads(placed_create) or [CURRENT_HEAD_REFERENCE]
    ]


def _option_words(placed_create: PlacedCreate) -> list[str]:
    program, all_gh_words = segment_program_and_arguments(list(placed_create.all_command_words))
    return all_gh_words if program == GH_PROGRAM_NAME else list(placed_create.all_arguments)


def _placed_repository(placed_create: PlacedCreate) -> tuple[str, str] | None:
    all_arguments = list(placed_create.all_arguments)
    all_words = _option_words(placed_create)
    flag_value = _last_option_value(all_words, LONG_REPOSITORY_OPTION, REPOSITORY_SHORT_LETTER)
    if flag_value is None:
        flag_value = option_value(all_arguments, ALL_REPOSITORY_OPTIONS)
    return named_repository(flag_value) if flag_value is not None else None


def _placed_heads(placed_create: PlacedCreate) -> list[str]:
    all_heads = _named_heads(list(placed_create.all_arguments))
    last_head = _last_option_value(_option_words(placed_create), LONG_HEAD_OPTION, HEAD_SHORT_LETTER)
    if last_head and last_head not in all_heads:
        all_heads.append(last_head)
    return all_heads


def _last_option_value(all_words: list[str], long_option: str, short_letter: str) -> str | None:
    last_value: str | None = None
    index = 0
    while index < len(all_words) and unquoted_token(all_words[index]) != LONG_OPTION_PREFIX:
        following = all_words[index + 1] if index + 1 < len(all_words) else None
        flag_value, width = _option_reading(unquoted_token(all_words[index]), following, long_option, short_letter)
        if flag_value is not None:
            last_value = unquoted_token(flag_value)
        index += width
    return last_value


def _option_reading(word: str, following: str | None, long_option: str, short_letter: str) -> tuple[str | None, int]:
    if not word.startswith(SHORT_OPTION_PREFIX) or word == SHORT_OPTION_PREFIX:
        return None, 1
    if not word.startswith(LONG_OPTION_PREFIX):
        return _short_cluster_reading(word[len(SHORT_OPTION_PREFIX) :], following, short_letter)
    option_name, separator, inline_value = word.partition(OPTION_VALUE_SEPARATOR)
    if option_name == long_option:
        return (inline_value, 1) if separator else (following, OPTION_AND_VALUE_WIDTH)
    if separator or option_name in ALL_VALUELESS_LONG_CREATE_OPTIONS:
        return None, 1
    return None, OPTION_AND_VALUE_WIDTH


def _short_cluster_reading(all_letters: str, following: str | None, short_letter: str) -> tuple[str | None, int]:
    for each_index, each_letter in enumerate(all_letters):
        if each_letter in ALL_VALUELESS_SHORT_CREATE_LETTERS:
            continue
        inline_value = all_letters[each_index + 1 :].removeprefix(OPTION_VALUE_SEPARATOR)
        flag_value, width = (inline_value, 1) if inline_value else (following, OPTION_AND_VALUE_WIDTH)
        return (flag_value if each_letter == short_letter else None), width
    return None, 1


def _named_heads(all_arguments: list[str]) -> list[str]:
    all_heads: list[str] = []
    all_words = [unquoted_token(each_argument) for each_argument in all_arguments]
    for each_index, each_word in enumerate(all_words):
        following = all_words[each_index + 1] if each_index + 1 < len(all_words) else None
        head = _head_from_word(each_word, following)
        if head:
            all_heads.append(head)
    return all_heads


def _head_from_word(word: str, following: str | None) -> str | None:
    if word in (SHORT_HEAD_OPTION, LONG_HEAD_OPTION):
        return following
    if word.startswith(LONG_HEAD_OPTION + OPTION_VALUE_SEPARATOR):
        return word[len(LONG_HEAD_OPTION + OPTION_VALUE_SEPARATOR) :]
    if word.startswith(SHORT_HEAD_OPTION) and not word.startswith(LONG_OPTION_PREFIX):
        return word[len(SHORT_HEAD_OPTION) :].removeprefix(OPTION_VALUE_SEPARATOR)
    return None


def _floor_open_call(command: str, folder: str | None) -> ShellOpenCall | None:
    options_only = CREATE_TEXT_OPTION_PATTERN.sub(" ", command)
    create_match = GH_PR_CREATE_PATTERN.search(
        options_only
    ) or PULL_REQUEST_SCRIPT_CREATE_PATTERN.search(options_only)
    if not create_match:
        return None
    folder = _folder_after_changes(options_only[: create_match.start()], folder)
    rest = create_match["rest"]
    repo_match = REPO_OPTION_PATTERN.search(rest)
    head_match = HEAD_OPTION_PATTERN.search(rest)
    return ShellOpenCall(
        repository=(repo_match["owner"], repo_match["repo"]) if repo_match else None,
        branch=head_match["head"] if head_match else CURRENT_HEAD_REFERENCE,
        folder=folder,
    )


def _folder_after_changes(command_before_create: str, folder: str | None) -> str | None:
    all_changes = list(CHANGE_FOLDER_PATTERN.finditer(command_before_create))
    if not all_changes:
        return folder
    target = Path(os.path.expanduser(all_changes[-1]["folder"].strip("\"'")))
    if not target.is_absolute() and folder:
        target = Path(folder) / target
    return str(target)


def _run_git(all_arguments: list[str], folder: str | None) -> str | None:
    printed_text = child_stdout(
        ["git", *all_arguments], GIT_TIMEOUT_SECONDS, ReadSlice.FOLLOWUP, folder
    )
    return (printed_text or "").strip() or None


def _branch_commit(branch: str, folder: str | None) -> str | None:
    branch_name = branch.split(":", 1)[-1]
    all_references = (
        (branch_name,)
        if branch_name == CURRENT_HEAD_REFERENCE
        else (REMOTE_BRANCH_PREFIX + branch_name, branch_name)
    )
    for each_reference in all_references:
        commit = _run_git(
            ["rev-parse", "--verify", "--quiet", f"{each_reference}^{{commit}}"], folder
        )
        if commit:
            return commit
    return None


def _pushed_commit(owner: str, repo: str, branch: str) -> str | None:
    head_owner, separator, head_branch = branch.partition(":")
    if not separator:
        head_owner, head_branch = owner, branch
    if not head_owner or not repo or not head_branch:
        return None
    reference = REMOTE_BRANCH_REFERENCE_TEMPLATE.format(branch=head_branch)
    remote_url = GITHUB_REMOTE_URL_TEMPLATE.format(owner=head_owner, repo=repo)
    listing = _remote_listing(remote_url, reference)
    return _listed_commit(listing, reference) if listing is not None else None


def _remote_listing(remote_url: str, reference: str) -> str | None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as empty_folder:
        return child_stdout(
            ["git", "ls-remote", remote_url, reference],
            REMOTE_LOOKUP_TIMEOUT_SECONDS,
            ReadSlice.FOLLOWUP,
            empty_folder,
            {**os.environ, **ALL_NON_INTERACTIVE_GIT_SETTINGS},
        )


def _listed_commit(listing: str, reference: str) -> str | None:
    for each_line in listing.splitlines():
        commit, separator, listed_reference = each_line.partition(LS_REMOTE_FIELD_SEPARATOR)
        if separator and listed_reference == reference:
            return commit
    return None


def _origin_repository(folder: str | None) -> tuple[str, str]:
    origin_url = answer_once(
        (ORIGIN_URL_QUESTION, folder),
        lambda: _run_git(list(ALL_ORIGIN_URL_ARGUMENTS), folder),
    )
    origin_match = ORIGIN_URL_PATTERN.search(origin_url) if origin_url else None
    if not origin_match:
        return "", ""
    return origin_match["owner"], origin_match["repo"]
