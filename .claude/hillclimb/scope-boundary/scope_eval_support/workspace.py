"""Build the files and folders one scope-boundary session runs in.

Each session gets a fresh git workspace copied from ``fixture/`` with the
variant's installed files on top. Every session reads one MCP config that
serves the ``request_decision`` stub and launches with this eval's flags.
"""

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
    ALLOWED_TOOLS_FLAG,
    DECISION_SERVER_SCRIPT,
    FIXTURE_DIGEST_PREFIX,
    FIXTURE_DIRECTORY,
    FLOW_ROOT,
    MCP_CONFIG_FILE_NAME,
    MCP_SERVER_NAME,
    PERMISSION_MODE,
    RESUME_FLAG,
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
