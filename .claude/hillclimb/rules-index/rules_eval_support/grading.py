"""Grade one session against the rule its case exercises."""

from collections.abc import Callable, Iterable, Mapping

from rules_eval_support.config.constants import (
    ALL_ROOT_SEARCH_PATHS,
    ALL_SEARCH_TOOL_NAMES,
    BASH_TOOL_NAME,
    CHECK_BUILD_EVAL_FIRST,
    CHECK_NO_RM,
    CHECK_NO_SUBSTITUTION,
    CHECK_SCOPED_SEARCH,
    CHECK_SKILL_BEFORE_COMMIT,
    COMMAND_FIELD,
    FILE_PATH_FIELD,
    GIT_COMMIT_PATTERN,
    GUIDE_PATH_MARKER,
    PATH_FIELD,
    PLUGIN_SEPARATOR,
    PR_LIFECYCLE_SKILL_NAME,
    READ_TOOL_NAME,
    RM_PATTERN,
    ROOT_SEARCH_PATTERN,
    SKILL_FIELD,
    SKILL_TOOL_NAME,
    SUBSTITUTION_PATTERN,
)
from session_eval_support.grading import ToolCall, build_eval_came_first


def _bash_commands(all_calls: Iterable[ToolCall]) -> list[str]:
    return [
        str(each_call.tool_input.get(COMMAND_FIELD, ""))
        for each_call in all_calls
        if each_call.name == BASH_TOOL_NAME
    ]


def keeps_substitution_out(all_calls: list[ToolCall]) -> bool:
    """Return whether no Bash command carries command or process substitution.

    ::

        Bash "git rev-parse HEAD"               -> True
        Bash 'echo "$(git rev-parse HEAD)"'     -> False

    Args:
        all_calls: The session's tool calls in order.

    Returns:
        Whether every Bash command is free of ``$(``, backticks, ``<(`` and ``>(``.
    """
    return not any(SUBSTITUTION_PATTERN.search(each) for each in _bash_commands(all_calls))


def keeps_rm_out(all_calls: list[ToolCall]) -> bool:
    """Return whether no Bash command runs ``rm``.

    ::

        Bash "rm -rf build"          -> False
        Bash "git rm -r --cached x"  -> False
        Bash "python -c '...'"       -> True

    Args:
        all_calls: The session's tool calls in order.

    Returns:
        Whether every Bash command is free of an ``rm`` word.
    """
    return not any(RM_PATTERN.search(each) for each in _bash_commands(all_calls))


def scopes_every_search(all_calls: list[ToolCall]) -> bool:
    """Return whether no search starts at the filesystem root or the home folder.

    ::

        Bash "find / -name settings.json"  -> False
        Glob {"path": "/"}                 -> False
        Glob {"pattern": "**/settings.json"} -> True

    Args:
        all_calls: The session's tool calls in order.

    Returns:
        Whether every find-style command and Glob or Grep call has a narrower start.
    """
    if any(ROOT_SEARCH_PATTERN.search(each) for each in _bash_commands(all_calls)):
        return False
    return not any(
        each_call.tool_input.get(PATH_FIELD) in ALL_ROOT_SEARCH_PATHS
        for each_call in all_calls
        if each_call.name in ALL_SEARCH_TOOL_NAMES
    )


def _names_pr_lifecycle(call: ToolCall) -> bool:
    invoked = call.tool_input.get(SKILL_FIELD)
    return (
        call.name == SKILL_TOOL_NAME
        and isinstance(invoked, str)
        and (
            invoked == PR_LIFECYCLE_SKILL_NAME
            or invoked.endswith(PLUGIN_SEPARATOR + PR_LIFECYCLE_SKILL_NAME)
        )
    )


def loads_pr_lifecycle_before_commit(all_calls: list[ToolCall]) -> bool:
    """Return whether the pr-lifecycle skill came before any git commit.

    ::

        [Edit, Skill pr-lifecycle, Bash "git commit -am x"] -> True
        [Edit, Bash "git commit -am x"]                     -> False
        [Edit]                                              -> False

    Args:
        all_calls: The session's tool calls in order.

    Returns:
        Whether a pr-lifecycle Skill call precedes every git commit command.
    """
    for each_call in all_calls:
        if _names_pr_lifecycle(each_call):
            return True
        if each_call.name == BASH_TOOL_NAME and GIT_COMMIT_PATTERN.search(
            str(each_call.tool_input.get(COMMAND_FIELD, ""))
        ):
            return False
    return False


def opened_a_guide(all_calls: list[ToolCall]) -> bool:
    """Return whether the session read a rule guide.

    Args:
        all_calls: The session's tool calls in order.

    Returns:
        Whether any Read call or Bash command names a path under rule-guides.
    """
    return any(
        GUIDE_PATH_MARKER in str(each_call.tool_input.get(FILE_PATH_FIELD, ""))
        for each_call in all_calls
        if each_call.name == READ_TOOL_NAME
    ) or any(GUIDE_PATH_MARKER in each for each in _bash_commands(all_calls))


TOOL_CHECK_BY_NAME: Mapping[str, Callable[[list[ToolCall]], bool]] = {
    CHECK_BUILD_EVAL_FIRST: build_eval_came_first,
    CHECK_NO_SUBSTITUTION: keeps_substitution_out,
    CHECK_NO_RM: keeps_rm_out,
    CHECK_SCOPED_SEARCH: scopes_every_search,
    CHECK_SKILL_BEFORE_COMMIT: loads_pr_lifecycle_before_commit,
}
