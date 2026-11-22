"""Read each pull request open a PreToolUse payload asks for, and the head each opens with."""

from __future__ import annotations

import os
import shlex
import sys
import tempfile
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.followup_pr_dedupe import named_repository, prefix_repository, sets_gh_repository
from blocking.merge_review_gate_parts.create_folders import PlacedCreate, all_placed_creates
from blocking.merge_review_gate_parts.create_options import all_option_values
from blocking.merge_review_gate_parts.quoted_lines import (
    expansion_marked_line,
    holds_unquoted_expansion,
    quote_aware_lines,
)
from blocking.gate_run_reads import (
    ReadSlice,
    answer_once,
    child_stdout,
)
from hooks_constants.followup_pr_dedupe_constants import (
    GH_REPOSITORY_ENVIRONMENT_NAME,
    WINDOWS_EXECUTABLE_SUFFIX,
)
from hooks_constants.merge_review_gate_constants import (
    ALL_LONE_CREATE_SUBCOMMANDS,
    ALL_LONE_CREATE_REFUSED_CHARACTERS,
    ALL_LONE_LAUNCHER_FLAG_OPTIONS,
    ALL_MANAGED_LAUNCHER_PATH_PARTS,
    ALL_LONE_LAUNCHER_REQUIRED_OPTIONS,
    ALL_LONE_LAUNCHER_VALUE_OPTIONS,
    ALL_ORIGIN_PUSH_KEYS,
    ALL_PUSH_REMOTE_BRANCH_KEYS,
    BRANCH_SETTING_SECTION,
    LOCAL_BRANCH_REFERENCE_TEMPLATE,
    LONE_CREATE_UNQUOTED_REFUSED_CHARACTERS,
    LONE_LAUNCHER_CREATE_WORD,
    LONE_LAUNCHER_LEAD_WIDTH,
    LONE_LAUNCHER_OPTION_PREFIX,
    LONE_LAUNCHER_OPTION_VALUE_SEPARATOR,
    LONE_LAUNCHER_PYTHON_PATTERN,
    MANAGED_LAUNCHER_HOME_PREFIX_PATTERN,
    MERGE_SETTING_KEY,
    PUSH_DEFAULT_REMOTE_KEY,
    REMOTE_LISTING_QUESTION,
    SETTINGS_LISTING_QUESTION,
    UNKNOWN_PUSH_TARGET_CAUSE,
    ALL_ROOT_REPOSITORY_JOINED_PREFIXES,
    ALL_ROOT_REPOSITORY_OPTIONS,
    ALL_SHELL_EXPANSION_CHARACTERS,
    EXTENDED_GLOB_OPENER_PATTERN,
    FETCH_REFSPEC_JOIN,
    FETCH_REFSPEC_TEMPLATE,
    FETCH_SETTING_KEY,
    FETCH_SETTINGS_UNREAD_TEXT,
    LONE_CREATE_SUBCOMMAND_WIDTH,
    LOCAL_BRANCH_BEHIND_CAUSE,
    MAPPED_TRACKING_REFERENCE_CAUSE,
    MERGE_TREE_CLEAN_STATUS,
    MERGE_TREE_CONFLICTED_STATUS,
    MERGE_TREE_FIELD_SEPARATOR,
    MERGE_TREE_INPUT_TEMPLATE,
    NO_ORIGIN_FETCH_TEXT,
    OPTION_AND_VALUE_WIDTH,
    ORIGIN_FETCH_DEFAULT_REFSPEC,
    ORIGIN_TRACKING_NAMESPACE,
    REFSPEC_GLOB_CHARACTER,
    REFSPEC_SIDE_SEPARATOR,
    ALL_BRANCH_REFERENCE_PREFIXES,
    ALL_CHECKOUT_BRANCH_ARGUMENTS,
    ALL_STORED_HISTORY_GIT_SETTINGS,
    ALL_ANCESTRY_WALK_ARGUMENTS,
    ALL_OUTSIDE_BASE_ARGUMENTS,
    ALL_MERGE_TREE_ARGUMENTS,
    ALL_VERIFY_OBJECT_ARGUMENTS,
    COMMIT_OBJECT_TEMPLATE,
    TREE_OF_COMMIT_TEMPLATE,
    ALL_HOLDING_REFERENCE_ARGUMENTS,
    BASE_UNREAD_CAUSE,
    HEAD_UNREAD_CAUSE,
    BRANCHES_UNREAD_CAUSE,
    HEAD_OWNER_SEPARATOR,
    HELD_BY_OTHER_REFERENCE_CAUSE,
    INSIDE_BASE_CAUSE,
    NO_BASE_OR_BRANCH_CAUSE,
    NO_CONTENT_ADDED_CAUSE,
    NOT_LONE_CAUSE,
    ORIGIN_TRACKING_REFERENCE_TEMPLATE,
    OTHER_HOST_CAUSE,
    OTHER_REMOTE_CAUSE,
    SESSION_REPOSITORY_CAUSE,
    TOOL_NO_BASE_CAUSE,
    UNREAD_FLAG_CAUSE,
    ALL_NON_INTERACTIVE_GIT_SETTINGS,
    ALL_ORIGIN_URL_ARGUMENTS,
    ALL_SHELL_TOOL_NAMES,
    ALL_MERGE_BASE_READ_ARGUMENTS,
    ALL_SETTINGS_READ_ARGUMENTS,
    ORIGIN_REMOTE_NAME,
    REMOTE_SETTING_SECTION,
    RESOLVED_AS_BASE_VALUE,
    RESOLVED_REMOTE_SETTING_KEY,
    SETTING_NAME_END,
    SETTING_PART_SEPARATOR,
    SETTING_RECORD_END,
    BASE_BRANCH_FIELD,
    BASE_OPTION_MENTION_PATTERN,
    BASE_OPTION_PATTERN,
    BASE_SHORT_LETTER,
    CHANGE_FOLDER_PATTERN,
    CONTAINS_OPTION_TEMPLATE,
    CREATE_TEXT_OPTION_PATTERN,
    CREATE_TOOL_SUFFIX,
    CURRENT_HEAD_REFERENCE,
    CWD_FIELD,
    EXCLUDE_FROM_WALK_OPTION,
    GH_PR_CREATE_PATTERN,
    GH_HOST_VARIABLE,
    GH_PROGRAM_NAME,
    GITHUB_HOST,
    GITHUB_REMOTE_URL_TEMPLATE,
    GIT_TIMEOUT_SECONDS,
    HEAD_BRANCH_FIELD,
    HEAD_OPTION_PATTERN,
    HEAD_SHORT_LETTER,
    HOST_OWNER_AND_REPO_PART_COUNT,
    LONG_BASE_OPTION,
    LONG_HEAD_OPTION,
    LONG_REPOSITORY_OPTION,
    LS_REMOTE_FIELD_SEPARATOR,
    MAX_COUNT_OPTION_TEMPLATE,
    MERGE_BASE_SETTING_TEMPLATE,
    NO_CONTAINS_OPTION_TEMPLATE,
    OPEN_REPOSITORY_OPTION_PATTERN,
    OPEN_REVIEW_ANCESTOR_LIMIT,
    ORIGIN_URL_PATTERN,
    ORIGIN_URL_QUESTION,
    OWNER_AND_REPO_PART_COUNT,
    OWNER_FIELD,
    PULL_REQUEST_SCRIPT_CREATE_PATTERN,
    REMOTE_BRANCH_PREFIX,
    REMOTE_BRANCH_REFERENCE_TEMPLATE,
    REMOTE_LOOKUP_TIMEOUT_SECONDS,
    REPO_FIELD,
    REPOSITORY_OPTION_MENTION_PATTERN,
    REPOSITORY_PATH_SEPARATOR,
    REPOSITORY_SHORT_LETTER,
    TILDE_CHARACTER,
    UNREADABLE_WORD_MARK,
)
from hooks_constants.shell_command_segments import token_basename
from hooks_constants.shell_command_wrappers import segment_program_and_arguments


class WithheldCredit(Enum):
    """Why a recorded pass on an earlier commit of the branch gives the open no credit.

    Each value is the cause sentence of the deny reason::

        create beside a cd, or an unquoted parenthesis  -> NOT_LONE, run the create alone
        create tool call with no base                   -> TOOL_NO_BASE, set its base
        no --head, upstream under another branch name   -> UNKNOWN_PUSH_TARGET, name the head
        head branch GitHub did not answer for           -> HEAD_UNREAD, check the read
        base GitHub does not list                       -> BASE_UNREAD, names the base
        backup branch at the reviewed commit            -> HELD_BY_OTHER_REFERENCE, names it
        origin/<branch> under a hand-edited fetch       -> MAPPED_TRACKING_REFERENCE, names the refspec
        local <branch> left behind its pushed fixes     -> LOCAL_BRANCH_BEHIND, fast-forward it
        base already holds the reviewed commit          -> INSIDE_BASE, review again

    The first fourteen causes leave the pass in place, so the step they name
    needs no new review. The last two say the pass covered base work.
    """

    UNREAD_FLAG = UNREAD_FLAG_CAUSE
    OTHER_HOST = OTHER_HOST_CAUSE
    SESSION_REPOSITORY = SESSION_REPOSITORY_CAUSE
    NOT_LONE = NOT_LONE_CAUSE
    NO_BASE_OR_BRANCH = NO_BASE_OR_BRANCH_CAUSE
    OTHER_REMOTE = OTHER_REMOTE_CAUSE
    TOOL_NO_BASE = TOOL_NO_BASE_CAUSE
    UNKNOWN_PUSH_TARGET = UNKNOWN_PUSH_TARGET_CAUSE
    HEAD_UNREAD = HEAD_UNREAD_CAUSE
    BASE_UNREAD = BASE_UNREAD_CAUSE
    BRANCHES_UNREAD = BRANCHES_UNREAD_CAUSE
    HELD_BY_OTHER_REFERENCE = HELD_BY_OTHER_REFERENCE_CAUSE
    MAPPED_TRACKING_REFERENCE = MAPPED_TRACKING_REFERENCE_CAUSE
    LOCAL_BRANCH_BEHIND = LOCAL_BRANCH_BEHIND_CAUSE
    INSIDE_BASE = INSIDE_BASE_CAUSE
    NO_CONTENT_ADDED = NO_CONTENT_ADDED_CAUSE


@dataclass(frozen=True)
class OpenRequest:
    """One pull request a tool call asks to open.

    Attributes:
        owner: Repository owner, or empty when it could not be read.
        repo: Repository name, or empty when it could not be read.
        head: The commit the pull request would open with, or None.
        folder: The folder the open runs in, where git reads the head's history.
        branch: The branch name the open names, or the folder's checkout
            branch for ``HEAD``, or None when it could not be read.
        base: The base branch the open uses, or None for the repository's
            default branch.
        unknown_base_cause: Why the gate cannot tell which base the open
            uses, so no base is read and no earlier pass gets credit, or
            None when it can tell.
        base_setting_branch: The branch whose ``gh-merge-base`` setting gh
            reads when the open names no base, or None when none applies.
        head_owner: The owner a ``user:branch`` head names, or None when the
            head names no owner.
        is_plain_words: False when bash may split or change a create word, or
            expand a flag or its value, so the gate cannot tell the head, base or
            repository gh reads.
        is_head_read_on_github: False when GitHub did not answer the read of
            the head branch, so ``head`` is the clone's copy, which may not be
            the tip gh opens.
        is_head_settled: False when the command holds a step the gate does
            not count as settled, such as a ``git push``, a file write or a
            process substitution, before the create or beside it, so the
            head, branch or repository may change after the gate reads them.
        is_push_target_known: False when the create names no head and the
            git settings may send gh to another branch name or repository
            than the branch the gate read.
    """

    owner: str
    repo: str
    head: str | None
    folder: str | None = field(default=None, compare=False)
    branch: str | None = field(default=None, compare=False)
    base: str | None = field(default=None, compare=False)
    unknown_base_cause: WithheldCredit | None = field(default=None, compare=False)
    base_setting_branch: str | None = field(default=None, compare=False)
    head_owner: str | None = field(default=None, compare=False)
    is_plain_words: bool = field(default=True, compare=False)
    is_head_read_on_github: bool = field(default=True, compare=False)
    is_head_settled: bool = field(default=True, compare=False)
    is_push_target_known: bool = field(default=True, compare=False)

    @property
    def slug(self) -> str:
        """Return ``owner/repo``."""
        return f"{self.owner}/{self.repo}"

    @property
    def is_base_known(self) -> bool:
        """Return whether the gate can tell which base the open uses."""
        return self.unknown_base_cause is None


@dataclass(frozen=True)
class ToolOpenCall:
    """A create pull request tool call, before the gate reads its head.

    Attributes:
        owner: Repository owner the call names, or empty.
        repo: Repository name the call names, or empty.
        branch: The head branch the call names, or None.
        folder: The payload's folder, or None.
        base: The base branch the call names, or None.
    """

    owner: str
    repo: str
    branch: str | None
    folder: str | None
    base: str | None = None


@dataclass(frozen=True)
class ShellOpenCall:
    """One create in a shell command, before the gate reads its repository and head.

    Attributes:
        repository: The ``(owner, repo)`` its ``--repo``, root ``-R`` or ``GH_REPO`` names, or None to read ``origin``.
        branch: The branch its ``--head`` names, or ``HEAD``.
        folder: The folder in effect at the create, after each folder change before it.
        is_folder_followed: False when a folder change before it could not be followed,
            or when the create names no repository in a command that sets ``GH_REPO``.
        is_prefix_origin_check: True for the origin call a create gets when only a
            ``GH_REPO=`` prefix names its repository. Equal calls compare equal either way.
        base: The branch its ``--base`` names, or None when it names none.
        is_base_readable: False when the command names a host or a base flag
            the gate cannot read.
        is_lone_create: True when the whole command is this one gh create,
            so nothing in it can change the git config or the host gh reads.
            Only such a create gives an earlier pass credit.
        is_plain_words: False when bash may split or change a create word, or
            expand a flag or its value, before gh reads them.
        is_head_settled: False when a step in the command that the gate
            does not count as settled may move the head, branch or repository
            before gh opens it. Equal calls compare equal
            either way, and a command that gives two equal calls keeps False
            when either is False.
    """

    repository: tuple[str, str] | None
    branch: str
    folder: str | None
    is_folder_followed: bool = True
    is_prefix_origin_check: bool = field(default=False, compare=False)
    base: str | None = None
    is_base_readable: bool = field(default=True, compare=False)
    is_lone_create: bool = field(default=False, compare=False)
    is_plain_words: bool = True
    is_head_settled: bool = field(default=True, compare=False)


OpenCall = ToolOpenCall | ShellOpenCall


def open_calls_from(all_payload_fields: dict[str, object]) -> list[OpenCall]:
    """Return every pull request open a PreToolUse payload asks for, in command order.

    This reads the payload only. No git or GitHub read runs here::

        mcp__github__create_pull_request {owner, repo, head}   -> [ToolOpenCall]
        gh pr create --head a && cd x && pull_request.py create -> [ShellOpenCall a, ShellOpenCall HEAD in x]
        gh pr merge 12                                          -> []

    Each walked create gives one call per head it names, in its own folder.
    A create whose repository comes only from a ``GH_REPO=`` prefix also gives
    one origin call per head, since a wrapper such as ``env -u GH_REPO`` can
    drop the prefix before gh runs::

        GH_REPO=o/r env -u GH_REPO gh pr create -> [ShellOpenCall o/r, ShellOpenCall origin]

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

    Both kinds of call read their head branch from GitHub first::

        ToolOpenCall acme/tools, head feature pushed at abc123 -> OpenRequest(acme, tools, abc123)
        ShellOpenCall, no --repo, origin names acme/tools      -> OpenRequest(acme, tools, <GitHub tip of the checkout branch>)
        a read that failed or ran out of time                  -> that part empty, or head None
        ShellOpenCall whose folder change was not followed     -> head None, no read

    A fork head ``user:branch`` reads the repository of ``user``. A branch
    GitHub does not list resolves in the call's folder as ``origin/<branch>``
    first. A tool call whose GitHub read fails resolves there too, while a
    shell create whose GitHub read fails gets no head.

    Args:
        call: One open from ``open_calls_from``.

    Returns:
        The open request with the commit it would open with.
    """
    if isinstance(call, ToolOpenCall):
        return _tool_open_request(call)
    return _shell_open_request(call)


def _tool_open_request(call: ToolOpenCall) -> OpenRequest:
    branch = _branch_name(call.branch, call.folder) if call.branch else None
    settled_head = (
        _settled_head(call.branch, branch, call.owner, call.repo, call.folder)
        if call.branch
        else _SettledHead(None, False)
    )
    return OpenRequest(
        owner=call.owner,
        repo=call.repo,
        head=settled_head.commit,
        folder=call.folder,
        branch=branch,
        base=call.base,
        unknown_base_cause=None if call.base is not None else WithheldCredit.TOOL_NO_BASE,
        head_owner=_head_owner(call.branch) if call.branch else None,
        is_head_read_on_github=settled_head.is_read_on_github,
    )


def _head_owner(branch: str) -> str | None:
    head_owner, separator, _branch = branch.partition(HEAD_OWNER_SEPARATOR)
    return head_owner if separator else None


def _shell_open_request(call: ShellOpenCall) -> OpenRequest:
    if not call.is_folder_followed:
        owner, repo = call.repository or ("", "")
        return OpenRequest(
            owner=owner,
            repo=repo,
            head=None,
            is_plain_words=call.is_plain_words,
            is_head_settled=call.is_head_settled,
        )
    owner, repo = call.repository or _origin_repository(call.folder)
    branch = _branch_name(call.branch, call.folder)
    settled_head = _settled_head(call.branch, branch, owner, repo, call.folder)
    return OpenRequest(
        owner=owner,
        repo=repo,
        head=settled_head.commit,
        folder=call.folder,
        branch=branch,
        base=call.base,
        unknown_base_cause=_unknown_base_cause(call, owner, repo, branch),
        base_setting_branch=branch if call.base is None else None,
        head_owner=_head_owner(call.branch),
        is_plain_words=call.is_plain_words,
        is_head_read_on_github=settled_head.is_read_on_github,
        is_head_settled=call.is_head_settled,
        is_push_target_known=_is_push_target_known(call, owner, repo, branch),
    )


@dataclass(frozen=True)
class _SettledHead:
    """The commit an open uses, and whether GitHub answered the read of its head branch."""

    commit: str | None
    is_read_on_github: bool


def _settled_head(
    branch: str, branch_name: str | None, owner: str, repo: str, folder: str | None
) -> _SettledHead:
    """Return the commit an open uses, which is the tip GitHub holds for its head branch.

    gh and the create tool send the branch name, and GitHub opens the pull
    request at its own tip, whatever the clone's ``origin/<branch>`` holds::

        GitHub lists feature at abc123, origin/feature at def456 -> abc123, read
        GitHub lists no such branch                               -> origin/<branch>, then <branch>, read
        the read fails, head feature                              -> origin/<branch>, then <branch>, not read
        the read fails, fork head someone:feature                 -> None, not read
        no branch name, owner or repository                       -> the local commit, not read

    A fork head ``user:branch`` reads the repository of ``user``, and its
    branch is never read from origin while that read fails.
    """
    head_owner = _head_owner(branch)
    if not branch_name or not owner or not repo:
        return _SettledHead(_branch_commit(branch, folder), False)
    pushed_head = _pushed_head(head_owner or owner, repo, branch_name)
    if pushed_head.commit:
        return _SettledHead(pushed_head.commit, True)
    if not pushed_head.is_read and head_owner:
        return _SettledHead(None, False)
    return _SettledHead(_branch_commit(branch, folder), pushed_head.is_read)


def _unknown_base_cause(
    call: ShellOpenCall, owner: str, repo: str, branch: str | None
) -> WithheldCredit | None:
    """Return the first reason the gate cannot tell which base a shell create uses.

    ::

        gh pr create --fill -R ghe.example.com/acme/tools -> UNREAD_FLAG
        GH_HOST=ghe.example.com in the gate's environment -> OTHER_HOST
        GH_REPO=evil/tools in the gate's environment      -> SESSION_REPOSITORY
        cd . && gh pr create --fill                       -> NOT_LONE
        no --base and no checkout branch                  -> NO_BASE_OR_BRANCH
        no --repo, and a second remote in the folder      -> OTHER_REMOTE
        gh pr create --fill --base main, origin alone     -> None

    The checks run in that order, and the remote read runs only when every
    check before it passed.
    """
    if not call.is_base_readable:
        return WithheldCredit.UNREAD_FLAG
    if _is_other_host(os.environ.get(GH_HOST_VARIABLE)):
        return WithheldCredit.OTHER_HOST
    if _names_another_repository(os.environ.get(GH_REPOSITORY_ENVIRONMENT_NAME), owner, repo):
        return WithheldCredit.SESSION_REPOSITORY
    if not call.is_lone_create:
        return WithheldCredit.NOT_LONE
    if call.base is None and branch is None:
        return WithheldCredit.NO_BASE_OR_BRANCH
    if call.repository is None and _resolves_to_another_remote(call.folder):
        return WithheldCredit.OTHER_REMOTE
    return None


def _resolves_to_another_remote(folder: str | None) -> bool:
    """Return whether gh may open in a repository other than origin.

    A create with no ``--repo`` opens in the repository gh picks among the
    remotes, and ``gh repo set-default`` records that pick in a
    ``gh-resolved`` setting::

        origin alone, no gh-resolved setting          -> False
        remote.origin.gh-resolved = base              -> False
        remote.origin.gh-resolved = upstream/tools    -> True
        a second remote, with or without a setting    -> True
        the settings read fails or runs out           -> True

    Remote names are compared as written, since git keeps their letter case.
    """
    listing = _settings_listing(folder)
    if listing is None:
        return True
    for each_setting in listing.split(SETTING_RECORD_END):
        name, _, setting_value = each_setting.partition(SETTING_NAME_END)
        section, _, remainder = name.partition(SETTING_PART_SEPARATOR)
        remote_name, _, key = remainder.rpartition(SETTING_PART_SEPARATOR)
        if section.lower() != REMOTE_SETTING_SECTION or not remote_name:
            continue
        if remote_name != ORIGIN_REMOTE_NAME:
            return True
        if key.lower() == RESOLVED_REMOTE_SETTING_KEY and setting_value != RESOLVED_AS_BASE_VALUE:
            return True
    return False


def _settings_listing(folder: str | None) -> str | None:
    return answer_once(
        (SETTINGS_LISTING_QUESTION, folder),
        lambda: child_stdout(
            ["git", *ALL_SETTINGS_READ_ARGUMENTS], GIT_TIMEOUT_SECONDS, ReadSlice.FOLLOWUP, folder
        ),
    )


def _is_push_target_known(call: ShellOpenCall, owner: str, repo: str, branch: str | None) -> bool:
    """Return whether gh opens the checkout branch under the name and repository the gate read.

    A create with no ``--head`` sends the branch gh finds from the git
    settings, which may differ from the checkout branch's own name::

        --head feature                                -> True, gh sends that name
        no --head, no upstream or push setting        -> True
        branch.feature.merge = refs/heads/other       -> False
        branch.feature.remote = upstream              -> False
        remote.origin.pushurl set                     -> False
        --repo acme/other while origin is acme/tools  -> False
        the settings read fails or runs out           -> False

    A detached checkout has no branch, so gh opens no branch the gate guessed.
    """
    if call.branch != CURRENT_HEAD_REFERENCE or branch is None:
        return True
    if call.repository is not None:
        origin_owner, origin_repo = _origin_repository(call.folder)
        if (origin_owner.casefold(), origin_repo.casefold()) != (owner.casefold(), repo.casefold()):
            return False
    listing = _settings_listing(call.folder)
    if listing is None:
        return False
    return not any(
        _moves_push_target(each_setting, branch) for each_setting in listing.split(SETTING_RECORD_END)
    )


def _moves_push_target(setting: str, branch: str) -> bool:
    """Return whether one git setting may send gh to another branch name or remote.

    ::

        branch.feature.merge=refs/heads/feature       -> False
        branch.feature.merge=refs/heads/other         -> True
        branch.feature.pushremote=fork                -> True
        remote.pushdefault=origin                     -> False
        remote.origin.push=refs/heads/a:refs/heads/b  -> True
    """
    name, _, setting_value = setting.partition(SETTING_NAME_END)
    section, _, remainder = name.partition(SETTING_PART_SEPARATOR)
    subsection, _, key = remainder.rpartition(SETTING_PART_SEPARATOR)
    section, key = section.lower(), key.lower()
    if section == BRANCH_SETTING_SECTION and subsection == branch:
        if key == MERGE_SETTING_KEY:
            return setting_value != LOCAL_BRANCH_REFERENCE_TEMPLATE.format(branch=branch)
        return key in ALL_PUSH_REMOTE_BRANCH_KEYS and setting_value != ORIGIN_REMOTE_NAME
    if section != REMOTE_SETTING_SECTION:
        return False
    if not subsection and key == PUSH_DEFAULT_REMOTE_KEY:
        return setting_value != ORIGIN_REMOTE_NAME
    return subsection == ORIGIN_REMOTE_NAME and key in ALL_ORIGIN_PUSH_KEYS


def _is_other_host(host: str | None) -> bool:
    return bool(host) and str(host).lower() != GITHUB_HOST


def _names_another_repository(session_repository: str | None, owner: str, repo: str) -> bool:
    """Return whether a ``GH_REPO`` value names a repository other than the open's.

    gh reads ``[HOST/]OWNER/REPO``, so a github.com host prefix names the same repository::

        None, "acme/tools", "GitHub.com/acme/tools"   -> False, for acme/tools
        "evil/tools", "ghe.example.com/acme/tools"    -> True
    """
    if not session_repository:
        return False
    all_parts = session_repository.lower().split(REPOSITORY_PATH_SEPARATOR)
    if len(all_parts) == HOST_OWNER_AND_REPO_PART_COUNT and all_parts[0] == GITHUB_HOST:
        all_parts = all_parts[1:]
    return all_parts != [owner.lower(), repo.lower()]


def _branch_name(branch: str, folder: str | None) -> str | None:
    branch_name = branch.split(":", 1)[-1]
    if branch_name != CURRENT_HEAD_REFERENCE:
        return branch_name
    return _run_git(list(ALL_CHECKOUT_BRANCH_ARGUMENTS), folder)


def first_parent_ancestors(head: str, folder: str | None) -> tuple[str, ...]:
    """Return the commits before a head along its first parents, newest first.

    Fix commits on a branch sit on top of the head a review pass saw, so that
    head is among them. A side branch merged in is left out, since only first
    parents are followed::

        reviewed abc123, fix def456, fix 789abc; head 789abc -> (def456, abc123, ...)
        a head the folder has no history for                 -> ()

    The walk stops after OPEN_REVIEW_ANCESTOR_LIMIT commits, and it reads the
    parents git stores, never a replace ref or a grafts file.

    Args:
        head: The commit the pull request would open with.
        folder: The folder git reads the history in.

    Returns:
        The full commit names, the head itself left out.
    """
    listing = _stored_history_read(
        [
            *ALL_ANCESTRY_WALK_ARGUMENTS,
            MAX_COUNT_OPTION_TEMPLATE.format(count=OPEN_REVIEW_ANCESTOR_LIMIT + 1),
            head,
        ],
        folder,
    )
    return tuple(listing.split()[1:]) if listing else ()


def _stored_history_read(all_arguments: list[str], folder: str | None) -> str | None:
    return child_stdout(
        ["git", *all_arguments],
        GIT_TIMEOUT_SECONDS,
        ReadSlice.FOLLOWUP,
        folder,
        {**os.environ, **ALL_STORED_HISTORY_GIT_SETTINGS},
    )


def _stored_history_read_of_input(all_arguments: list[str], folder: str | None, standard_input: str) -> str | None:
    return child_stdout(
        ["git", *all_arguments],
        GIT_TIMEOUT_SECONDS,
        ReadSlice.FOLLOWUP,
        folder,
        {**os.environ, **ALL_STORED_HISTORY_GIT_SETTINGS},
        standard_input,
    )


def branches_holding_without(commit: str, head: str, folder: str | None) -> tuple[str, ...] | None:
    """Return the local and remote branches that hold a commit and lack the head.

    A review pass on the branch's own earlier commit covers the fix commits
    on top of it. A commit some other branch holds without the head, such as
    a commit of ``main`` or of the branch this one stacks on, is not this
    branch's review::

        feature holds reviewed abc123 and head def456      -> ()
        second stacks on feature at abc123, head def456    -> ("refs/heads/feature",)
        origin/feature still at abc123, fix def456 local   -> ("refs/remotes/origin/feature",)
        a read that fails or runs out of time              -> None

    Replace refs and grafts are not read. The caller decides which of the
    branches is the open's own branch on origin, with
    ``foreign_origin_fetch_refspec`` telling whether that name can hold
    another branch.

    Args:
        commit: The commit a review pass saw.
        head: The commit the pull request would open with.
        folder: The folder git reads the branches in.

    Returns:
        The full reference names, or None when the read failed.
    """
    listing = _stored_history_read(
        [
            *ALL_HOLDING_REFERENCE_ARGUMENTS,
            CONTAINS_OPTION_TEMPLATE.format(commit=commit),
            NO_CONTAINS_OPTION_TEMPLATE.format(commit=head),
            *ALL_BRANCH_REFERENCE_PREFIXES,
        ],
        folder,
    )
    return None if listing is None else tuple(listing.split())


def own_tracking_reference(request: OpenRequest) -> str | None:
    """Return the origin remote-tracking branch of the branch the open names.

    That reference is the same branch, as fetched or pushed before the fix
    commits, so it is not another line::

        head feature, origin acme/tools, open on acme/tools          -> "refs/remotes/origin/feature"
        head someone:feature, origin acme/tools, open on acme/tools -> None
        head feature, origin names another repository or none       -> None
        no branch                                                    -> None

    Owner and repository names compare in any letter case, as on GitHub.

    Args:
        request: The open the tool call asks for.

    Returns:
        The full reference name, or None when origin is not the head's repository.
    """
    if not request.branch:
        return None
    head_owner = request.head_owner or request.owner
    origin_owner, origin_repo = _origin_repository(request.folder)
    if (origin_owner.casefold(), origin_repo.casefold()) != (
        head_owner.casefold(),
        request.repo.casefold(),
    ):
        return None
    return ORIGIN_TRACKING_REFERENCE_TEMPLATE.format(branch=request.branch)


def foreign_origin_fetch_refspec(folder: str | None) -> str | None:
    """Return the fetch settings that could write another branch onto an ``origin/<branch>`` name.

    The branch's own ``refs/remotes/origin/<branch>`` counts as the branch
    only while the clone default writes it::

        remote.origin.fetch = +refs/heads/*:refs/remotes/origin/*, alone   -> None
        a second origin refspec, or a changed one                         -> every origin refspec
        remote.upstream.fetch = +refs/heads/*:refs/remotes/*               -> that refspec
        remote.upstream.fetch = refs/heads/x:refs/remotes/origin/feature  -> that refspec
        no remote.origin.fetch                                            -> NO_ORIGIN_FETCH_TEXT
        the settings read fails or runs out                               -> FETCH_SETTINGS_UNREAD_TEXT

    Args:
        folder: The folder git reads the settings in.

    Returns:
        The refspecs in backticks, or a sentence naming why none can be trusted,
        or None when only the clone default writes under ``refs/remotes/origin/``.
    """
    listing = _settings_listing(folder)
    if listing is None:
        return FETCH_SETTINGS_UNREAD_TEXT
    all_origin_refspecs, all_foreign_refspecs = _fetch_refspecs(listing)
    if all_origin_refspecs == [ORIGIN_FETCH_DEFAULT_REFSPEC] and not all_foreign_refspecs:
        return None
    if not all_origin_refspecs:
        return NO_ORIGIN_FETCH_TEXT
    all_named_refspecs = all_foreign_refspecs or all_origin_refspecs
    return FETCH_REFSPEC_JOIN.join(
        FETCH_REFSPEC_TEMPLATE.format(refspec=each_refspec) for each_refspec in all_named_refspecs
    )


def _fetch_refspecs(listing: str) -> tuple[list[str], list[str]]:
    all_fetch_settings = [
        each_pair
        for each_setting in listing.split(SETTING_RECORD_END)
        if (each_pair := _fetch_setting(each_setting)) is not None
    ]
    all_origin_refspecs = [
        each_refspec for each_remote, each_refspec in all_fetch_settings if each_remote == ORIGIN_REMOTE_NAME
    ]
    all_foreign_refspecs = [
        each_refspec
        for each_remote, each_refspec in all_fetch_settings
        if each_remote != ORIGIN_REMOTE_NAME and _writes_under_origin_tracking(each_refspec)
    ]
    return all_origin_refspecs, all_foreign_refspecs


def _fetch_setting(setting: str) -> tuple[str, str] | None:
    name, _, setting_value = setting.partition(SETTING_NAME_END)
    section, _, remainder = name.partition(SETTING_PART_SEPARATOR)
    remote_name, _, key = remainder.rpartition(SETTING_PART_SEPARATOR)
    if section.lower() != REMOTE_SETTING_SECTION or key.lower() != FETCH_SETTING_KEY:
        return None
    return remote_name, setting_value


def _writes_under_origin_tracking(refspec: str) -> bool:
    """Return whether a fetch refspec's destination can name a ref under ``refs/remotes/origin/``.

    ::

        +refs/heads/*:refs/remotes/upstream/*    -> False
        +refs/heads/*:refs/remotes/*             -> True, a branch named origin/x lands there
        refs/heads/x:refs/remotes/origin/feature -> True
        ^refs/heads/skip                         -> False, no destination
    """
    _source, separator, destination = refspec.partition(REFSPEC_SIDE_SEPARATOR)
    if not separator:
        return False
    fixed_part = destination.split(REFSPEC_GLOB_CHARACTER, 1)[0]
    if REFSPEC_GLOB_CHARACTER in destination:
        return ORIGIN_TRACKING_NAMESPACE.startswith(fixed_part) or fixed_part.startswith(
            ORIGIN_TRACKING_NAMESPACE
        )
    return destination.startswith(ORIGIN_TRACKING_NAMESPACE)


def base_tip(request: OpenRequest) -> str | None:
    """Return the commit the pull request's base branch holds on GitHub.

    The base is read from the repository the open targets, never from a
    local ref, so a clone that lacks the base branch still reads it::

        base main, GitHub main at abc123        -> abc123
        no base named, gh-merge-base stack      -> GitHub stack
        no base named, no setting, default at def456 -> def456
        a base GitHub does not list, or a read that fails -> None
        a base the gate could not tell                    -> None, no read

    Args:
        request: The open the tool call asks for.

    Returns:
        The full commit name, or None when the base could not be read.
    """
    if not request.owner or not request.repo or not request.is_base_known:
        return None
    base = request.base
    if base is None and request.base_setting_branch is not None:
        merge_base = _merge_base_setting(request.base_setting_branch, request.folder)
        if merge_base is None:
            return None
        base = merge_base or None
    reference = (
        REMOTE_BRANCH_REFERENCE_TEMPLATE.format(branch=base) if base else CURRENT_HEAD_REFERENCE
    )
    remote_url = GITHUB_REMOTE_URL_TEMPLATE.format(owner=request.owner, repo=request.repo)
    listing = _remote_listing(remote_url, reference)
    return _listed_commit(listing, reference) if listing is not None else None


def _merge_base_setting(branch: str, folder: str | None) -> str | None:
    """Return the ``gh-merge-base`` setting gh reads for a branch.

    ::

        branch.feature.gh-merge-base = stack -> "stack"
        no setting                           -> ""
        a read that fails or runs out of time -> None
    """
    printed_text = child_stdout(
        ["git", *ALL_MERGE_BASE_READ_ARGUMENTS, MERGE_BASE_SETTING_TEMPLATE.format(branch=branch)],
        GIT_TIMEOUT_SECONDS,
        ReadSlice.FOLLOWUP,
        folder,
    )
    return printed_text.rstrip("\r\n") if printed_text is not None else None


def is_outside_base(commit: str, base_commit: str, folder: str | None) -> bool:
    """Return whether a commit is missing from the history of the base.

    A commit the base already holds is base work, so a review pass on it says
    nothing about the branch's own commits::

        feature commit abc123, base main at def456 below it -> True
        base main at abc123 itself, or above it             -> False
        a base commit the folder has no history for         -> False

    Replace refs and grafts are not read. A read that fails or runs out of
    time counts as inside the base, so the open is denied.

    Args:
        commit: The commit a review pass saw.
        base_commit: The commit the base branch holds, from ``base_tip``.
        folder: The folder git reads the history in.

    Returns:
        True when ``commit`` is not reachable from ``base_commit``.
    """
    listing = _stored_history_read(
        [*ALL_OUTSIDE_BASE_ARGUMENTS, commit, EXCLUDE_FROM_WALK_OPTION, base_commit],
        folder,
    )
    return bool(listing and listing.strip())


def adds_content_to_base(commit: str, base_commit: str, folder: str | None) -> bool:
    """Return whether merging a commit into the base would change the base's files.

    A base that squashed a branch in holds the branch's content without its
    commits, so a pass on that content says nothing about later work::

        feature commit adds feature.txt, base lacks it      -> True
        the merge conflicts with a base that moved on        -> True
        base holds a squash of the commit                    -> False
        a read fails or runs out                             -> False

    A conflict means the base holds the commit's lines in another form, so
    the commit still adds content. A base that squashed the commit and then
    edited the same lines also conflicts, and so gets credit: the pull request
    then conflicts with its base on GitHub, and its merge still needs the
    full review loop. The merge runs with ``git merge-tree --stdin
    --write-tree``, which reports a conflict in its output and not in its
    exit status, stores the merged tree as loose objects and moves no ref.

    Args:
        commit: The commit a review pass saw.
        base_commit: The commit the base branch holds, from ``base_tip``.
        folder: The folder git reads the history in.

    Returns:
        True when the merged tree differs from the base commit's tree.
    """
    merged_listing = _stored_history_read_of_input(
        list(ALL_MERGE_TREE_ARGUMENTS),
        folder,
        MERGE_TREE_INPUT_TEMPLATE.format(base_commit=base_commit, commit=commit),
    )
    base_tree = _stored_history_read(
        [*ALL_VERIFY_OBJECT_ARGUMENTS, TREE_OF_COMMIT_TEMPLATE.format(commit=base_commit)], folder
    )
    if not merged_listing or not base_tree or not base_tree.strip():
        return False
    merge_status, _, rest = merged_listing.partition(MERGE_TREE_FIELD_SEPARATOR)
    merged_tree = rest.partition(MERGE_TREE_FIELD_SEPARATOR)[0].strip()
    if merge_status == MERGE_TREE_CONFLICTED_STATUS:
        return True
    return merge_status == MERGE_TREE_CLEAN_STATUS and bool(merged_tree) and merged_tree != base_tree.strip()


def is_stored_locally(commit: str, folder: str | None) -> bool:
    """Return whether the folder's git stores a commit.

    ::

        a commit the clone fetched                 -> True
        a commit GitHub holds that was not fetched -> False

    Args:
        commit: The full commit name.
        folder: The folder git reads in.

    Returns:
        True when git can read the commit, False when it cannot or the read fails.
    """
    return bool(
        _stored_history_read(
            [*ALL_VERIFY_OBJECT_ARGUMENTS, COMMIT_OBJECT_TEMPLATE.format(commit=commit)], folder
        )
    )


def _tool_open_call(all_tool_input: dict[object, object], folder: str | None) -> ToolOpenCall:
    branch = all_tool_input.get(HEAD_BRANCH_FIELD)
    base = all_tool_input.get(BASE_BRANCH_FIELD)
    return ToolOpenCall(
        owner=str(all_tool_input.get(OWNER_FIELD, "")),
        repo=str(all_tool_input.get(REPO_FIELD, "")),
        branch=branch if isinstance(branch, str) and branch else None,
        folder=folder,
        base=base if isinstance(base, str) and base else None,
    )


def _shell_open_calls(command: str, folder: str | None) -> list[OpenCall]:
    all_calls: list[ShellOpenCall] = []
    is_gh_repository_set = sets_gh_repository(command)
    is_lone_create = _is_lone_create(command)
    all_creates = all_placed_creates(command, folder)
    for each_create in all_creates:
        all_calls.extend(
            replace(
                each_call,
                is_plain_words=each_create.is_plain_words,
                is_head_settled=each_create.is_head_settled,
            )
            for each_call in _placed_open_calls(each_create, is_gh_repository_set, is_lone_create)
        )
    floor_call = _floor_open_call(command, folder, is_lone_create)
    if floor_call is not None:
        is_first_create_settled = bool(all_creates) and all_creates[0].is_head_settled
        all_calls.append(replace(floor_call, is_head_settled=is_lone_create or is_first_create_settled))
    is_settled_by_call: dict[ShellOpenCall, bool] = {}
    for each_call in all_calls:
        is_settled_by_call[each_call] = is_settled_by_call.get(each_call, True) and each_call.is_head_settled
    return [
        replace(each_call, is_head_settled=each_is_settled)
        for each_call, each_is_settled in is_settled_by_call.items()
    ]


def _is_lone_create(command: str) -> bool:
    """Return whether a whole shell command is one plain ``gh pr create`` or one plain launcher create.

    gh reads the head branch's ``gh-merge-base`` setting when it runs. Any
    other word in the command can write that setting or the git config gh
    reads first, so only a lone create is read::

        gh pr create --fill                                  -> True
        gh -R acme/tools pr create --fill                    -> True
        gh pr create --title "Fix edge cases (Windows)"      -> True, the parentheses are quoted
        gh pr create --title '[WIP] {x}?'                    -> True, quoted
        python3 ~/.agents/skills/pull-request/scripts/pull_request.py create --repo o/r --base main --head f -> True
        python3 /x/pull_request.py create --repo o/r --base main --head f -> False, not the managed launcher
        git config "branch.x.gh-merge""-base" y && gh pr create -> False
        LANG=C gh pr create --fill                           -> False
        gh pr create --fill > out.txt                        -> False
        gh pr create --title "$(date)"                       -> False
        gh pr create --fill # ; git config ...               -> False
        gh pr create --title a&b                             -> False
        python3 ~/x/pull_request.py create ...               -> False, the ~ is outside quotes

    A ``$``, backtick or line break anywhere makes the command not lone. The
    rest is split as POSIX shell words, and each of ``( ) ; < > | & # { } *
    ? [ ~`` outside quotes and not escaped comes back as a word of its own,
    which makes the command not lone. A word made only of those characters
    inside quotes, such as ``"()"``, makes it not lone too. A split that fails also makes it not lone.
    One root ``-R``/``--repo`` value may come between ``gh`` and ``pr``. The
    launcher is the managed script at ``~/.agents/skills/pull-request/scripts/pull_request.py``,
    whose leading ``~`` or ``$HOME`` reads as the home folder before the split.
    It runs as its own program or after ``python`` or ``python3``, and
    names each of ``--repo``, ``--base`` and ``--head`` once, each with a
    value that is not empty and does not start with ``-``. Its other words
    are only ``--title``, ``--body-file`` and their values, and ``--draft``.

    Args:
        command: The shell command text.

    Returns:
        True when the command is one create and nothing else.
    """
    all_words = _lone_command_words(_with_managed_launcher_home(command))
    if not all_words:
        return False
    program = token_basename(all_words[0]).removesuffix(WINDOWS_EXECUTABLE_SUFFIX)
    if program != GH_PROGRAM_NAME:
        return _is_lone_launcher_create(program, all_words)
    subcommand_start = 1 + _root_repository_width(all_words[1:])
    all_subcommand_words = tuple(all_words[subcommand_start : subcommand_start + LONE_CREATE_SUBCOMMAND_WIDTH])
    return all_subcommand_words in ALL_LONE_CREATE_SUBCOMMANDS


def _lone_command_words(command: str) -> list[str] | None:
    """Return the shell words of a command, or None when one of them is not a plain word.

    ::

        gh pr create --title "a (b)"   -> ["gh", "pr", "create", "--title", "a (b)"]
        gh pr create --fill; x         -> None, the ; is a word of its own
        gh pr create --title "$(x)"    -> None
    """
    if not ALL_LONE_CREATE_REFUSED_CHARACTERS.isdisjoint(command):
        return None
    lexer = shlex.shlex(command, posix=True, punctuation_chars=LONE_CREATE_UNQUOTED_REFUSED_CHARACTERS)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        all_words = list(lexer)
    except ValueError:
        return None
    is_each_word_plain = all(
        not each_word or not set(each_word) <= set(LONE_CREATE_UNQUOTED_REFUSED_CHARACTERS)
        for each_word in all_words
    )
    return all_words if is_each_word_plain else None


def _with_managed_launcher_home(command: str) -> str:
    """Return the command with a home prefix on the managed launcher path written out as the home folder.

    Bash turns a leading ``~`` or ``$HOME`` into the home folder, and the
    gate runs with the same home::

        python3 ~/.agents/skills/pull-request/scripts/pull_request.py create ...
            -> python3 /home/u/.agents/skills/pull-request/scripts/pull_request.py create ...
        $HOME/.agents/skills/pull-request/scripts/pull_request.py create ... -> /home/u/.agents/...
        python3 ~/x/pull_request.py create ..., ~other/.agents/..., '~'/.agents/... -> unchanged

    Only the script word of the launcher changes, so any other ``~`` or
    ``$`` still makes the command not lone.
    """
    home_folder = shlex.quote(Path.home().as_posix())
    return MANAGED_LAUNCHER_HOME_PREFIX_PATTERN.sub(
        lambda each_match: each_match["lead"] + home_folder, command, count=1
    )


def _is_managed_launcher(script_word: str) -> bool:
    """Return whether a script word names the launcher at ``~/.agents/skills/pull-request/scripts/pull_request.py``.

    ::

        /home/u/.agents/skills/pull-request/scripts/pull_request.py           -> True
        /home/u/.agents/skills/pull-request/scripts/../scripts/pull_request.py -> True
        pull_request.py, ./pull_request.py, scripts/pull_request.py            -> False
        /tmp/x/pull_request.py, /repo/.agents/skills/pull-request/...          -> False

    A relative word is never the launcher, since the gate cannot tell which
    folder bash runs it from. Both paths resolve links and letter case
    before the compare.
    """
    if not os.path.isabs(script_word):
        return False
    managed_launcher = Path.home().joinpath(*ALL_MANAGED_LAUNCHER_PATH_PARTS)
    return os.path.normcase(os.path.realpath(script_word)) == os.path.normcase(
        os.path.realpath(managed_launcher)
    )


def _is_lone_launcher_create(program: str, all_words: list[str]) -> bool:
    """Return whether shell words run the managed ``pull_request.py create`` launcher with one repository, base and head.

    ::

        /home/u/.agents/skills/pull-request/scripts/pull_request.py create --repo o/r --base main --head f -> True
        python3 /home/u/.agents/.../pull_request.py create --repo=o/r --base main --head f            -> True
        python3 /x/pull_request.py create ..., ./pull_request.py create ...                           -> False
        python3 -X utf8 /home/u/.agents/.../pull_request.py create ...                                -> False
        /home/u/.agents/.../pull_request.py create --repo o/r --base main                             -> False
        ... --head f --head g, --head=, --title --head                                                -> False

    The script word must be the managed launcher, so a different script
    with the same name cannot change git config or open elsewhere and still
    count. The words after ``create`` must read as the launcher's own
    options, each in an option position, so the head and repository the
    gate reads are the ones the launcher hands to gh.
    """
    script_start = 1 if LONE_LAUNCHER_PYTHON_PATTERN.fullmatch(program) else 0
    all_launcher_words = all_words[script_start:]
    if len(all_launcher_words) < LONE_LAUNCHER_LEAD_WIDTH:
        return False
    script_word, action_word = all_launcher_words[:LONE_LAUNCHER_LEAD_WIDTH]
    if action_word != LONE_LAUNCHER_CREATE_WORD or not _is_managed_launcher(script_word):
        return False
    all_values_by_option = _launcher_option_values(all_launcher_words[LONE_LAUNCHER_LEAD_WIDTH:])
    if all_values_by_option is None:
        return False
    return all(
        len(all_values_by_option.get(each_option, [])) == 1 for each_option in ALL_LONE_LAUNCHER_REQUIRED_OPTIONS
    )


def _launcher_option_values(all_option_words: list[str]) -> dict[str, list[str]] | None:
    """Read the launcher's create options, or None when a word is not one of them with a plain value.

    ::

        ["--repo", "o/r", "--head=f", "--draft"] -> {"--repo": ["o/r"], "--head": ["f"]}
        ["--head", "f", "--head", "g"]           -> {"--head": ["f", "g"]}
        ["--head="], ["--head"], ["--fill"]      -> None
        ["--title", "--head"], ["--", "x"]       -> None

    A value that is empty or starts with ``-`` also gives None, since the
    launcher's parser either refuses it or reads it as another option.
    """
    all_values_by_option: dict[str, list[str]] = {}
    index = 0
    while index < len(all_option_words):
        option, separator, inline_value = all_option_words[index].partition(LONE_LAUNCHER_OPTION_VALUE_SEPARATOR)
        if option in ALL_LONE_LAUNCHER_FLAG_OPTIONS and not separator:
            index += 1
            continue
        if option not in ALL_LONE_LAUNCHER_VALUE_OPTIONS:
            return None
        if separator:
            option_value = inline_value
            index += 1
        else:
            option_value = all_option_words[index + 1] if index + 1 < len(all_option_words) else ""
            index += OPTION_AND_VALUE_WIDTH
        if not option_value or option_value.startswith(LONE_LAUNCHER_OPTION_PREFIX):
            return None
        all_values_by_option.setdefault(option, []).append(option_value)
    return all_values_by_option


def _root_repository_width(all_words_after_program: list[str]) -> int:
    """Return how many words a root ``-R``/``--repo`` before ``pr`` takes.

    ::

        ["-R", "o/r", "pr", "create"]  -> 2
        ["--repo=o/r", "pr", "create"] -> 1
        ["-Ro/r", "pr", "create"]      -> 1
        ["pr", "create"]               -> 0
    """
    first_word = all_words_after_program[0] if all_words_after_program else ""
    if first_word in ALL_ROOT_REPOSITORY_OPTIONS:
        return OPTION_AND_VALUE_WIDTH
    return 1 if first_word.startswith(ALL_ROOT_REPOSITORY_JOINED_PREFIXES) else 0


def _placed_open_calls(
    placed_create: PlacedCreate, is_gh_repository_set: bool, is_lone_create: bool
) -> list[ShellOpenCall]:
    flag_value = _flag_value(placed_create)
    prefix_value = prefix_repository(list(placed_create.all_command_words)) if flag_value is None else None
    repository_value = flag_value if flag_value is not None else prefix_value
    repository = named_repository(repository_value) if repository_value is not None else None
    is_repository_read = repository is not None or not is_gh_repository_set
    all_calls: list[ShellOpenCall] = []
    for each_head in _placed_heads(placed_create) or [CURRENT_HEAD_REFERENCE]:
        named_call = ShellOpenCall(
            repository=repository,
            branch=each_head,
            folder=placed_create.folder,
            is_folder_followed=placed_create.is_folder_followed and is_repository_read,
            is_prefix_origin_check=prefix_value is not None and repository is None,
            base=_placed_base(placed_create),
            is_base_readable=_is_github_repository_value(repository_value),
            is_lone_create=is_lone_create,
        )
        all_calls.append(named_call)
        if prefix_value is not None:
            all_calls.append(
                replace(
                    named_call,
                    repository=None,
                    is_folder_followed=placed_create.is_folder_followed,
                    is_prefix_origin_check=True,
                    is_base_readable=True,
                )
            )
    return all_calls


def _is_github_repository_value(repository_value: str | None) -> bool:
    """Return whether a ``--repo`` or ``GH_REPO`` value leaves the open on github.com.

    ::

        None, "acme/tools", "github.com/acme/tools" -> True
        "ghe.example.com/acme/tools", "a/b/c/d"     -> False
    """
    if repository_value is None:
        return True
    all_parts = repository_value.split(REPOSITORY_PATH_SEPARATOR)
    if len(all_parts) == OWNER_AND_REPO_PART_COUNT:
        return True
    return len(all_parts) == HOST_OWNER_AND_REPO_PART_COUNT and not _is_other_host(all_parts[0])


def _option_words(placed_create: PlacedCreate) -> list[str]:
    program, all_gh_words = segment_program_and_arguments(list(placed_create.all_command_words))
    return all_gh_words if program == GH_PROGRAM_NAME else list(placed_create.all_arguments)


def _flag_value(placed_create: PlacedCreate) -> str | None:
    all_values = all_option_values(_option_words(placed_create), LONG_REPOSITORY_OPTION, REPOSITORY_SHORT_LETTER)
    return all_values[-1] if all_values else None


def _placed_heads(placed_create: PlacedCreate) -> list[str]:
    """Return each head a create names, with an empty ``--head`` read as the checkout branch.

    gh and the launcher take the last ``--head``, and an empty one leaves gh
    to pick the checkout branch's push target::

        --head a --head b  -> ["a", "b"]
        --head a --head=   -> ["a", "HEAD"]
    """
    all_heads = all_option_values(_option_words(placed_create), LONG_HEAD_OPTION, HEAD_SHORT_LETTER)
    return list(dict.fromkeys(each_head or CURRENT_HEAD_REFERENCE for each_head in all_heads))


def _placed_base(placed_create: PlacedCreate) -> str | None:
    all_bases = all_option_values(_option_words(placed_create), LONG_BASE_OPTION, BASE_SHORT_LETTER)
    return all_bases[-1] if all_bases and all_bases[-1] else None


def _floor_open_call(command: str, folder: str | None, is_lone_create: bool) -> ShellOpenCall | None:
    """Read the first create the way the gate read it before it walked every create.

    The repository comes from a ``--repo`` flag or the origin remote, never
    from a ``GH_REPO=`` prefix::

        GH_REPO=o/r env -u GH_REPO gh pr create --fill  -> origin, HEAD

    There gh opens in origin. The walk also asks for a clean pass on origin
    for every create a ``GH_REPO=`` prefix names, so this call repeats that
    check for the first create.

    The first ``--repo`` is read, so the walk's call checks the repository gh
    takes. The last ``--base`` wins, as in gh::

        --base=a -Bb                -> base b
        --base a --base "" or -dBb  -> a flag the patterns cannot read: base unreadable

    A ``--repo`` on another host also leaves the base unreadable. The words
    after the create, outside its title and body values, are not plain words
    when ``_is_first_create_plain`` finds one bash may split or change.
    """
    options_only = CREATE_TEXT_OPTION_PATTERN.sub(" ", command)
    create_match = GH_PR_CREATE_PATTERN.search(
        options_only
    ) or PULL_REQUEST_SCRIPT_CREATE_PATTERN.search(options_only)
    if not create_match:
        return None
    folder = _folder_after_changes(options_only[: create_match.start()], folder)
    rest = create_match["rest"]
    all_repository_values = [
        each_match["repository"] for each_match in OPEN_REPOSITORY_OPTION_PATTERN.finditer(rest)
    ]
    head_match = HEAD_OPTION_PATTERN.search(rest)
    all_base_matches = list(BASE_OPTION_PATTERN.finditer(rest))
    is_each_flag_read = len(all_repository_values) == len(
        REPOSITORY_OPTION_MENTION_PATTERN.findall(rest)
    ) and len(all_base_matches) == len(BASE_OPTION_MENTION_PATTERN.findall(rest))
    return ShellOpenCall(
        repository=named_repository(all_repository_values[0]) if all_repository_values else None,
        branch=head_match["head"] if head_match else CURRENT_HEAD_REFERENCE,
        folder=folder,
        base=all_base_matches[-1]["base"] if all_base_matches else None,
        is_base_readable=is_each_flag_read
        and all(_is_github_repository_value(each_value) for each_value in all_repository_values),
        is_lone_create=is_lone_create,
        is_plain_words=_is_first_create_plain(command, create_match["rest"]),
    )


def _is_first_create_plain(command: str, raw_create_text: str) -> bool:
    """Return whether the words after the first create, outside its title and body values, are plain.

    Each logical line is read with its quotes, as bash reads them::

        gh pr create --fill --base main $X                        -> False
        gh pr create --title "a [b]" --body "$(cat <<'B' ... B)"  -> True, quoted values
        cd ~/c && gh pr create --body "- [x] done"                -> True, the ~ is not the create's

    Only an unquoted expansion counts here, since the walk judges every word
    the create runs with. A command whose quotes do not close, or whose first
    create sits where no logical line holds it, such as a heredoc body, is
    read raw: a brace, glob or leading tilde in the create's text, in a
    command that holds one outside quotes, is not plain.
    """
    for each_line in quote_aware_lines(command) or []:
        options_only = CREATE_TEXT_OPTION_PATTERN.sub(" ", expansion_marked_line(each_line))
        create_match = GH_PR_CREATE_PATTERN.search(options_only) or PULL_REQUEST_SCRIPT_CREATE_PATTERN.search(
            options_only
        )
        if create_match:
            return UNREADABLE_WORD_MARK not in create_match["rest"]
    return not (holds_unquoted_expansion(command) and _holds_expansion_text(raw_create_text))


def _holds_expansion_text(create_text: str) -> bool:
    if EXTENDED_GLOB_OPENER_PATTERN.search(create_text) is not None:
        return True
    return not ALL_SHELL_EXPANSION_CHARACTERS.isdisjoint(create_text) or any(
        each_word.startswith(TILDE_CHARACTER) for each_word in create_text.split()
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


@dataclass(frozen=True)
class _PushedHead:
    """What GitHub answered for one branch: whether the read ran, and the tip it lists or None."""

    is_read: bool
    commit: str | None


def _pushed_head(owner: str, repo: str, branch: str) -> _PushedHead:
    reference = REMOTE_BRANCH_REFERENCE_TEMPLATE.format(branch=branch)
    remote_url = GITHUB_REMOTE_URL_TEMPLATE.format(owner=owner, repo=repo)
    listing = _remote_listing(remote_url, reference)
    if listing is None:
        return _PushedHead(is_read=False, commit=None)
    return _PushedHead(is_read=True, commit=_listed_commit(listing, reference))


def _remote_listing(remote_url: str, reference: str) -> str | None:
    return answer_once(
        (REMOTE_LISTING_QUESTION, remote_url, reference),
        lambda: _listing_from_github(remote_url, reference),
    )


def _listing_from_github(remote_url: str, reference: str) -> str | None:
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
