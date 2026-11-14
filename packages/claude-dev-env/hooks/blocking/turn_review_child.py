"""Start the review and judge runs for the turn review gate.

Each run is a separate ``claude -p`` process that starts in the checkout it
reads::

    review  ->  claude -p "/code-review low A..B"
    judge   ->  claude -p --model sonnet --effort high, prompt on stdin

The review and judge
runs carry ``CLAUDE_TURN_REVIEW_CHILD=1`` and none of the parent session's id,
messaging or ingress variables. Each may read
files and run ``git diff``, ``git show`` and ``git log``; every other tool is
denied. A run that times out, cannot start or ends with another exit code than
0 writes one log line and gives no output.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from hooks_constants.subprocess_window import hidden_window_creation_flags
from hooks_constants.turn_review_gate_constants import (
    ALL_PARENT_SESSION_VARIABLES,
    ALL_REVIEW_ALLOWED_TOOLS,
    ALL_REVIEW_DISALLOWED_TOOLS,
    JUDGE_EFFORT,
    JUDGE_MODEL_ALIAS,
    REVIEW_CHILD_ENVIRONMENT_VARIABLE,
    REVIEW_CHILD_MARKER,
    REVIEW_EFFORT,
    REVIEW_EXECUTABLE_NAME,
    REVIEW_MODEL_ALIAS,
    REVIEW_MODEL_EFFORT,
    REVIEW_PROMPT_TEMPLATE,
    REVIEW_SETTINGS_TEXT,
    REVIEW_SETTING_SOURCES_TEXT,
    REVIEW_TOOLS_TEXT,
)
from turn_review_state import _log


def _review_command(base_commit: str, turn_commit: str) -> list[str]:
    review_prompt = REVIEW_PROMPT_TEMPLATE.format(
        effort=REVIEW_EFFORT, base_commit=base_commit, turn_commit=turn_commit
    )
    return [
        shutil.which(REVIEW_EXECUTABLE_NAME) or REVIEW_EXECUTABLE_NAME,
        "-p",
        review_prompt,
        "--model",
        REVIEW_MODEL_ALIAS,
        "--effort",
        REVIEW_MODEL_EFFORT,
        *_read_only_child_options(),
    ]


def _judge_command() -> list[str]:
    return [
        shutil.which(REVIEW_EXECUTABLE_NAME) or REVIEW_EXECUTABLE_NAME,
        "-p",
        "--model",
        JUDGE_MODEL_ALIAS,
        "--effort",
        JUDGE_EFFORT,
        *_read_only_child_options(),
    ]


def _read_only_child_options() -> list[str]:
    return [
        "--output-format",
        "json",
        "--permission-mode",
        "dontAsk",
        "--setting-sources",
        REVIEW_SETTING_SOURCES_TEXT,
        "--tools",
        REVIEW_TOOLS_TEXT,
        "--no-session-persistence",
        "--allowedTools",
        *ALL_REVIEW_ALLOWED_TOOLS,
        "--disallowedTools",
        *ALL_REVIEW_DISALLOWED_TOOLS,
        "--settings",
        REVIEW_SETTINGS_TEXT,
    ]


def _review_environment() -> dict[str, str]:
    all_child_environment_variables = {
        each_name: each_value
        for each_name, each_value in os.environ.items()
        if each_name not in ALL_PARENT_SESSION_VARIABLES
    }
    all_child_environment_variables[REVIEW_CHILD_ENVIRONMENT_VARIABLE] = REVIEW_CHILD_MARKER
    return all_child_environment_variables


@dataclass(frozen=True)
class _ChildRun:
    repository_root: Path
    all_command_parts: list[str]
    prompt_text: str | None
    failure_template: str

    def write_failure(self, failure_text: str) -> None:
        _log(
            self.failure_template.format(
                repository=self.repository_root.name, reason=failure_text
            )
        )


def _child_stdout(child_run: _ChildRun, remaining_seconds: float) -> str | None:
    closed_stdin = subprocess.DEVNULL if child_run.prompt_text is None else None
    try:
        completed_process = subprocess.run(
            child_run.all_command_parts,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=remaining_seconds,
            cwd=str(child_run.repository_root),
            env=_review_environment(),
            creationflags=hidden_window_creation_flags(),
            stdin=closed_stdin,
            input=child_run.prompt_text,
        )
    except subprocess.TimeoutExpired:
        child_run.write_failure("timed out")
        return None
    except OSError as start_error:
        child_run.write_failure(str(start_error))
        return None
    if completed_process.returncode != 0:
        child_run.write_failure(f"exit {completed_process.returncode}")
        return None
    return completed_process.stdout
