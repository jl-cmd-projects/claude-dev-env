#!/usr/bin/env python3
"""PreToolUse gate: keep cloud sessions from calling GitHub GraphQL.

The Claude Code cloud proxy answers every request to
``api.github.com/graphql`` with HTTP 403, an unauthenticated one included, so
no token or setting makes the call work there. Inside a cloud session, where
``CLAUDE_CODE_REMOTE`` is ``true``, a command segment is denied when it runs
a ``gh`` command that calls GraphQL or points an HTTP client such as ``curl``
at the GraphQL endpoint. The deny reason names the REST routes that do the same
jobs. ``gh`` calls GraphQL for ``api graphql``, for every ``pr``, ``issue``,
``project`` and ``discussion`` subcommand except ``pr diff`` and ``pr list
--web``, and for ``status``, ``org list``, ``repo view``, ``repo clone``,
``repo list``, ``repo archive``, ``repo unarchive``, ``label list``, ``search
prs``, ``search issues``, ``ruleset list``, ``gist list``, ``release list``,
``release view`` with a tag, and ``workflow run`` without ``--ref``. ``repo
edit``, ``repo create`` and ``repo sync`` call GraphQL only for some flags (an
interactive edit, ``--template``, no ``--branch``), so they pass. The command
words skip options and the values of ``-R``, ``--json`` and the like, so ``gh -R o/r pr list``
and ``gh api -X POST graphql`` read as ``pr list`` and ``api graphql``. A
``gh`` call with ``--help`` or ``-h`` passes, because it reaches no network,
unless the flag is the separate value of an option such as ``--body``. An HTTP client or a script
interpreter such as ``python -c`` is denied when an argument names
``api.github.com/graphql``, with or without a port. A URL held in a shell
variable, or built inside a script file, is not in the command text, so the
gate cannot see it. The program is read past wrappers, shell keywords such as
``if`` and ``!``, command substitutions and chained commands. Outside a cloud
session the gate stays quiet, because GraphQL works there.

Hosted by ``blocking/bash_pre_tool_use_dispatcher.py`` for the Bash and
PowerShell tools.
"""

from __future__ import annotations

import json
import sys
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
        ALL_GH_COMMAND_PATHS_CALLING_GRAPHQL_WITH_AN_OPERAND,
        ALL_GH_GRAPHQL_COMMAND_GROUPS,
        ALL_GH_GRAPHQL_COMMAND_PATHS,
        ALL_GH_HELP_FLAGS,
        ALL_GH_REST_COMMAND_PATHS_IN_GRAPHQL_GROUPS,
        ALL_GH_REST_OPTIONS_BY_COMMAND_PATH,
        ALL_HTTP_CLIENT_PROGRAM_NAMES,
        ALL_SCRIPT_INTERPRETER_PROGRAM_NAMES,
        CLOUD_GRAPHQL_DENY_REASON,
        GATE_HOOK_NAME,
        GH_API_SUBCOMMAND,
        GH_COMMAND_PATH_LENGTH,
        GH_ENDPOINT_PATH_SEPARATOR,
        GH_GRAPHQL_ENDPOINT,
        GH_PROGRAM_NAME,
        GITHUB_GRAPHQL_ENDPOINT_PATTERN,
    )
    from hooks_constants.cloud_session import is_cloud_session
    from hooks_constants.gh_command_words import gh_command_words, gh_standalone_options
    from hooks_constants.hook_block_logger import log_hook_block
    from hooks_constants.piped_pytest_blocker_constants import PYTHON_INTERPRETER_BASENAME_PATTERN
    from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
    from hooks_constants.shell_command_wrappers import (
        all_wrapped_command_segments,
        segment_program_and_arguments,
    )
except ImportError as import_error:
    raise ImportError(
        "The cloud GraphQL gate cannot import its dependencies; "
        "ensure the hooks directory is importable."
    ) from import_error


def _is_graphql_endpoint(endpoint: str) -> bool:
    """Return True when a ``gh api`` endpoint word is ``graphql``, ``/graphql`` or the full URL."""
    return (
        endpoint.strip(GH_ENDPOINT_PATH_SEPARATOR).lower() == GH_GRAPHQL_ENDPOINT
        or GITHUB_GRAPHQL_ENDPOINT_PATTERN.search(endpoint) is not None
    )


def _gh_arguments_call_graphql(all_arguments: list[str]) -> bool:
    """Return True when gh, run with these arguments, sends a GraphQL request.

    Args:
        all_arguments: The tokens after the ``gh`` program name.
    """
    all_option_names = gh_standalone_options(all_arguments)
    if any(each_option in ALL_GH_HELP_FLAGS for each_option in all_option_names):
        return False
    all_command_words = gh_command_words(all_arguments)
    if all_command_words[:1] == [GH_API_SUBCOMMAND]:
        return any(_is_graphql_endpoint(each_word) for each_word in all_command_words[1:])
    command_path = tuple(all_command_words[:GH_COMMAND_PATH_LENGTH])
    all_rest_options = ALL_GH_REST_OPTIONS_BY_COMMAND_PATH.get(command_path, frozenset())
    if any(each_option in all_rest_options for each_option in all_option_names):
        return False
    if command_path in ALL_GH_COMMAND_PATHS_CALLING_GRAPHQL_WITH_AN_OPERAND:
        return len(all_command_words) > GH_COMMAND_PATH_LENGTH
    if any(
        command_path[: len(each_path)] == each_path for each_path in ALL_GH_GRAPHQL_COMMAND_PATHS
    ):
        return True
    return (
        len(command_path) == GH_COMMAND_PATH_LENGTH
        and command_path[0] in ALL_GH_GRAPHQL_COMMAND_GROUPS
        and command_path not in ALL_GH_REST_COMMAND_PATHS_IN_GRAPHQL_GROUPS
    )


def _calls_github_graphql(all_segment_tokens: list[str]) -> bool:
    """Return True when a segment runs a GraphQL gh command or sends an HTTP client to the endpoint.

    Args:
        all_segment_tokens: One command segment's shell tokens.
    """
    program_name, all_arguments = segment_program_and_arguments(all_segment_tokens)
    normalized_program_name = program_name.lower()
    if normalized_program_name == GH_PROGRAM_NAME:
        return _gh_arguments_call_graphql(all_arguments)
    if (
        normalized_program_name in ALL_HTTP_CLIENT_PROGRAM_NAMES
        or normalized_program_name in ALL_SCRIPT_INTERPRETER_PROGRAM_NAMES
        or PYTHON_INTERPRETER_BASENAME_PATTERN.fullmatch(normalized_program_name) is not None
    ):
        return any(
            GITHUB_GRAPHQL_ENDPOINT_PATTERN.search(each_argument) is not None
            for each_argument in all_arguments
        )
    return False


def calls_github_graphql(command: str) -> bool:
    """Return True when any command segment calls the GitHub GraphQL API.

    ::

        gh api graphql -f query='query{viewer{login}}'       -> True
        gh pr create --title t --body-file b.md              -> True
        gh api -X POST graphql -f query='query{viewer{login}}' -> True
        gh -R o/r pr list                                    -> True
        curl -X POST https://api.github.com/graphql -d @q    -> True
        gh api repos/o/r/pulls/1/ccr/review_threads          -> False
        gh pr diff 12                                        -> False
        gh pr list --web                                     -> False
        grep -rn "api.github.com/graphql" scripts            -> False

    Args:
        command: The shell command text the agent is about to run.
    """
    return any(
        _calls_github_graphql(each_segment)
        for each_segment in all_wrapped_command_segments(command)
    )


def _write_deny_decision() -> None:
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": HOOK_EVENT_NAME,
                    "permissionDecision": DENY_DECISION,
                    "permissionDecisionReason": CLOUD_GRAPHQL_DENY_REASON,
                }
            }
        )
    )
    sys.stdout.flush()


def main() -> None:
    """Deny a GitHub GraphQL call inside a cloud session, or stay quiet."""
    if not is_cloud_session():
        return
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
    if not isinstance(command, str) or not calls_github_graphql(command):
        return
    log_hook_block(
        GATE_HOOK_NAME, HOOK_EVENT_NAME, CLOUD_GRAPHQL_DENY_REASON, str(tool_name), command
    )
    _write_deny_decision()


if __name__ == "__main__":
    main()
