"""Find an open follow-up pull request that already holds a new one's parent findings."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from enum import Enum
from http import HTTPStatus
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.gate_run_reads import ReadSlice, answer_once, answer_within_allowance, child_stdout
from hooks_constants.followup_pr_dedupe_constants import (
    ALL_BODY_FILE_OPTIONS,
    ALL_BODY_OPTIONS,
    ALL_GH_ACTION_WORDS_BY_ALIAS,
    ALL_GIT_REMOTE_COMMAND_WORDS,
    ALL_PULL_REQUEST_DISPATCH_INPUT_KEYS,
    ALL_PYTHON_NON_SCRIPT_OPTIONS,
    ALL_PYTHON_OPTIONS_WITH_VALUE,
    ALL_REPOSITORY_OPTIONS,
    ALL_TITLE_OPTIONS,
    ALL_VARIABLE_SETTING_PROGRAM_NAMES,
    ASSIGNMENT_SEPARATOR,
    CREATE_PULL_REQUEST_TOOL_SUFFIX,
    DUPLICATE_FOLLOWUP_REASON_TEMPLATE,
    FOLLOWUP_PARENT_PATTERN,
    GH_PROGRAM_NAME,
    GH_REPO_SET_FOLLOWUP_REASON_TEMPLATE,
    GH_REPOSITORY_ENVIRONMENT_NAME,
    GH_REPOSITORY_ENVIRONMENT_PREFIX,
    GITHUB_API_ROOT,
    GITHUB_REMOTE_PATTERN,
    LONG_OPTION_PREFIX,
    OPEN_PULL_REQUESTS_PATH_TEMPLATE,
    OPTION_AND_VALUE_WIDTH,
    OPTION_PREFIX,
    PYTHON_PROGRAM_NAME_PATTERN,
    READ_TIMEOUT_SECONDS,
    REPOSITORY_OPTION,
    RUN_WORKFLOW_METHOD,
    SHORT_OPTION_LENGTH,
    STANDARD_INPUT_PATH,
    STANDARD_INPUT_SCRIPT,
    UNANSWERED_FOLLOWUP_REASON_TEMPLATE,
    UNREAD_ORIGIN_FOLLOWUP_REASON_TEMPLATE,
    WINDOWS_EXECUTABLE_SUFFIX,
    WORKFLOW_DISPATCH_TOOL_SUFFIX,
)
from hooks_constants.pr_lifecycle_skill_gate_constants import SHELL_TOOL_NAMES
from hooks_constants.pull_request_proof_constants import (
    ALL_GH_CREATE_WORDS,
    PULL_REQUEST_SCRIPT_CREATE_WORD,
    PULL_REQUEST_SCRIPT_NAME,
)
from hooks_constants.pytest_invocation import all_tokens_after_wrappers, unquoted_token
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING
from hooks_constants.shell_command_pipeline import pipeline_segments_for_command
from hooks_constants.shell_command_segments import token_basename
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


@dataclass(frozen=True)
class UnreadOriginDraft:
    """The body of a create whose repository the gate cannot read.

    Attributes:
        body: The create's body.
        reason_template: The deny reason, for the origin remote that gave no
            answer or for a command that sets ``GH_REPO``.
    """

    body: str
    reason_template: str = UNREAD_ORIGIN_FOLLOWUP_REASON_TEMPLATE


class UnreadOpenPullRequests(Enum):
    """Why a repository's open pull requests came back unread.

    ::

        read raised TimeoutError, or URLError whose reason is a TimeoutError -> UNANSWERED
        read raised HTTPError 500 or above, a GitHub server error           -> UNANSWERED
        read raised HTTPError 403, 404 or 429, a refused connection,
        a name that does not resolve, or malformed JSON                     -> FAILED

    An unanswered read refuses the create, because a retry may answer. A
    failed read skips that create and leaves the duplicate to the CI check.
    A rate limit can last an hour and a private repository answers 404 on
    every read, so a retry does not help there.
    """

    UNANSWERED = "no answer inside the allowance"
    FAILED = "a definite failure"


OpenPullRequestReader = Callable[[str, str], list[Mapping[str, object]]]
OpenPullRequestsAnswer = list[Mapping[str, object]] | UnreadOpenPullRequests


def followup_parent_number(body: str) -> int | None:
    """Return the parent number a "Follow-up to #N" line names, or None."""
    match = re.search(FOLLOWUP_PARENT_PATTERN, body, re.IGNORECASE)
    return int(match.group(1)) if match else None


def read_open_pull_requests(owner: str, repo: str) -> list[Mapping[str, object]]:
    """Read one page of a repository's open pull requests from the GitHub API.

    The whole read, connect and headers included, fits in its allowance:
    READ_TIMEOUT_SECONDS, or less when the follow-up deadline is nearer.

    Raises:
        TimeoutError: The read did not finish inside its allowance, or the
            slice had no time left. ``duplicate_followup_reason`` refuses the create.
        urllib.error.HTTPError: GitHub answered with an error status. A status of
            500 or above refuses the create, and any other status skips it.
        Exception: Any other failure, such as a refused connection or a reply
            that is not JSON. ``duplicate_followup_reason`` skips the create.
    """
    url = GITHUB_API_ROOT + OPEN_PULL_REQUESTS_PATH_TEMPLATE.format(owner=owner, repo=repo)
    answer = answer_within_allowance(
        lambda allowance: _fetched_json(url, allowance), READ_TIMEOUT_SECONDS, ReadSlice.FOLLOWUP
    )
    if answer is None:
        raise TimeoutError(url)
    return [each_entry for each_entry in answer if isinstance(each_entry, dict)]


def _fetched_json(url: str, timeout_seconds: float) -> list[object]:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as reply:
        answer = json.loads(reply.read())
    return answer if isinstance(answer, list) else []


def option_value(all_arguments: list[str], all_option_names: frozenset[str]) -> str | None:
    """Return the value of the first named option in an argument list, its quotes removed, or None.

    ::

        ["--head", "a", "--head", "b"], {"--head"}  -> "a"
        ["-H='c'"], {"-H", "--head"}                -> "c"
        ["--fill"], {"--head"}                      -> None

    Args:
        all_arguments: The options of one call.
        all_option_names: Every spelling of the option, such as ``{"-H", "--head"}``.
    """
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
    """Return the body a gh or pull_request.py argument list passes, or None when it passes none.

    ``--body`` text comes back as given. A ``--body-file`` path is read from
    the working directory only when it names a regular file. Standard input,
    a directory, a named pipe, any other special file, and an unreadable file
    give None.
    """
    inline_body = option_value(all_arguments, ALL_BODY_OPTIONS)
    if inline_body is not None:
        return inline_body
    body_path = option_value(all_arguments, ALL_BODY_FILE_OPTIONS)
    if body_path is None or body_path == STANDARD_INPUT_PATH:
        return None
    body_file = Path(working_directory) / body_path
    try:
        if not body_file.is_file():
            return None
        return body_file.read_text(encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY)
    except OSError:
        return None


def title_from_arguments(all_arguments: list[str]) -> str | None:
    """Return the title a gh or pull_request.py argument list passes, or None when it passes none.

    ::

        ["--title", "feat: x"] -> "feat: x"
        ["-t=fix: y"]          -> "fix: y"
        ["--fill"]             -> None
    """
    return option_value(all_arguments, ALL_TITLE_OPTIONS)


def _origin_remote_url(working_directory: str) -> str | None:
    return answer_once(
        ("origin remote url", working_directory),
        lambda: child_stdout(ALL_GIT_REMOTE_COMMAND_WORDS, READ_TIMEOUT_SECONDS, ReadSlice.FOLLOWUP, working_directory),
    )


def _github_repository(remote_url: str) -> tuple[str, str] | None:
    match = re.search(GITHUB_REMOTE_PATTERN, remote_url.strip())
    return (match.group(1), match.group(2)) if match else None


def named_repository(repository_value: str) -> tuple[str, str] | None:
    """Return the owner and name a ``--repo`` value names, or None when it names no pair.

    ::

        "o/r"             -> ("o", "r")
        "github.com/o/r"  -> ("o", "r")
        "notaslug"        -> None

    Args:
        repository_value: The value a ``--repo`` option, ``-R`` or ``GH_REPO`` gives.
    """
    owner, separator, repo = repository_value.rpartition("/")
    owner = owner.rpartition("/")[2]
    return (owner, repo) if separator and owner and repo else None


def all_command_segments(command: str) -> Iterator[list[str]]:
    """Return the token list of each segment in a command and in each command a wrapper inside it runs.

    ::

        "git add x && gh pr view 7"  -> ["git", "add", "x"], then ["gh", "pr", "view", "7"]

    A segment with a quoted word comes back twice, once with the quotes
    removed and once with them kept, because the pipeline parser reads it both
    ways.

    Args:
        command: The shell command text.
    """
    return (
        each_segment
        for each_text in all_wrapped_command_texts(command)
        for each_segment, _each_following_operator in pipeline_segments_for_command(each_text)
    )


def _python_script_index(all_arguments: list[str]) -> int | None:
    index = 0
    while index < len(all_arguments):
        option = unquoted_token(all_arguments[index])
        if option == STANDARD_INPUT_SCRIPT or not option.startswith(OPTION_PREFIX):
            return index
        if not option.startswith(LONG_OPTION_PREFIX) and option[:SHORT_OPTION_LENGTH] in ALL_PYTHON_NON_SCRIPT_OPTIONS:
            return None
        index += OPTION_AND_VALUE_WIDTH if option in ALL_PYTHON_OPTIONS_WITH_VALUE else 1
    return None


def _script_arguments(program: str, all_arguments: list[str]) -> list[str] | None:
    if program == PULL_REQUEST_SCRIPT_NAME:
        return all_arguments
    if re.fullmatch(PYTHON_PROGRAM_NAME_PATTERN, program) is None:
        return None
    script_index = _python_script_index(all_arguments)
    if script_index is None:
        return None
    script_name = token_basename(unquoted_token(all_arguments[script_index]))
    return all_arguments[script_index + 1 :] if script_name == PULL_REQUEST_SCRIPT_NAME else None


def _script_word_arguments(program: str, all_arguments: list[str], word: str) -> list[str] | None:
    all_script_arguments = _script_arguments(program, all_arguments)
    if all_script_arguments is None or all_script_arguments[:1] != [word]:
        return None
    return all_script_arguments[1:]


def _gh_action_arguments(all_arguments: list[str], all_gh_words: list[str]) -> list[str] | None:
    index = 0
    while index < len(all_arguments) and unquoted_token(all_arguments[index]).startswith(OPTION_PREFIX):
        index += OPTION_AND_VALUE_WIDTH if unquoted_token(all_arguments[index]) in ALL_REPOSITORY_OPTIONS else 1
    all_action_words = [
        ALL_GH_ACTION_WORDS_BY_ALIAS.get(unquoted_token(each_word), unquoted_token(each_word))
        for each_word in all_arguments[index : index + len(all_gh_words)]
    ]
    if all_action_words != all_gh_words:
        return None
    return [*all_arguments[index + len(all_gh_words) :], *all_arguments[:index]]


def prefix_repository(all_segment_tokens: list[str]) -> str | None:
    """Return the value a ``GH_REPO=`` prefix gives a gh command, or None when it has none.

    ::

        ["GH_REPO=o/r", "gh", "pr", "create"]  -> "o/r"
        ["gh", "pr", "create", "GH_REPO=o/r"]  -> None

    Args:
        all_segment_tokens: The tokens of one simple command.
    """
    for each_token in all_segment_tokens:
        unquoted_word = unquoted_token(each_token)
        if token_basename(unquoted_word).removesuffix(WINDOWS_EXECUTABLE_SUFFIX) == GH_PROGRAM_NAME:
            return None
        if unquoted_word.startswith(GH_REPOSITORY_ENVIRONMENT_PREFIX):
            return unquoted_word[len(GH_REPOSITORY_ENVIRONMENT_PREFIX) :]
    return None


def _gh_arguments(all_segment_tokens: list[str], all_arguments: list[str], all_gh_words: list[str]) -> list[str] | None:
    all_action_arguments = _gh_action_arguments(all_arguments, all_gh_words)
    if all_action_arguments is None:
        return None
    environment_repository = prefix_repository(all_segment_tokens)
    if environment_repository and option_value(all_action_arguments, ALL_REPOSITORY_OPTIONS) is None:
        return [*all_action_arguments, REPOSITORY_OPTION, environment_repository]
    return all_action_arguments


def _command_arguments(
    all_segment_tokens: list[str], all_gh_words: list[str], script_word: str
) -> list[str] | None:
    program, all_arguments = segment_program_and_arguments(all_segment_tokens)
    if program == GH_PROGRAM_NAME:
        return _gh_arguments(all_segment_tokens, all_arguments, all_gh_words)
    return _script_word_arguments(program, all_arguments, script_word)


def create_arguments(all_segment_tokens: list[str]) -> list[str] | None:
    """Return the options of the pull request create one segment runs, or None when it runs none.

    ::

        ["gh", "pr", "new", "--head", "h"]                -> ["--head", "h"]
        ["gh", "-R", "o/r", "pr", "create"]               -> ["-R", "o/r"]
        ["GH_REPO=o/r", "gh", "pr", "create"]             -> ["--repo", "o/r"]
        ["py", "-3", "~/x/pull_request.py", "create"]     -> []
        ["git", "commit", "-m", "gh pr create"]           -> None

    A repository a root ``-R``/``--repo`` or a ``GH_REPO=`` prefix names
    comes after the create's own options, so the create's own ``--repo`` wins.
    A shell variable, alias or function that holds the program name is not followed.

    Args:
        all_segment_tokens: The tokens of one simple command.
    """
    return _command_arguments(all_segment_tokens, ALL_GH_CREATE_WORDS, PULL_REQUEST_SCRIPT_CREATE_WORD)


def all_pull_request_argument_lists(
    command: str, all_gh_words: list[str], script_word: str
) -> Iterator[list[str]]:
    """Return the options of each gh or pull_request.py call in a command that runs one action.

    ::

        gh pr edit 7 --body x                    -> ["7", "--body", "x"]
        python3 pull_request.py edit --number 8  -> ["--number", "8"]
        gh pr create --body y                    -> nothing, for the edit action

    The words before the options are dropped. A quoted call, which the
    command parser reads twice, comes back once.

    Args:
        command: The shell command text.
        all_gh_words: The gh words that name the action, such as ``["pr", "edit"]``.
        script_word: The pull_request.py action word, such as ``"edit"``.
    """
    all_seen_arguments: set[tuple[str, ...]] = set()
    for each_segment in all_command_segments(command):
        all_arguments = _command_arguments(each_segment, all_gh_words, script_word)
        if all_arguments is None:
            continue
        all_unquoted_arguments = tuple(unquoted_token(each_argument) for each_argument in all_arguments)
        if all_unquoted_arguments in all_seen_arguments:
            continue
        all_seen_arguments.add(all_unquoted_arguments)
        yield all_arguments


def all_create_argument_lists(command: str) -> Iterator[list[str]]:
    """Return the options of each pull request create in a command, gh and pull_request.py alike.

    ::

        gh pr create --title "fix: a" --body x               -> ["--title", "fix: a", "--body", "x"]
        python3 pull_request.py create --repo o/r --title t  -> ["--repo", "o/r", "--title", "t"]
        python3 pull_request.py edit --number 7              -> nothing

    ``create_arguments`` reads each segment, so ``gh pr new``, root ``-R``
    and ``GH_REPO=`` prefixes, and every Python spelling of the script count.

    Args:
        command: The shell command text.
    """
    return all_pull_request_argument_lists(command, ALL_GH_CREATE_WORDS, PULL_REQUEST_SCRIPT_CREATE_WORD)


def _arguments_draft(
    all_arguments: list[str], working_directory: str, is_gh_repository_set: bool
) -> PullRequestDraft | UnreadOriginDraft | None:
    body = body_from_arguments(all_arguments, working_directory)
    if body is None or followup_parent_number(body) is None:
        return None
    repository_value = option_value(all_arguments, ALL_REPOSITORY_OPTIONS)
    if repository_value is None and is_gh_repository_set:
        return UnreadOriginDraft(body, GH_REPO_SET_FOLLOWUP_REASON_TEMPLATE)
    if repository_value is not None:
        repository = named_repository(repository_value)
    else:
        remote_url = _origin_remote_url(working_directory)
        if remote_url is None:
            return UnreadOriginDraft(body)
        repository = _github_repository(remote_url)
    return None if repository is None else PullRequestDraft(repository[0], repository[1], body)


def sets_gh_repository(command: str) -> bool:
    """Return True when a command sets or exports ``GH_REPO`` outside a create's own prefix.

    ::

        export GH_REPO=o/r ; gh pr create    -> True
        GH_REPO=o/r bash -c 'gh pr create'   -> True
        declare -x GH_REPO                   -> True
        GH_REPO=o/r gh pr create             -> False
        echo GH_REPO=o/r                     -> False

    An ``export``, ``declare``, ``typeset``, ``local`` or ``readonly`` that
    names ``GH_REPO`` counts, and so does a ``GH_REPO=`` assignment before any
    program but a create, in the command or in a text a wrapper runs. The gate
    does not follow the value, so a create that names no repository of its
    own cannot be read.

    Args:
        command: The shell command text.
    """
    return any(_segment_sets_gh_repository(each_segment) for each_segment in all_command_segments(command))


def _segment_sets_gh_repository(all_segment_tokens: list[str]) -> bool:
    if create_arguments(all_segment_tokens) is not None:
        return False
    program, all_arguments = segment_program_and_arguments(all_segment_tokens)
    if program in ALL_VARIABLE_SETTING_PROGRAM_NAMES:
        all_names = [unquoted_token(each_argument).partition(ASSIGNMENT_SEPARATOR)[0] for each_argument in all_arguments]
        return GH_REPOSITORY_ENVIRONMENT_NAME in all_names
    all_unwrapped_tokens = all_tokens_after_wrappers(all_segment_tokens)
    program_index = len(all_unwrapped_tokens) - len(all_arguments) - (1 if program else 0)
    return any(
        unquoted_token(each_token).startswith(GH_REPOSITORY_ENVIRONMENT_PREFIX)
        for each_token in all_unwrapped_tokens[:program_index]
    )


def _shell_followup_drafts(command: str, working_directory: str) -> list[PullRequestDraft | UnreadOriginDraft]:
    is_gh_repository_set = sets_gh_repository(command)
    all_drafts = (
        _arguments_draft(all_arguments, working_directory, is_gh_repository_set)
        for all_arguments in all_create_argument_lists(command)
    )
    return list(dict.fromkeys(each_draft for each_draft in all_drafts if each_draft is not None))


def shell_command(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return the command text of a Bash or PowerShell call, or None for any other tool.

    ::

        {"tool_name": "Bash", "tool_input": {"command": "git push"}} -> "git push"
        {"tool_name": "Read", "tool_input": {"file_path": "a.py"}}   -> None

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    tool_input = all_payload_fields.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if all_payload_fields.get("tool_name") not in SHELL_TOOL_NAMES or not isinstance(command, str):
        return None
    return command


def _working_directory(all_payload_fields: Mapping[str, object]) -> str:
    working_directory = all_payload_fields.get("cwd")
    return working_directory if isinstance(working_directory, str) else ""


def _dispatch_fields(all_tool_input_fields: Mapping[str, object]) -> dict[str, object] | None:
    all_inputs = all_tool_input_fields.get("inputs")
    if all_tool_input_fields.get("method") != RUN_WORKFLOW_METHOD or not isinstance(all_inputs, dict):
        return None
    if not all(isinstance(all_inputs.get(each_key), str) for each_key in ALL_PULL_REQUEST_DISPATCH_INPUT_KEYS):
        return None
    return {**all_inputs, "owner": all_tool_input_fields.get("owner"), "repo": all_tool_input_fields.get("repo")}


def create_tool_fields(all_payload_fields: Mapping[str, object]) -> Mapping[str, object] | None:
    """Return the fields a GitHub MCP call that opens a pull request carries, or None.

    ::

        create_pull_request {owner, repo, title, body}       -> those fields
        actions_run_trigger run_workflow, head and title in   -> the inputs, owner and repo
        actions_run_trigger whose inputs name no head         -> None

    A dispatch whose inputs name a head branch and a title runs a workflow
    that opens the pull request, so it counts as a create call.

    Args:
        all_payload_fields: The parsed PreToolUse input.

    Returns:
        The owner, repo, title, body and head keys the call names, or None.
    """
    tool_name = all_payload_fields.get("tool_name")
    tool_input = all_payload_fields.get("tool_input")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return None
    if tool_name.endswith(CREATE_PULL_REQUEST_TOOL_SUFFIX):
        return tool_input
    return _dispatch_fields(tool_input) if tool_name.endswith(WORKFLOW_DISPATCH_TOOL_SUFFIX) else None


def followup_drafts(all_payload_fields: Mapping[str, object]) -> list[PullRequestDraft | UnreadOriginDraft]:
    """Return one draft per distinct repository and body among the creates whose body names a parent.

    ::

        create on o/r "Follow-up to #7" && create on o/r "Follow-up to #8" -> both drafts
        create_pull_request {owner, repo, body "Follow-up to #7"}          -> that one draft
        create with no --repo where the origin read gives nothing         -> UnreadOriginDraft
        create with no --repo whose origin is not on GitHub               -> no draft
        create whose body names no parent, or any other tool               -> []

    A body that names no parent gives no draft before any repository or
    origin read. The origin is read once per gate run. A quoted create,
    which the command parser reads twice, gives one draft.

    Args:
        all_payload_fields: The parsed PreToolUse input.

    Returns:
        The drafts, in command order.
    """
    create_fields = create_tool_fields(all_payload_fields)
    if create_fields is not None:
        return _tool_followup_drafts(create_fields)
    command = shell_command(all_payload_fields)
    if command is None:
        return []
    return _shell_followup_drafts(command, _working_directory(all_payload_fields))


def _tool_followup_drafts(all_create_fields: Mapping[str, object]) -> list[PullRequestDraft | UnreadOriginDraft]:
    owner, repo, body = (all_create_fields.get(each_key) for each_key in ("owner", "repo", "body"))
    if not isinstance(body, str) or followup_parent_number(body) is None:
        return []
    return [PullRequestDraft(owner, repo, body)] if isinstance(owner, str) and isinstance(repo, str) else []


def _open_pull_requests_once(owner: str, repo: str, read_open: OpenPullRequestReader) -> OpenPullRequestsAnswer:
    return answer_once(("open pull requests", owner, repo), lambda: _open_pull_requests_answer(owner, repo, read_open))


def _is_unanswered(error: Exception) -> bool:
    if isinstance(error, urllib.error.HTTPError):
        return error.code >= HTTPStatus.INTERNAL_SERVER_ERROR
    return isinstance(error, TimeoutError) or (
        isinstance(error, urllib.error.URLError) and isinstance(error.reason, TimeoutError)
    )


def _open_pull_requests_answer(owner: str, repo: str, read_open: OpenPullRequestReader) -> OpenPullRequestsAnswer:
    try:
        return read_open(owner, repo)
    except Exception as error:
        return UnreadOpenPullRequests.UNANSWERED if _is_unanswered(error) else UnreadOpenPullRequests.FAILED


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

    ::

        open pull request #9 says "Follow-up to #7"      -> DUPLICATE_FOLLOWUP_REASON_TEMPLATE
        the read gives no answer inside its allowance   -> UNANSWERED_FOLLOWUP_REASON_TEMPLATE
        the read answers with a GitHub server error     -> UNANSWERED_FOLLOWUP_REASON_TEMPLATE
        no --repo, and the origin read gives nothing    -> UNREAD_ORIGIN_FOLLOWUP_REASON_TEMPLATE
        the read answers 403, 404 or 429, refuses, or sends bad JSON -> None for that create

    Every create body that names a parent is checked, in command order, and
    the first duplicate, unanswered read or unread origin denies. A read that
    answers with a failure skips that create. When no create body carries a
    "Follow-up to #N" line, nothing is read, not even the origin remote.

    Args:
        all_payload_fields: The parsed PreToolUse input.
        read_open: Reads the open pull requests of an owner and repository;
            None reads them from the GitHub API. A raised TimeoutError means
            no answer; any other exception means a failed read.
    """
    reader = read_open or read_open_pull_requests
    for each_draft in followup_drafts(all_payload_fields):
        parent_number = followup_parent_number(each_draft.body)
        if parent_number is None:
            continue
        if isinstance(each_draft, UnreadOriginDraft):
            return each_draft.reason_template.format(parent_number=parent_number)
        answer = _open_pull_requests_once(each_draft.owner, each_draft.repo, reader)
        if answer is UnreadOpenPullRequests.UNANSWERED:
            return UNANSWERED_FOLLOWUP_REASON_TEMPLATE.format(
                owner=each_draft.owner, repo=each_draft.repo, parent_number=parent_number
            )
        if answer is UnreadOpenPullRequests.FAILED:
            continue
        reason = _reason_for_parent(parent_number, answer)
        if reason is not None:
            return reason
    return None
