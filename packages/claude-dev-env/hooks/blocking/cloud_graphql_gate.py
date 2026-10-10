#!/usr/bin/env python3
"""PreToolUse gate: keep cloud sessions from calling GitHub GraphQL.

The Claude Code cloud proxy answers every request to
``api.github.com/graphql`` with HTTP 403, an unauthenticated one included, so
no token or setting makes the call work there. Inside a cloud session, where
``CLAUDE_CODE_REMOTE`` is ``true``, a command segment that runs ``gh api
graphql`` or points an HTTP client such as ``curl`` at the GraphQL endpoint is
denied, and the deny reason names the REST routes that do the same jobs. The
program is read past wrappers and chained commands. Outside a cloud session the
gate stays quiet, because GraphQL works there.

Hosted by ``blocking/bash_pre_tool_use_dispatcher.py`` for the Bash and
PowerShell tools.
"""

from __future__ import annotations

import json
import os
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
        ALL_HTTP_CLIENT_PROGRAM_NAMES,
        CLOUD_GRAPHQL_DENY_REASON,
        CLOUD_SESSION_ENV_TRUE_VALUE,
        CLOUD_SESSION_ENV_VAR,
        GATE_HOOK_NAME,
        GH_GRAPHQL_COMMAND_PATH,
        GH_PROGRAM_NAME,
        GITHUB_GRAPHQL_ENDPOINT_FRAGMENT,
    )
    from hooks_constants.hook_block_logger import log_hook_block
    from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
    from hooks_constants.shell_command_pipeline import pipeline_segments_for_command
    from hooks_constants.shell_command_wrappers import (
        all_wrapped_command_texts,
        segment_program_and_arguments,
    )
except ImportError as import_error:
    raise ImportError(
        "The cloud GraphQL gate cannot import its dependencies; "
        "ensure the hooks directory is importable."
    ) from import_error


def _calls_github_graphql(all_segment_tokens: list[str]) -> bool:
    """Return True when a segment runs gh api graphql or sends an HTTP client to the endpoint.

    Args:
        all_segment_tokens: One command segment's shell tokens.
    """
    program_name, all_arguments = segment_program_and_arguments(all_segment_tokens)
    normalized_program_name = program_name.lower()
    if normalized_program_name == GH_PROGRAM_NAME:
        return tuple(all_arguments[: len(GH_GRAPHQL_COMMAND_PATH)]) == GH_GRAPHQL_COMMAND_PATH
    if normalized_program_name in ALL_HTTP_CLIENT_PROGRAM_NAMES:
        return any(
            GITHUB_GRAPHQL_ENDPOINT_FRAGMENT in each_argument.lower()
            for each_argument in all_arguments
        )
    return False


def calls_github_graphql(command: str) -> bool:
    """Return True when any command segment calls the GitHub GraphQL API.

    ::

        gh api graphql -f query='query{viewer{login}}'       -> True
        curl -X POST https://api.github.com/graphql -d @q    -> True
        gh api repos/o/r/pulls/1/ccr/review_threads          -> False
        grep -rn "api.github.com/graphql" scripts            -> False

    Args:
        command: The shell command text the agent is about to run.
    """
    return any(
        _calls_github_graphql(each_segment)
        for each_text in all_wrapped_command_texts(command)
        for each_segment, _each_following_operator in pipeline_segments_for_command(each_text)
    )


def is_cloud_session() -> bool:
    """Return True when this hook runs inside a Claude Code cloud session."""
    return os.environ.get(CLOUD_SESSION_ENV_VAR, "").strip().lower() == CLOUD_SESSION_ENV_TRUE_VALUE


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


if __name__ == "__main__":
    main()
