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
from blocking.merge_review_gate_parts.quoted_lines import holds_unquoted_expansion
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
)
from hooks_constants.shell_command_segments import token_basename
from hooks_constants.shell_command_wrappers import segment_program_and_arguments


class WithheldCredit(Enum):
    """Why a recorded pass on an earlier commit of the branch gives the open no credit.

    Each value is the cause sentence of the deny reason::

        create beside a cd, or a title with parentheses -> NOT_LONE, run the create alone
        create tool call with no base                   -> TOOL_NO_BASE, set its base
        base GitHub does not list                       -> BASE_UNREAD, names the base
        backup branch at the reviewed commit            -> HELD_BY_OTHER_REFERENCE, names it
        origin/<branch> under a hand-edited fetch       -> MAPPED_TRACKING_REFERENCE, names the refspec
        local <branch> left behind its pushed fixes     -> LOCAL_BRANCH_BEHIND, fast-forward it
        base already holds the reviewed commit          -> INSIDE_BASE, review again

    The first twelve causes leave the pass in place, so the step they name
    needs no new review. The last two say the pass covered base work.
    """

    UNREAD_FLAG = UNREAD_FLAG_CAUSE
    OTHER_HOST = OTHER_HOST_CAUSE
    SESSION_REPOSITORY = SESSION_REPOSITORY_CAUSE
    NOT_LONE = NOT_LONE_CAUSE
    NO_BASE_OR_BRANCH = NO_BASE_OR_BRANCH_CAUSE
    OTHER_REMOTE = OTHER_REMOTE_CAUSE
    TOOL_NO_BASE = TOOL_NO_BASE_CAUSE
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
        is_plain_words: False when bash may expand a brace, a glob, an extended
            glob or a tilde in the create's words, so the gate cannot tell the head,
            base or repository gh reads.
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
        is_plain_words: False when bash may expand a brace, a glob, an extended
            glob or a tilde in the create's words before gh reads them.
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
    return OpenRequest(
        owner=call.owner,
        repo=call.repo,
        head=head,
        folder=call.folder,
        branch=_branch_name(call.branch, call.folder) if call.branch else None,
        base=call.base,
        unknown_base_cause=None if call.base is not None else WithheldCredit.TOOL_NO_BASE,
        head_owner=_head_owner(call.branch) if call.branch else None,
    )


def _head_owner(branch: str) -> str | None:
    head_owner, separator, _branch = branch.partition(HEAD_OWNER_SEPARATOR)
    return head_owner if separator else None


def _shell_open_request(call: ShellOpenCall) -> OpenRequest:
    if not call.is_folder_followed:
        owner, repo = call.repository or ("", "")
        return OpenRequest(owner=owner, repo=repo, head=None, is_plain_words=call.is_plain_words)
    owner, repo = call.repository or _origin_repository(call.folder)
    branch = _branch_name(call.branch, call.folder)
    return OpenRequest(
        owner=owner,
        repo=repo,
        head=_branch_commit(call.branch, call.folder),
        folder=call.folder,
        branch=branch,
        base=call.base,
        unknown_base_cause=_unknown_base_cause(call, owner, repo, branch),
        base_setting_branch=branch if call.base is None else None,
        head_owner=_head_owner(call.branch),
        is_plain_words=call.is_plain_words,
    )


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
    listing = child_stdout(
        ["git", *ALL_SETTINGS_READ_ARGUMENTS], GIT_TIMEOUT_SECONDS, ReadSlice.FOLLOWUP, folder
    )
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
    listing = child_stdout(
        ["git", *ALL_SETTINGS_READ_ARGUMENTS], GIT_TIMEOUT_SECONDS, ReadSlice.FOLLOWUP, folder
    )
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
    all_calls: list[OpenCall] = []
    is_gh_repository_set = sets_gh_repository(command)
    is_lone_create = _is_lone_gh_create(command)
    for each_create in all_placed_creates(command, folder):
        all_calls.extend(
            replace(each_call, is_plain_words=each_create.is_plain_words)
            for each_call in _placed_open_calls(each_create, is_gh_repository_set, is_lone_create)
        )
    floor_call = _floor_open_call(command, folder, is_lone_create)
    if floor_call is not None:
        all_calls.append(floor_call)
    return list(dict.fromkeys(all_calls))


def _is_lone_gh_create(command: str) -> bool:
    """Return whether a whole shell command is one plain ``gh pr create``.

    gh reads the head branch's ``gh-merge-base`` setting when it runs. Any
    other word in the command, quoted or not, can write that setting or the
    git config gh reads first, so only a lone create is read::

        gh pr create --fill                                  -> True
        gh -R acme/tools pr create --fill                    -> True
        git config "branch.x.gh-merge""-base" y && gh pr create -> False
        LANG=C gh pr create --fill                           -> False
        gh pr create --fill > out.txt                        -> False
        gh pr create --title "$(date)"                       -> False
        gh pr create --fill # ; git config ...               -> False
        gh pr create --title 'a & b'                         -> False
        gh pr create --title '[WIP] {x}?'                    -> False

    Any shell operator character, ``#``, ``$``, brace, glob character
    ``* ? [``, ``~``, backtick or line break in the text, quoted or not, makes
    the command not lone, so no comment, segment, redirect, substitution or
    expansion hides from the split. The rest is split as POSIX shell words,
    and a split that fails also makes the command not lone. One root
    ``-R``/``--repo`` value may come between ``gh`` and ``pr``.

    Args:
        command: The shell command text.

    Returns:
        True when the command is one ``gh pr create`` or ``gh pr new`` and nothing else.
    """
    if not ALL_LONE_CREATE_REFUSED_CHARACTERS.isdisjoint(command):
        return False
    try:
        all_words = shlex.split(command, comments=False, posix=True)
    except ValueError:
        return False
    if not all_words:
        return False
    program = token_basename(all_words[0]).removesuffix(WINDOWS_EXECUTABLE_SUFFIX)
    subcommand_start = 1 + _root_repository_width(all_words[1:])
    all_subcommand_words = tuple(all_words[subcommand_start : subcommand_start + LONE_CREATE_SUBCOMMAND_WIDTH])
    return program == GH_PROGRAM_NAME and all_subcommand_words in ALL_LONE_CREATE_SUBCOMMANDS


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
    all_heads = all_option_values(_option_words(placed_create), LONG_HEAD_OPTION, HEAD_SHORT_LETTER)
    return list(dict.fromkeys(each_head for each_head in all_heads if each_head))


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

    A ``--repo`` on another host also leaves the base unreadable. A create
    whose text holds a brace, a glob character or a leading tilde, in a
    command that holds one outside quotes, is not plain words.
    """
    options_only = CREATE_TEXT_OPTION_PATTERN.sub(" ", command)
    is_expanding_text = holds_unquoted_expansion(command)
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
        is_plain_words=not (is_expanding_text and _holds_expansion_text(create_match["rest"])),
    )


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
