"""Build the files and folders one scope-boundary session runs in.

Each session gets a fresh git workspace copied from ``fixture/`` with the
variant's installed files on top. Every session reads one MCP config that
serves the ``request_decision`` stub and launches with this eval's flags.
"""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from session_eval_support.config.constants import ALL_GIT_INIT_COMMANDS
from session_eval_support.session import remove_workspace

from scope_eval_support.config.constants import (
    ALL_ALLOWED_TOOLS,
    ALL_DIFF_COMMAND_WORDS,
    ALL_INTENT_TO_ADD_COMMAND,
    ALL_STARTING_COMMIT_COMMAND,
    ALLOWED_TOOLS_FLAG,
    DECISION_SERVER_SCRIPT,
    FAILURE_DECISION_STUB,
    FIXTURE_DIGEST_PREFIX,
    FIXTURE_DIRECTORY,
    FLOW_ROOT,
    INIT_SUBTYPE,
    MCP_CONFIG_FILE_NAME,
    MCP_CONNECTED_STATUS,
    MCP_SERVER_NAME,
    PERMISSION_MODE,
    RESUME_FLAG,
    UNREADABLE_DIFF_TEXT,
    WORKSPACE_DIFF_CHARACTER_LIMIT,
    WORKSPACE_DIFF_TRUNCATION_NOTE,
    WORKSPACE_PREFIX,
)


def fixture_bytes() -> dict[str, bytes]:
    """Return the bytes of every fixture file, keyed for the run digest.

    ::

        fixture/README.md -> {"fixture/README.md": b"..."}

    Returns:
        Each fixture file's bytes under ``fixture/`` plus its relative path.
    """
    return {
        FIXTURE_DIGEST_PREFIX
        + each_path.relative_to(FIXTURE_DIRECTORY).as_posix(): each_path.read_bytes()
        for each_path in sorted(FIXTURE_DIRECTORY.rglob("*"))
        if each_path.is_file()
    }


def prepare_workspace(bytes_by_target: dict[str, bytes]) -> Path:
    """Copy the fixture to a new temporary folder, install files, and init git.

    The folder is removed again when any copy, write or git step fails.

    Args:
        bytes_by_target: Workspace-relative paths and the bytes to write there.

    Returns:
        The new workspace folder.

    Raises:
        OSError: A copy or write failed.
        subprocess.CalledProcessError: A git init command failed.
    """
    workspace = Path(tempfile.mkdtemp(prefix=WORKSPACE_PREFIX))
    try:
        shutil.copytree(FIXTURE_DIRECTORY, workspace, dirs_exist_ok=True)
        for each_target, each_bytes in bytes_by_target.items():
            target_path = workspace / each_target
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(each_bytes)
        for each_command in ALL_GIT_INIT_COMMANDS:
            subprocess.run(each_command, cwd=workspace, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        remove_workspace(workspace)
        raise
    return workspace


def cases_digest(all_cases: list[dict[str, str]]) -> str:
    """Return a sha256 hex over each selected case's id, prompt and setup turn.

    ::

        [{"id": "d01", "prompt": "Port it."}] -> "3f1c..."

    A changed prompt or setup turn changes the digest, so it starts fresh
    rows. A label edit leaves it alone; rejudge.py regrades those.

    Args:
        all_cases: The cases this run selected.

    Returns:
        The hex digest of the sorted JSON of ``[id, prompt, setup]`` per case.
    """
    all_case_texts = [
        [each_case["id"], each_case["prompt"], each_case.get("setup")]
        for each_case in all_cases
    ]
    return hashlib.sha256(
        json.dumps(all_case_texts, sort_keys=True).encode("utf-8")
    ).hexdigest()


def starting_commit(workspace: Path) -> str:
    """Return the commit a fresh workspace starts on.

    Args:
        workspace: A folder from prepare_workspace.

    Returns:
        The full sha of ``HEAD``.

    Raises:
        subprocess.CalledProcessError: git could not read ``HEAD``.
    """
    completed = subprocess.run(
        ALL_STARTING_COMMIT_COMMAND,
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _capped_diff(diff_text: str) -> str:
    if len(diff_text) <= WORKSPACE_DIFF_CHARACTER_LIMIT:
        return diff_text
    return diff_text[
        :WORKSPACE_DIFF_CHARACTER_LIMIT
    ] + WORKSPACE_DIFF_TRUNCATION_NOTE.format(limit=WORKSPACE_DIFF_CHARACTER_LIMIT)


def workspace_diff(workspace: Path, from_commit: str) -> str:
    """Return every file change in the workspace since a commit, as one diff.

    ::

        edited README.md, added notes.txt -> "diff --git a/README.md ...notes.txt..."

    Args:
        workspace: The folder the session ran in.
        from_commit: The commit from starting_commit.

    Returns:
        The diff text, cut to the character limit with a note when longer,
        or a note that the git record was unreadable when the session broke it.
    """
    try:
        subprocess.run(
            ALL_INTENT_TO_ADD_COMMAND, cwd=workspace, check=True, capture_output=True
        )
        completed = subprocess.run(
            [*ALL_DIFF_COMMAND_WORDS, from_commit],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
            errors="replace",
        )
    except subprocess.CalledProcessError:
        return UNREADABLE_DIFF_TEXT
    return _capped_diff(completed.stdout)


def scope_words(
    all_claude_words: list[str], mcp_config_path: Path, resume_session_id: str
) -> list[str]:
    """Return the ``claude`` command words with this eval's session flags added.

    ::

        ["claude", "-p"] -> ["claude", "-p", "--allowedTools", "Bash", ..., "--strict-mcp-config"]

    Args:
        all_claude_words: The base command words.
        mcp_config_path: The MCP config that serves the decision stub.
        resume_session_id: The setup turn's session id on a follow-up, else empty.

    Returns:
        The words with ``--resume <id>`` on a follow-up, Bash and the
        decision tool allowed, the
        permission mode, and the strict MCP config.
    """
    return [
        *all_claude_words,
        *([RESUME_FLAG, resume_session_id] if resume_session_id else []),
        ALLOWED_TOOLS_FLAG,
        *ALL_ALLOWED_TOOLS,
        "--permission-mode",
        PERMISSION_MODE,
        "--mcp-config",
        str(mcp_config_path),
        "--strict-mcp-config",
    ]


def write_mcp_config(variant_directory: Path) -> Path:
    """Write the MCP config that serves the decision stub to sessions.

    Args:
        variant_directory: The variant's output folder.

    Returns:
        The written config file path.
    """
    config_path = variant_directory / MCP_CONFIG_FILE_NAME
    server = {
        "command": sys.executable,
        "args": [str(DECISION_SERVER_SCRIPT)],
        "env": {"PYTHONPATH": str(FLOW_ROOT)},
    }
    config_path.write_text(
        json.dumps({"mcpServers": {MCP_SERVER_NAME: server}}), encoding="utf-8"
    )
    return config_path


def _init_event(all_events: list[dict[str, object]]) -> dict[str, object] | None:
    return next(
        (
            each_event
            for each_event in all_events
            if each_event.get("type") == "system"
            and each_event.get("subtype") == INIT_SUBTYPE
        ),
        None,
    )


def decision_stub_failure(
    all_events: list[dict[str, object]],
) -> tuple[str, object] | None:
    """Return a failure when the session started without the decision stub connected.

    The stream's ``system`` ``init`` event lists each MCP server and its
    status. A session whose ``thread`` server is missing or not connected
    could not post a card, so its asks would count text questions only.

    Args:
        all_events: The session's stream events.

    Returns:
        The failure class and the server statuses, or None when the stub connected.
    """
    init_event = _init_event(all_events)
    if init_event is None:
        return FAILURE_DECISION_STUB, None
    all_servers = init_event.get("mcp_servers") or []
    is_connected = any(
        each_server.get("name") == MCP_SERVER_NAME
        and each_server.get("status") == MCP_CONNECTED_STATUS
        for each_server in all_servers
    )
    return None if is_connected else (FAILURE_DECISION_STUB, all_servers)
