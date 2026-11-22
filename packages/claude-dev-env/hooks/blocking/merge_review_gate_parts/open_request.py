"""Read each pull request open a PreToolUse payload asks for, and the head each opens with."""

from __future__ import annotations

import os
import shlex
import sys
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.followup_pr_dedupe import named_repository, prefix_repository, sets_gh_repository
from blocking.merge_review_gate_parts.create_folders import PlacedCreate, all_placed_creates
from blocking.merge_review_gate_parts.create_options import all_option_values
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
    LONE_CREATE_SUBCOMMAND_SLICE,
    ALL_BRANCH_REFERENCE_PREFIXES,
    ALL_CHECKOUT_BRANCH_ARGUMENTS,
    ALL_STORED_HISTORY_GIT_SETTINGS,
    ALL_ANCESTRY_WALK_ARGUMENTS,
    ALL_OUTSIDE_BASE_ARGUMENTS,
    ALL_MERGE_TREE_ARGUMENTS,
    ALL_VERIFY_OBJECT_ARGUMENTS,
    COMMIT_OBJECT_TEMPLATE,
    TREE_OF_COMMIT_TEMPLATE,
    ALL_OTHER_LINE_REFERENCE_ARGUMENTS,
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
)
from hooks_constants.shell_command_segments import token_basename
from hooks_constants.shell_command_wrappers import segment_program_and_arguments


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
        is_base_known: False when the gate cannot tell which base the open
            uses, so no base is read and no earlier pass gets credit.
        base_setting_branch: The branch whose ``gh-merge-base`` setting gh
            reads when the open names no base, or None when none applies.
    """

    owner: str
    repo: str
    head: str | None
    folder: str | None = field(default=None, compare=False)
    branch: str | None = field(default=None, compare=False)
    base: str | None = field(default=None, compare=False)
    is_base_known: bool = field(default=True, compare=False)
    base_setting_branch: str | None = field(default=None, compare=False)

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
    """

    repository: tuple[str, str] | None
    branch: str
    folder: str | None
    is_folder_followed: bool = True
    is_prefix_origin_check: bool = field(default=False, compare=False)
    base: str | None = None
    is_base_readable: bool = field(default=True, compare=False)
    is_lone_create: bool = field(default=False, compare=False)


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
        is_base_known=call.base is not None,
    )


def _shell_open_request(call: ShellOpenCall) -> OpenRequest:
    if not call.is_folder_followed:
        owner, repo = call.repository or ("", "")
        return OpenRequest(owner=owner, repo=repo, head=None)
    owner, repo = call.repository or _origin_repository(call.folder)
    branch = _branch_name(call.branch, call.folder)
    is_base_known = (
        call.is_base_readable
        and not _is_other_host(os.environ.get(GH_HOST_VARIABLE))
        and not _names_another_repository(os.environ.get(GH_REPOSITORY_ENVIRONMENT_NAME), owner, repo)
        and call.is_lone_create
        and (call.base is not None or branch is not None)
        and (call.repository is not None or not _resolves_to_another_remote(call.folder))
    )
    return OpenRequest(
        owner=owner,
        repo=repo,
        head=_branch_commit(call.branch, call.folder),
        folder=call.folder,
        branch=branch,
        base=call.base,
        is_base_known=is_base_known,
        base_setting_branch=branch if call.base is None else None,
    )


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


def is_held_by_another_line(commit: str, head: str, folder: str | None) -> bool:
    """Return whether a branch that lacks the head holds a commit.

    A review pass on the branch's own earlier commit covers the fix commits
    on top of it. A commit some other branch holds without the head, such as
    a commit of ``main`` or of the branch this one stacks on, is not this
    branch's review::

        feature holds reviewed abc123 and head def456      -> False
        second stacks on feature at abc123, head def456    -> True, feature lacks def456
        main holds abc123, the head branches off main      -> True

    Local branches and remote branches are both read, and replace refs and
    grafts are not. A read that fails or runs out of time counts as held, so the open
    is denied.

    Args:
        commit: The commit a review pass saw.
        head: The commit the pull request would open with.
        folder: The folder git reads the branches in.

    Returns:
        True when some branch holds ``commit`` and not ``head``.
    """
    listing = _stored_history_read(
        [
            *ALL_OTHER_LINE_REFERENCE_ARGUMENTS,
            CONTAINS_OPTION_TEMPLATE.format(commit=commit),
            NO_CONTAINS_OPTION_TEMPLATE.format(commit=head),
            *ALL_BRANCH_REFERENCE_PREFIXES,
        ],
        folder,
    )
    return listing is None or bool(listing.strip())


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
        base holds a squash of the commit                    -> False
        the merge conflicts, or a read fails or runs out     -> False

    The merge runs with ``git merge-tree --write-tree``, which stores the
    merged tree as loose objects and moves no ref.

    Args:
        commit: The commit a review pass saw.
        base_commit: The commit the base branch holds, from ``base_tip``.
        folder: The folder git reads the history in.

    Returns:
        True when the merged tree differs from the base commit's tree.
    """
    merged_listing = _stored_history_read([*ALL_MERGE_TREE_ARGUMENTS, base_commit, commit], folder)
    base_tree = _stored_history_read(
        [*ALL_VERIFY_OBJECT_ARGUMENTS, TREE_OF_COMMIT_TEMPLATE.format(commit=base_commit)], folder
    )
    if not merged_listing or not merged_listing.strip() or not base_tree or not base_tree.strip():
        return False
    return merged_listing.split()[0] != base_tree.strip()


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
        all_calls.extend(_placed_open_calls(each_create, is_gh_repository_set, is_lone_create))
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
        git config "branch.x.gh-merge""-base" y && gh pr create -> False
        LANG=C gh pr create --fill                           -> False
        gh pr create --fill > out.txt                        -> False
        gh pr create --title "$(date)"                       -> False
        gh pr create --fill # ; git config ...               -> False
        gh pr create --title 'a & b'                         -> False

    Any shell operator character, ``#``, ``$``, backtick or line break in the
    text, quoted or not, makes the command not lone, so no comment, segment,
    redirect or substitution hides from the split. The rest is split as POSIX
    shell words, and a split that fails also makes the command not lone.

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
    return program == GH_PROGRAM_NAME and tuple(all_words[LONE_CREATE_SUBCOMMAND_SLICE]) in ALL_LONE_CREATE_SUBCOMMANDS


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

    A ``--repo`` on another host also leaves the base unreadable.
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
