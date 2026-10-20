#!/usr/bin/env python3
"""PostToolUse context reminder: own the review loop on a new owned pull request.

This hook never blocks. It runs after a shell call or a GitHub MCP
``create_pull_request`` call. When that call opened a pull request on a
repository we own, and the repository is not on the preset list of
repositories that run their own automated review, it adds one instruction
block to the agent's context::

    === OWNED PR REVIEW LOOP (context reminder, never a block) ===
    You opened jl-cmd-projects/claude-dev-env#42  https://github.com/...
    1. Review loop. Load the efficient-review skill ...
    2. Mark ready. ...
    3. Babysit. Follow the pstack babysit playbook ...
    4. Ship. Follow the pstack shipping playbook ...

Each reported pull request also goes into the session record, so the owned
pull request Stop gate holds the turn until it merges.

The pull request URL in the tool response is the proof that a pull request
opened, so the hook needs no network call and reads the same on Claude Code
and Codex.

Quiet branches: another tool, a shell command that opens no pull request,
a harness-reported non-zero exit, a response that says the pull request
already exists, a response with no pull request URL, an owner outside the
owned set, and a preset repository each emit nothing.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

try:
    _hooks_root_directory = str(Path(__file__).resolve().parent.parent)
    if _hooks_root_directory not in sys.path:
        sys.path.insert(0, _hooks_root_directory)
    from hooks_constants.bash_post_call_dispatcher_constants import (
        EXIT_CODE_ERROR_PREFIX,
    )
    from hooks_constants.owned_pr_review_loop_constants import (
        ALL_DECLARED_URL_KEYS,
        ALL_GH_API_BODY_OPTIONS,
        ALL_GH_API_METHOD_OPTIONS,
        ALL_GH_API_SHORT_OPTIONS,
        ALL_GH_PR_CREATE_ACTIONS,
        ALL_MCP_CREATE_PULL_REQUEST_TOOL_SUFFIXES,
        ALL_OWNED_OWNER_DIGESTS,
        ALL_PRESET_REPOSITORY_DIGESTS,
        ALL_SHELL_COMMAND_INPUT_KEYS,
        ALL_SHELL_TOOL_NAMES,
        ALREADY_EXISTS_MARKER,
        GH_API_POST_METHOD,
        GH_API_PULLS_ENDPOINT_PATTERN,
        GH_API_SUBCOMMAND,
        GH_LONG_OPTION_PREFIX,
        GH_OPTION_VALUE_SEPARATOR,
        GH_PR_SUBCOMMAND,
        GH_PROGRAM_NAME,
        GH_SHORT_OPTION_LENGTH,
        JSON_OBJECT_OPENER,
        MCP_OWNER_INPUT_KEY,
        MCP_REPOSITORY_INPUT_KEY,
        MCP_TOOL_NAME_PREFIX,
        NAME_DIGEST_TEXT_ENCODING,
        PULL_REQUEST_URL_PATTERN,
        REVIEW_LOOP_CONTEXT_TEMPLATE,
        SHELL_ARGUMENT_SEPARATOR,
    )
    from hooks_constants.post_tool_use_context import (
        write_post_tool_use_context_to_stdout,
    )
    from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
    from hooks_constants.pull_request_proof_constants import (
        ALL_PYTHON_PROGRAM_NAMES,
        PULL_REQUEST_SCRIPT_CREATE_WORD,
        PULL_REQUEST_SCRIPT_NAME,
    )
    from hooks_constants.pytest_invocation import unquoted_token
    from hooks_constants.shell_command_segments import (
        command_tokens,
        split_into_segments,
        token_basename,
    )
    from hooks_constants.shell_command_wrappers import (
        all_wrapped_command_texts,
        segment_program_and_arguments,
    )
    from owned_pr_session_record import record_pull_request
except ImportError as import_error:
    raise ImportError(
        "owned_pr_review_loop: cannot import its dependencies; "
        "ensure the hooks directory is importable."
    ) from import_error


def _is_gh_pr_create(all_arguments: list[str]) -> bool:
    return (
        all_arguments[:1] == [GH_PR_SUBCOMMAND]
        and len(all_arguments) > 1
        and all_arguments[1] in ALL_GH_PR_CREATE_ACTIONS
    )


def _option_name_and_inline_value(argument: str) -> tuple[str, str | None]:
    if argument.startswith(GH_LONG_OPTION_PREFIX):
        option_name, separator, inline_value = argument.partition(GH_OPTION_VALUE_SEPARATOR)
        return option_name, inline_value if separator else None
    short_option_name = argument[:GH_SHORT_OPTION_LENGTH]
    if short_option_name in ALL_GH_API_SHORT_OPTIONS and len(argument) > GH_SHORT_OPTION_LENGTH:
        return short_option_name, argument[GH_SHORT_OPTION_LENGTH:]
    return argument, None


def _is_gh_api_pulls_post(all_arguments: list[str]) -> bool:
    if all_arguments[:1] != [GH_API_SUBCOMMAND]:
        return False
    if not any(
        GH_API_PULLS_ENDPOINT_PATTERN.fullmatch(each_argument) for each_argument in all_arguments
    ):
        return False
    explicit_method: str | None = None
    sends_body = False
    all_following_arguments = [*all_arguments[1:], ""]
    for each_argument, each_following_argument in zip(all_arguments, all_following_arguments, strict=True):
        option_name, inline_value = _option_name_and_inline_value(each_argument)
        if option_name in ALL_GH_API_BODY_OPTIONS:
            sends_body = True
        if option_name in ALL_GH_API_METHOD_OPTIONS:
            explicit_method = inline_value or each_following_argument
    if explicit_method:
        return explicit_method.upper() == GH_API_POST_METHOD
    return sends_body


def _is_pull_request_script_create(program_name: str, all_arguments: list[str]) -> bool:
    all_script_arguments = all_arguments
    if program_name != PULL_REQUEST_SCRIPT_NAME:
        if program_name not in ALL_PYTHON_PROGRAM_NAMES or not all_arguments:
            return False
        if token_basename(unquoted_token(all_arguments[0])) != PULL_REQUEST_SCRIPT_NAME:
            return False
        all_script_arguments = all_arguments[1:]
    return all_script_arguments[:1] == [PULL_REQUEST_SCRIPT_CREATE_WORD]


def _segment_opens_pull_request(all_segment_tokens: list[str]) -> bool:
    program_name, all_arguments = segment_program_and_arguments(all_segment_tokens)
    if _is_pull_request_script_create(program_name, all_arguments):
        return True
    return program_name == GH_PROGRAM_NAME and (
        _is_gh_pr_create(all_arguments) or _is_gh_api_pulls_post(all_arguments)
    )


def command_creates_pull_request(command: str) -> bool:
    """Return True when any segment of the shell command opens a pull request.

    Four shapes count::

        gh pr create --fill
        gh pr new --fill
        gh api repos/acme/widgets/pulls --input pr.json
        python ~/.agents/skills/pull-request/scripts/pull_request.py create --repo acme/widgets

    The publisher counts when ``python``, ``python3``, or ``py`` runs a
    script named ``pull_request.py`` with ``create``, or the script runs
    alone.

    A ``gh api`` call counts only when it targets the pulls collection. An
    explicit method (``-X POST``, ``-XPOST``, ``--method=POST``) decides
    alone. With no method, a body (``-f``, ``-F``, ``--field``,
    ``--raw-field``, ``--input``, or the ``--name=value`` and ``-ftitle=t``
    forms) means
    POST, as it does for ``gh``. A ``pwsh -Command "..."``
    wrapper is unwrapped and its inner text scanned the same way.

    Args:
        command: The shell command text the agent ran.
    """
    return any(
        _segment_opens_pull_request(each_segment)
        for each_command_text in all_wrapped_command_texts(command)
        for each_segment in split_into_segments(command_tokens(each_command_text))
    )


def _is_mcp_create_pull_request(tool_name: str) -> bool:
    return tool_name.startswith(MCP_TOOL_NAME_PREFIX) and tool_name.endswith(
        ALL_MCP_CREATE_PULL_REQUEST_TOOL_SUFFIXES
    )


def _shell_command(all_tool_input: dict[str, object]) -> str:
    for each_key in ALL_SHELL_COMMAND_INPUT_KEYS:
        command = all_tool_input.get(each_key)
        if isinstance(command, str):
            return command
        if isinstance(command, list) and all(isinstance(each, str) for each in command):
            return SHELL_ARGUMENT_SEPARATOR.join(command)
    return ""


def _response_text(tool_response: object) -> str:
    if isinstance(tool_response, str):
        return tool_response
    return json.dumps(tool_response)


def tool_call_opens_pull_request(tool_name: str, all_tool_input: dict[str, object]) -> bool:
    """Return True when the tool call is a pull request creation.

    Args:
        tool_name: The tool name from the hook payload, such as ``Bash``,
            ``exec_command``, or ``mcp__github__create_pull_request``.
        all_tool_input: The tool input from the hook payload.
    """
    if _is_mcp_create_pull_request(tool_name):
        return True
    if tool_name in ALL_SHELL_TOOL_NAMES:
        return command_creates_pull_request(_shell_command(all_tool_input))
    return False


def _matches_for_input_repository(
    all_url_matches: list[re.Match[str]], all_tool_input: dict[str, object]
) -> list[re.Match[str]]:
    input_owner = str(all_tool_input.get(MCP_OWNER_INPUT_KEY) or "").lower()
    input_repository = str(all_tool_input.get(MCP_REPOSITORY_INPUT_KEY) or "").lower()
    if not (input_owner and input_repository):
        return all_url_matches
    return [
        each_match
        for each_match in all_url_matches
        if each_match["owner"].lower() == input_owner
        and each_match["repository"].lower() == input_repository
    ]


def _parsed_json_object_text(text: str) -> object:
    stripped_text = text.strip()
    if not stripped_text.startswith(JSON_OBJECT_OPENER):
        return None
    try:
        return json.loads(stripped_text)
    except json.JSONDecodeError:
        return None


def _all_declared_url_matches(response_value: object) -> list[re.Match[str]]:
    if isinstance(response_value, str):
        return _all_declared_url_matches(_parsed_json_object_text(response_value))
    if isinstance(response_value, list):
        return [
            each_match
            for each_item in response_value
            for each_match in _all_declared_url_matches(each_item)
        ]
    if not isinstance(response_value, dict):
        return []
    all_own_matches = [
        PULL_REQUEST_URL_PATTERN.fullmatch(str(response_value.get(each_key) or ""))
        for each_key in ALL_DECLARED_URL_KEYS
    ]
    return [each_match for each_match in all_own_matches if each_match] + [
        each_match
        for each_child in response_value.values()
        for each_match in _all_declared_url_matches(each_child)
    ]


def _scanned_url_match(
    all_tool_input: dict[str, object], tool_response: object
) -> re.Match[str] | None:
    response_text = _response_text(tool_response)
    if response_text.startswith(EXIT_CODE_ERROR_PREFIX):
        return None
    if ALREADY_EXISTS_MARKER in response_text.lower():
        return None
    all_url_matches = _matches_for_input_repository(
        list(PULL_REQUEST_URL_PATTERN.finditer(response_text)), all_tool_input
    )
    return all_url_matches[-1] if all_url_matches else None


def opened_pull_request(
    all_tool_input: dict[str, object], tool_response: object
) -> dict[str, str] | None:
    """Return the owner, repository, number, and url of the opened pull request.

    A JSON response declares the new pull request in an ``html_url`` or
    ``url`` field, as the REST API and the MCP tools do. That field wins over
    any URL the body cites. With no declared field, the hook scans the text
    and takes the last URL, since ``gh pr create`` prints it last; a non-zero
    exit or an "already exists" notice then means no new pull request. When
    the tool input names an owner and a repository, only a URL for that
    repository counts.

    Args:
        all_tool_input: The tool input from the hook payload.
        tool_response: The tool response from the hook payload.

    Returns:
        The pull request fields, or None when the response shows no new pull
        request.
    """
    all_declared_matches = _matches_for_input_repository(
        _all_declared_url_matches(tool_response), all_tool_input
    )
    url_match = next(iter(all_declared_matches), None)
    url_match = url_match or _scanned_url_match(all_tool_input, tool_response)
    if url_match is None:
        return None
    return {**url_match.groupdict(), "url": url_match.group(0)}


def name_digest(name: str) -> str:
    """Return the SHA-256 digest of a name in its normalized form.

    Normalizing keeps only ASCII letters and digits in lower case, so
    ``"Acme-Widgets/tools"`` and ``"acmewidgetstools"`` share one digest.

    Args:
        name: An owner name or an ``owner/repository`` full name.
    """
    normalized_name = "".join(
        each_character
        for each_character in name.lower()
        if each_character.isascii() and each_character.isalnum()
    )
    return hashlib.sha256(normalized_name.encode(NAME_DIGEST_TEXT_ENCODING)).hexdigest()


def needs_review_loop(
    owner: str,
    repository: str,
    all_owned_owner_digests: frozenset[str],
    all_preset_repository_digests: frozenset[str],
) -> bool:
    """Return True for an owned repository outside the preset review list.

    Args:
        owner: The GitHub owner of the repository.
        repository: The repository name.
        all_owned_owner_digests: Digests of the owners we own.
        all_preset_repository_digests: Digests of the ``owner/repository``
            names that run their own automated review.
    """
    return (
        name_digest(owner) in all_owned_owner_digests
        and name_digest(f"{owner}/{repository}") not in all_preset_repository_digests
    )


def build_review_loop_context(all_pull_request_fields: dict[str, str]) -> str:
    """Build the review-loop instruction block for one opened pull request.

    Args:
        all_pull_request_fields: The owner, repository, number, and url fields.
    """
    return REVIEW_LOOP_CONTEXT_TEMPLATE.format(**all_pull_request_fields)


def main() -> None:
    """Add the review-loop instructions after a pull request opens on an owned repository.

    Reads the PostToolUse payload from stdin. The pull request also goes into
    the session record that the owned pull request Stop gate reads. Every quiet branch returns with
    no output, so this hook can never alter or block a tool call.
    """
    hook_payload = read_hook_input_dictionary_from_stdin()
    if hook_payload is None:
        return
    tool_name = str(hook_payload.get("tool_name") or "")
    tool_input = hook_payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    if not tool_call_opens_pull_request(tool_name, tool_input):
        return
    pull_request = opened_pull_request(tool_input, hook_payload.get("tool_response"))
    if pull_request is None:
        return
    if not needs_review_loop(
        pull_request["owner"],
        pull_request["repository"],
        ALL_OWNED_OWNER_DIGESTS,
        ALL_PRESET_REPOSITORY_DIGESTS,
    ):
        return
    record_pull_request(hook_payload.get("session_id"), pull_request)
    write_post_tool_use_context_to_stdout(build_review_loop_context(pull_request))


if __name__ == "__main__":
    main()
