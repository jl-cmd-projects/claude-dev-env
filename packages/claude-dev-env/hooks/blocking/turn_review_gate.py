#!/usr/bin/env python3
"""Stop hook that has a fresh reviewer read each turn's changes before the turn ends.

The agent edits ``src/service.py`` and drops a retry. When the turn stops, a
separate ``claude -p`` run reviews only that turn's edits with
``/code-review low`` and the hook holds the stop with what it found::

    prompt arrives  ->  snapshot A of the working tree
    agent edits     ->  src/service.py loses @with_retry
    stop            ->  snapshot B (parent A), claude -p "/code-review low A..B"
                    ->  block: "src/service.py:208 - The diff removes ..."
    agent fixes it  ->  stop reviews B..C only, finds nothing, the turn ends

``turn_review_snapshot`` builds the snapshots, and ``turn_review_findings``
reads the findings out of the review text. Edits the user left before the
prompt sit in snapshot A, so the review sees only the agent's work. Each stop
moves the baseline to the snapshot it took, so the stop after a block reviews
only the fix.

A repository takes part when it is the session's project folder or a folder
directly inside it, and its GitHub origin ``owner/repo`` slug is listed in
``CLAUDE_TURN_REVIEW_REPOSITORIES``. The hook holds a stop at most three times
in a row, skips a turn that changed more than 30 files, and lets the stop
through when the review fails or times out; a new prompt resets the count.
These are the limits of Anthropic's security-guidance plugin. The review run
carries ``CLAUDE_TURN_REVIEW_CHILD=1`` and none of the parent session's id,
messaging or ingress variables, and the hook does nothing inside such a run. The review may read
files and run ``git diff``, ``git show`` and ``git log``; every other tool is
denied.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from atomic_file_writer import write_text_atomically
from hooks_constants.atomic_file_writer_constants import ATOMIC_WRITE_TEMPORARY_SUFFIX
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.session_file_id import session_file_id
from hooks_constants.subprocess_window import hidden_window_creation_flags
from hooks_constants.turn_review_gate_constants import (
    ALL_PARENT_SESSION_VARIABLES,
    ALL_REVIEW_ALLOWED_TOOLS,
    ALL_REVIEW_DISALLOWED_TOOLS,
    BASELINE_COMMIT_PATTERN,
    BLOCK_DECISION,
    BLOCK_REASON_TEMPLATE,
    DECISION_KEY,
    FINDING_LINE_SEPARATOR,
    GIT_DIRECTORY_NAME,
    HOOK_EVENT_NAME_KEY,
    MAXIMUM_BLOCKS_IN_A_ROW,
    MAXIMUM_TURN_FILES,
    PROJECT_DIRECTORY_ENVIRONMENT_VARIABLE,
    PROMPT_EVENT_NAME,
    REASON_KEY,
    REPOSITORIES_ENVIRONMENT_VARIABLE,
    REPOSITORY_FINDINGS_SEPARATOR,
    REPOSITORY_FINDINGS_TEMPLATE,
    REPOSITORY_SEPARATOR,
    REVIEW_CHILD_ENVIRONMENT_VARIABLE,
    REVIEW_CHILD_MARKER,
    REVIEW_EFFORT,
    REVIEW_FAILURE_DIAGNOSTIC_TEMPLATE,
    REVIEW_MODEL_ALIAS,
    REVIEW_PROMPT_TEMPLATE,
    REVIEW_RESULT_KEY,
    REVIEW_EXECUTABLE_NAME,
    REVIEW_SETTING_SOURCES_TEXT,
    REVIEW_SETTINGS_TEXT,
    MINIMUM_REVIEW_SECONDS,
    REVIEW_TIMEOUT_SECONDS,
    REVIEW_TOOLS_TEXT,
    SESSION_ID_KEY,
    STATE_BASELINES_KEY,
    STATE_BLOCKS_KEY,
    STATE_FILE_TEMPLATE,
    STATE_TEMPORARY_PREFIX,
    STATE_TEXT_ENCODING,
    STOP_EVENT_NAME,
    TOO_MANY_FILES_DIAGNOSTIC_TEMPLATE,
)
from pii_prevention_blocker_parts.repository_exemption import repository_origin_slug
from turn_review_findings import finding_lines
from turn_review_snapshot import turn_changed_paths, working_tree_snapshot


def _opted_in_repository_slugs() -> frozenset[str]:
    listed = os.environ.get(REPOSITORIES_ENVIRONMENT_VARIABLE, "")
    return frozenset(
        each.strip().casefold() for each in listed.split(REPOSITORY_SEPARATOR) if each.strip()
    )


def _opted_in_repository_roots(all_slugs: frozenset[str]) -> list[Path]:
    project_directory = os.environ.get(PROJECT_DIRECTORY_ENVIRONMENT_VARIABLE, "")
    if not project_directory or not Path(project_directory).is_dir():
        return []
    project_path = Path(project_directory).resolve()
    all_candidates = [project_path, *sorted(_child_entries(project_path))]
    return [each for each in all_candidates if _is_opted_in_checkout(each, all_slugs)]


def _child_entries(project_path: Path) -> list[Path]:
    try:
        return list(project_path.iterdir())
    except OSError:
        return []


def _is_opted_in_checkout(folder: Path, all_slugs: frozenset[str]) -> bool:
    try:
        is_checkout = folder.is_dir() and (folder / GIT_DIRECTORY_NAME).exists()
    except OSError:
        return False
    return is_checkout and repository_origin_slug(folder) in all_slugs


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


def _write_review_failure(repository_root: Path, failure_text: str) -> None:
    sys.stderr.write(
        REVIEW_FAILURE_DIAGNOSTIC_TEMPLATE.format(
            repository=repository_root.name, reason=failure_text
        )
    )


def _review_stdout(
    repository_root: Path, base_commit: str, turn_commit: str, remaining_seconds: float
) -> str | None:
    try:
        completed_process = subprocess.run(
            _review_command(base_commit, turn_commit),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=remaining_seconds,
            cwd=str(repository_root),
            env=_review_environment(),
            creationflags=hidden_window_creation_flags(),
        )
    except subprocess.TimeoutExpired:
        _write_review_failure(repository_root, "timed out")
        return None
    except OSError as start_error:
        _write_review_failure(repository_root, str(start_error))
        return None
    if completed_process.returncode != 0:
        _write_review_failure(repository_root, f"exit {completed_process.returncode}")
        return None
    return completed_process.stdout


def _review_text(
    repository_root: Path, base_commit: str, turn_commit: str, review_deadline: float
) -> str | None:
    remaining_seconds = review_deadline - time.monotonic()
    if remaining_seconds < MINIMUM_REVIEW_SECONDS:
        _write_review_failure(repository_root, "no review time left this stop")
        return None
    review_stdout = _review_stdout(repository_root, base_commit, turn_commit, remaining_seconds)
    if review_stdout is None:
        return None
    try:
        review_result = json.loads(review_stdout)
    except ValueError:
        _write_review_failure(repository_root, "output was not JSON")
        return None
    review_text = review_result.get(REVIEW_RESULT_KEY) if isinstance(review_result, dict) else None
    if not isinstance(review_text, str):
        _write_review_failure(repository_root, "output had no result text")
        return None
    return review_text


def _state_path(session_id: object) -> Path:
    return Path(tempfile.gettempdir()) / STATE_FILE_TEMPLATE.format(
        session_id=session_file_id(session_id)
    )


def _load_state(session_id: object) -> tuple[dict[str, str], int]:
    try:
        saved_state = json.loads(_state_path(session_id).read_text(encoding=STATE_TEXT_ENCODING))
    except (OSError, ValueError):
        return {}, 0
    if not isinstance(saved_state, dict):
        return {}, 0
    raw_baselines = saved_state.get(STATE_BASELINES_KEY)
    all_baselines = {
        each_root: each_commit
        for each_root, each_commit in (
            raw_baselines.items() if isinstance(raw_baselines, dict) else []
        )
        if isinstance(each_root, str)
        and isinstance(each_commit, str)
        and re.fullmatch(BASELINE_COMMIT_PATTERN, each_commit)
    }
    raw_blocks = saved_state.get(STATE_BLOCKS_KEY)
    return all_baselines, raw_blocks if isinstance(raw_blocks, int) else 0


def _save_state(session_id: object, all_baselines: dict[str, str], blocks_in_a_row: int) -> None:
    write_text_atomically(
        _state_path(session_id),
        json.dumps({STATE_BASELINES_KEY: all_baselines, STATE_BLOCKS_KEY: blocks_in_a_row}),
        STATE_TEXT_ENCODING,
        STATE_TEMPORARY_PREFIX,
        ATOMIC_WRITE_TEMPORARY_SUFFIX,
        False,
    )


def _record_prompt_baselines(session_id: object, all_roots: list[Path]) -> None:
    all_baselines = {}
    for each_root in all_roots:
        snapshot_commit = working_tree_snapshot(each_root, None)
        if snapshot_commit is not None:
            all_baselines[str(each_root)] = snapshot_commit
    _save_state(session_id, all_baselines, 0)


def _repository_findings(
    repository_root: Path, base_commit: str, turn_commit: str, review_deadline: float
) -> str | None:
    all_changed_paths = turn_changed_paths(repository_root, base_commit, turn_commit)
    if len(all_changed_paths) > MAXIMUM_TURN_FILES:
        sys.stderr.write(
            TOO_MANY_FILES_DIAGNOSTIC_TEMPLATE.format(
                repository=repository_root.name,
                count=len(all_changed_paths),
                limit=MAXIMUM_TURN_FILES,
            )
        )
        return None
    if not all_changed_paths:
        return None
    review_text = _review_text(repository_root, base_commit, turn_commit, review_deadline)
    all_finding_lines = finding_lines(review_text or "", all_changed_paths)
    if not all_finding_lines:
        return None
    return REPOSITORY_FINDINGS_TEMPLATE.format(
        repository=repository_root.name,
        findings=FINDING_LINE_SEPARATOR.join(all_finding_lines),
    )


def _turn_block_reason(session_id: object, all_roots: list[Path]) -> str | None:
    all_baselines, blocks_in_a_row = _load_state(session_id)
    all_next_baselines: dict[str, str] = {}
    all_findings: list[str] = []
    review_deadline = time.monotonic() + REVIEW_TIMEOUT_SECONDS
    for each_root in all_roots:
        base_commit = all_baselines.get(str(each_root))
        turn_commit = working_tree_snapshot(each_root, base_commit)
        if turn_commit is None:
            continue
        all_next_baselines[str(each_root)] = turn_commit
        if base_commit is None or blocks_in_a_row >= MAXIMUM_BLOCKS_IN_A_ROW:
            continue
        repository_findings = _repository_findings(
            each_root, base_commit, turn_commit, review_deadline
        )
        if repository_findings is not None:
            all_findings.append(repository_findings)
    if all_findings:
        blocks_in_a_row += 1
    elif blocks_in_a_row < MAXIMUM_BLOCKS_IN_A_ROW:
        blocks_in_a_row = 0
    _save_state(session_id, all_next_baselines, blocks_in_a_row)
    if not all_findings:
        return None
    return BLOCK_REASON_TEMPLATE.format(
        all_findings=REPOSITORY_FINDINGS_SEPARATOR.join(all_findings)
    )


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return 0
    if os.environ.get(REVIEW_CHILD_ENVIRONMENT_VARIABLE) == REVIEW_CHILD_MARKER:
        return 0
    all_slugs = _opted_in_repository_slugs()
    if not all_slugs:
        return 0
    all_roots = _opted_in_repository_roots(all_slugs)
    if not all_roots:
        return 0
    session_id = hook_input.get(SESSION_ID_KEY)
    hook_event_name = hook_input.get(HOOK_EVENT_NAME_KEY)
    if hook_event_name == PROMPT_EVENT_NAME:
        _record_prompt_baselines(session_id, all_roots)
        return 0
    if hook_event_name != STOP_EVENT_NAME:
        return 0
    block_reason = _turn_block_reason(session_id, all_roots)
    if block_reason is None:
        return 0
    log_hook_block(Path(__file__).name, STOP_EVENT_NAME, block_reason)
    sys.stdout.write(json.dumps({DECISION_KEY: BLOCK_DECISION, REASON_KEY: block_reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
