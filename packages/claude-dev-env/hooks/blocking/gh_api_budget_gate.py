#!/usr/bin/env python3
"""PreToolUse gate: keep agents from draining the GitHub API limit.

The gate refuses three kinds of gh call, checked in this order::

    gh run watch 123                                   watch command
    gh pr checks 12 --watch                            watch command
    while :; do gh run view 1; sleep 10; done          tight polling loop
    watch -n 5 gh run view 1                           tight polling loop
    gh pr view 12   (core limit 4000 of 5000 used)     spent budget

A watch command polls every few seconds until a run ends. A polling loop is a
Bash ``while``, ``until`` or ``for`` loop, a PowerShell ``while``, ``do``,
``for`` or ``foreach`` loop or ``ForEach-Object`` or ``%`` pipeline loop, or
``watch``, that calls gh and sleeps under 60 seconds in total per pass. Each
outermost loop is read on its own, from its keyword through the ``done`` or
``}`` that closes it, and a loop nested inside it counts toward it. A brace
glued to a word, as in ``{gh run view 1}``, counts as its own token. An
endless loop such as ``while :`` or
``for (;;)``, or a ``while`` or ``until`` loop whose condition calls gh, is
refused when it calls gh with no sleep. Any other loop with no sleep passes,
and so does a loop whose sleep is a variable.

A gh read on the core REST limit is refused while ``used * 5 >= limit * 4``.
The reads are the ``gh api`` calls with no write method and no field or input
option, and the subcommands the constants table lists, such as ``pr view`` and
``run list``. Writes, local commands, ``gh api graphql`` and ``gh api
rate_limit`` pass. ``hooks_constants/gh_api_budget.py`` reads the limit and
caches it for five minutes, and a limit it cannot read lets the call through.

The program is read past wrappers, chained commands and a leading PowerShell
``$name =`` assignment, so ``bash -c "gh run watch 1"`` and ``$s = gh run
watch 1`` are refused, while quoted text such as ``echo "gh run watch"``
passes. A command with no gh call reads no cache and runs no query.

Hosted by ``blocking/bash_pre_tool_use_dispatcher.py`` for the Bash and
PowerShell tools.
"""

from __future__ import annotations

import json
import sys
import time
from itertools import pairwise
from pathlib import Path

try:
    _hooks_root_directory = str(Path(__file__).resolve().parent.parent)
    if _hooks_root_directory not in sys.path:
        sys.path.insert(0, _hooks_root_directory)
    from hooks_constants.bash_pre_tool_use_dispatcher_constants import (
        ALL_BASH_AND_POWERSHELL_TOOL_NAMES,
        DENY_DECISION,
        HOOK_EVENT_NAME,
    )
    from hooks_constants.cloud_graphql_gate_constants import (
        ALL_GH_HELP_FLAGS,
        GH_API_SUBCOMMAND,
        GH_ENDPOINT_PATH_SEPARATOR,
        GITHUB_GRAPHQL_ENDPOINT_PATTERN,
    )
    from hooks_constants.gh_api_budget import (
        CoreRateBudget,
        is_core_budget_spent,
        read_core_rate_budget,
    )
    from hooks_constants.gh_api_budget_gate_constants import (
        ALL_GH_API_BODY_OPTIONS,
        ALL_GH_API_METHOD_OPTIONS,
        ALL_GH_API_READ_METHODS,
        ALL_GH_API_SHORT_BODY_OPTIONS,
        ALL_GH_API_UNBUDGETED_ENDPOINTS,
        ALL_GH_PR_CHECKS_COMMAND_WORDS,
        ALL_GH_READ_COMMAND_GROUPS,
        ALL_GH_READ_SUBCOMMANDS_BY_COMMAND_GROUP,
        ALL_GH_RUN_WATCH_COMMAND_WORDS,
        GATE_HOOK_NAME,
        GH_API_SHORT_METHOD_OPTION,
        GH_COMMAND_PATH_LENGTH,
        GH_SHORT_OPTION_LENGTH,
        GH_WATCH_OPTION,
        RESET_TIME_FORMAT,
        SPENT_BUDGET_DENY_REASON_TEMPLATE,
        SPENT_BUDGET_RESET_SENTENCE_TEMPLATE,
        TIGHT_POLLING_LOOP_DENY_REASON,
        WATCH_COMMAND_DENY_REASON,
    )
    from hooks_constants.gh_argument_lists import all_gh_call_argument_lists
    from hooks_constants.gh_command_words import gh_command_words_and_options
    from hooks_constants.gh_command_words_constants import GH_OPTION_VALUE_SEPARATOR
    from hooks_constants.gh_shell_loop_scan import (
        is_tight_gh_loop_text,
        is_tight_gh_watch_segment,
    )
    from hooks_constants.hook_block_logger import log_hook_block
    from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
    from hooks_constants.pytest_invocation import unquoted_token
    from hooks_constants.shell_command_wrappers import (
        all_wrapped_command_segments,
        all_wrapped_command_texts,
    )
except ImportError as import_error:
    raise ImportError(
        "The gh API budget gate cannot import its dependencies; "
        "ensure the hooks directory is importable."
    ) from import_error


def _is_gh_watch_call(all_gh_arguments: list[str]) -> bool:
    all_command_words, all_option_names = gh_command_words_and_options(all_gh_arguments)
    if any(each_option in ALL_GH_HELP_FLAGS for each_option in all_option_names):
        return False
    command_path = tuple(all_command_words[:GH_COMMAND_PATH_LENGTH])
    if command_path == ALL_GH_RUN_WATCH_COMMAND_WORDS:
        return True
    return command_path == ALL_GH_PR_CHECKS_COMMAND_WORDS and GH_WATCH_OPTION in all_option_names


def runs_gh_watch_command(command: str) -> bool:
    """Return True when the command runs ``gh run watch`` or ``gh pr checks --watch``.

    ::

        gh run watch 123                 -> True
        cd repo && gh pr checks --watch  -> True
        echo "gh run watch"              -> False

    Args:
        command: The shell command text the agent is about to run.
    """
    return any(_is_gh_watch_call(each) for each in all_gh_call_argument_lists(command))


def runs_tight_gh_polling_loop(command: str) -> bool:
    """Return True when a shell loop or ``watch`` calls gh with under 60 seconds of sleep.

    ::

        while :; do gh run view 1; sleep 30; done      -> True
        while ($true) { gh run view 1 }                -> True
        watch -n 5 gh run view 1                       -> True
        while :; do gh run view 1; sleep 60; done      -> False
        for x in a b c; do gh pr view $x; done         -> False

    Args:
        command: The shell command text the agent is about to run.
    """
    if any(is_tight_gh_watch_segment(each) for each in all_wrapped_command_segments(command)):
        return True
    return any(is_tight_gh_loop_text(each) for each in all_wrapped_command_texts(command))


def _gh_api_method(all_gh_arguments: list[str]) -> str | None:
    """Return the HTTP method a ``gh api`` call names, uppercased, or None when it names none."""
    all_unquoted_arguments = [unquoted_token(each) for each in all_gh_arguments]
    for each_previous_argument, each_argument in pairwise(["", *all_unquoted_arguments]):
        if each_previous_argument in ALL_GH_API_METHOD_OPTIONS:
            return each_argument.upper()
        option, separator, attached_method = each_argument.partition(GH_OPTION_VALUE_SEPARATOR)
        if option in ALL_GH_API_METHOD_OPTIONS and separator:
            return attached_method.upper()
        is_glued_short_method = each_argument.startswith(GH_API_SHORT_METHOD_OPTION)
        if is_glued_short_method and len(each_argument) > GH_SHORT_OPTION_LENGTH:
            return each_argument[GH_SHORT_OPTION_LENGTH:].upper()
    return None


def _is_budgeted_api_call(
    all_gh_arguments: list[str], all_command_words: list[str], all_option_names: list[str]
) -> bool:
    endpoint = unquoted_token(all_command_words[1]) if len(all_command_words) > 1 else ""
    is_unbudgeted_endpoint = (
        endpoint.strip(GH_ENDPOINT_PATH_SEPARATOR).lower() in ALL_GH_API_UNBUDGETED_ENDPOINTS
        or GITHUB_GRAPHQL_ENDPOINT_PATTERN.search(endpoint) is not None
    )
    if not endpoint or is_unbudgeted_endpoint:
        return False
    method = _gh_api_method(all_gh_arguments)
    if method is not None:
        return method in ALL_GH_API_READ_METHODS
    return not any(
        each_option in ALL_GH_API_BODY_OPTIONS
        or each_option[:GH_SHORT_OPTION_LENGTH] in ALL_GH_API_SHORT_BODY_OPTIONS
        for each_option in all_option_names
    )


def _is_budgeted_gh_read(all_gh_arguments: list[str]) -> bool:
    all_command_words, all_option_names = gh_command_words_and_options(all_gh_arguments)
    if not all_command_words or any(each in ALL_GH_HELP_FLAGS for each in all_option_names):
        return False
    command_group = all_command_words[0]
    if command_group == GH_API_SUBCOMMAND:
        return _is_budgeted_api_call(all_gh_arguments, all_command_words, all_option_names)
    if command_group in ALL_GH_READ_COMMAND_GROUPS:
        return True
    all_read_subcommands = ALL_GH_READ_SUBCOMMANDS_BY_COMMAND_GROUP.get(command_group, frozenset())
    return len(all_command_words) > 1 and all_command_words[1] in all_read_subcommands


def runs_budgeted_gh_read(command: str) -> bool:
    """Return True when the command runs a gh read that draws on the core REST limit.

    ::

        gh pr view 12                          -> True
        gh api repos/o/r/pulls                 -> True
        gh api -X POST repos/o/r/issues        -> False
        gh api graphql -f query=@q.graphql     -> False
        gh auth status                         -> False

    Args:
        command: The shell command text the agent is about to run.
    """
    return any(_is_budgeted_gh_read(each) for each in all_gh_call_argument_lists(command))


def _spent_budget_reason(budget: CoreRateBudget) -> str:
    reset_sentence = ""
    try:
        if budget.reset is not None:
            reset_time = time.strftime(RESET_TIME_FORMAT, time.gmtime(budget.reset))
            reset_sentence = SPENT_BUDGET_RESET_SENTENCE_TEMPLATE.format(reset_time=reset_time)
    except (OverflowError, OSError, ValueError):
        reset_sentence = ""
    return SPENT_BUDGET_DENY_REASON_TEMPLATE.format(
        used=budget.used, limit=budget.limit, reset_sentence=reset_sentence
    )


def _deny_reason(command: str, all_gh_argument_lists: list[list[str]]) -> str | None:
    """Return the first refusal's reason for a command that calls gh, or None when it passes."""
    if any(_is_gh_watch_call(each) for each in all_gh_argument_lists):
        return WATCH_COMMAND_DENY_REASON
    if runs_tight_gh_polling_loop(command):
        return TIGHT_POLLING_LOOP_DENY_REASON
    if not any(_is_budgeted_gh_read(each) for each in all_gh_argument_lists):
        return None
    budget = read_core_rate_budget()
    if budget is None or not is_core_budget_spent(budget):
        return None
    return _spent_budget_reason(budget)


def main() -> None:
    """Deny a gh watch command, a tight gh polling loop, or a gh read on a spent budget."""
    hook_payload = read_hook_input_dictionary_from_stdin()
    if hook_payload is None:
        return
    tool_name = hook_payload.get("tool_name")
    if tool_name not in ALL_BASH_AND_POWERSHELL_TOOL_NAMES:
        return
    tool_input = hook_payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    command = tool_input.get("command", "")
    if not isinstance(command, str):
        return
    all_gh_argument_lists = all_gh_call_argument_lists(command)
    if not all_gh_argument_lists:
        return
    deny_reason = _deny_reason(command, all_gh_argument_lists)
    if deny_reason is None:
        return
    log_hook_block(GATE_HOOK_NAME, HOOK_EVENT_NAME, deny_reason, str(tool_name), command)
    _write_deny_decision(deny_reason)


def _write_deny_decision(deny_reason: str) -> None:
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": HOOK_EVENT_NAME,
                    "permissionDecision": DENY_DECISION,
                    "permissionDecisionReason": deny_reason,
                }
            }
        )
    )
    sys.stdout.flush()


if __name__ == "__main__":
    main()
