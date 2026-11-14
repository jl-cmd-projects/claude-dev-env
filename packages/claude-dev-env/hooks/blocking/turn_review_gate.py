#!/usr/bin/env python3
"""Stop hook that has a fresh reviewer read each turn's changes, and a judge rule on each dismissal.

The agent edits ``src/service.py`` and drops a retry. The turn ends at once.
In the background, a separate ``claude -p`` run reviews only that turn's edits
with ``/code-review low``, on Sonnet at high effort. A finding exits 2 and wakes the agent with it::

    prompt arrives  ->  snapshot A of the working tree
    agent edits     ->  src/service.py loses @with_retry
    stop            ->  turn ends; snapshot B (parent A), claude -p "/code-review low A..B"
                    ->  exit 2 wakes the agent: "src/service.py:208 - The diff removes ..."
    agent fixes it  ->  stop reviews B..C only, finds nothing, prints nothing

``turn_review_snapshot`` builds the snapshots, and ``turn_review_findings``
reads the findings out of the review text. Edits the user left before the
prompt sit in snapshot A, so the review sees only the agent's work.

Each finding gets an id that is unique in the session, such as ``TR-1``, and
is saved as open in the session's state. The wake shows the id beside the
finding. The agent fixes the finding or contests it with one reply line, and
a separate judge run decides::

    reply ends with "Dismiss TR-1: the caller retries the update"
    stop            ->  claude -p --model sonnet --effort high, prompt on stdin
    judge approves  ->  TR-1 dismissed, reason saved, one log line, no wake
    judge rejects   ->  TR-1 upheld; exit 2: "Dismissal of TR-1 rejected: <reason>. Fix it."

``turn_review_transcript`` reads the reply and the user's messages, and
``turn_review_claim`` builds the judge's data from them. The judge runs with
the review's read-only options, once per checkout
that holds a contested finding. A rejection counts toward the hold count, and
it shares one wake with that stop's new findings. The judge runs after the
review and shares its time. A judge that fails, times out or gets no time, or
whose whole answer is not one JSON array of verdicts, leaves the finding open
and exits 0 with no output.

Claude Code runs the Stop entry with ``asyncRewake``. A plain ``claude -p``
run has no background, so the same entry holds that stop with exit code 2.
A finding or a rejected dismissal goes to stderr and to the stdout ``reason``. Every
other outcome exits 0 with no output, and its diagnostic goes to ``~/.claude/logs/turn-review.log``.

A stop claims its range before the review starts, under a lock on the session's
state file. ``turn_review_claim`` makes the claim and saves the stop's outcome,
and ``turn_review_state`` keeps the state file, the lock and the log.
After the review, the stop waits up to 35 seconds for the
lock, longer than a prompt run may hold it, and changes only the hold count. A stop that never gets that lock
exits 0 with no wake, so each wake is counted.

``turn_review_repositories`` picks the checkouts that take part, from the
slugs listed in ``CLAUDE_TURN_REVIEW_REPOSITORIES``. The hook holds a stop at most three times
in a row, skips a turn that changed more than 30 files, and lets the stop
through when the review fails or times out. A user's prompt resets the hold
count, and a prompt that belongs to a wake keeps it, so a chain of wakes stops at three.
A stop gets 280 seconds of work and a prompt 25, under the 300 and 30
second registrations. A git call or review that would start after that time
is skipped.
The cap and the file limit match Anthropic's security-guidance plugin.
``turn_review_child`` starts the review and judge runs, and the hook does
nothing inside such a run.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.hook_time_budget import call_timeout, remaining_seconds, time_budget
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.session_file_id import session_file_id
from hooks_constants.stop_hook_hold import hold_stop
from hooks_constants.turn_review_gate_constants import (
    HOOK_EVENT_NAME_KEY,
    JUDGE_FAILURE_DIAGNOSTIC_TEMPLATE,
    MAXIMUM_TURN_FILES,
    MINIMUM_REVIEW_SECONDS,
    NO_VERDICT_DIAGNOSTIC_TEMPLATE,
    PROMPT_EVENT_NAME,
    PROMPT_KEY,
    PROMPT_RUN_BUDGET_SECONDS,
    REVIEW_CHILD_ENVIRONMENT_VARIABLE,
    REVIEW_CHILD_MARKER,
    REVIEW_FAILURE_DIAGNOSTIC_TEMPLATE,
    REVIEW_RESULT_KEY,
    REVIEW_TIMEOUT_SECONDS,
    RUN_DIAGNOSTIC_TEMPLATE,
    SESSION_ID_KEY,
    STATE_LOCK_BUSY_DIAGNOSTIC_TEMPLATE,
    STATE_LOCK_FILE_MODE,
    STATE_LOCK_FILE_TEMPLATE,
    STATE_LOCK_OUTCOME_WAIT_SECONDS,
    STATE_LOCK_RETRY_SECONDS,
    STATE_LOCK_WAIT_SECONDS,
    STOP_EVENT_NAME,
    STOP_HOOK_ACTIVE_KEY,
    STOP_RUN_BUDGET_SECONDS,
    TOO_MANY_FILES_DIAGNOSTIC_TEMPLATE,
)
from turn_review_child import _ChildRun, _child_stdout, _judge_command, _review_command
from turn_review_claim import (
    _claim_locked_stop,
    _is_wake_prompt,
    _judge_prompt,
    _JudgeRequest,
    _locked_stop_wake,
    _prompt_baselines,
    _StopClaim,
)
from turn_review_findings import JudgeVerdict, dismiss_requests, finding_lines, judge_verdicts
from turn_review_repositories import _opted_in_repository_roots, _opted_in_repository_slugs
from turn_review_snapshot import turn_changed_paths
from turn_review_state import _is_lock_taken, _load_state, _log, _release_and_close, _save_state
from turn_review_transcript import _ReversedTranscript, _reply_text, _typed_user_messages


def _acquire_with_wait(file_descriptor: int, wait_seconds: float) -> bool:
    deadline = time.monotonic() + (call_timeout(wait_seconds) or 0)
    while not _is_lock_taken(file_descriptor):
        if time.monotonic() >= deadline:
            return False
        time.sleep(STATE_LOCK_RETRY_SECONDS)
    return True


@contextmanager
def _state_lock(session_id: object, wait_seconds: float) -> Iterator[bool]:
    lock_path = Path(tempfile.gettempdir()) / STATE_LOCK_FILE_TEMPLATE.format(
        session_id=session_file_id(session_id)
    )
    try:
        file_descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, STATE_LOCK_FILE_MODE)
    except OSError:
        yield False
        return
    is_locked = _acquire_with_wait(file_descriptor, wait_seconds)
    try:
        yield is_locked
    finally:
        _release_and_close(file_descriptor, is_locked)


def _child_result_text(child_run: _ChildRun, deadline: float) -> str | None:
    remaining_seconds = deadline - time.monotonic()
    if remaining_seconds < MINIMUM_REVIEW_SECONDS:
        child_run.write_failure("no time left this stop")
        return None
    child_stdout = _child_stdout(child_run, remaining_seconds)
    if child_stdout is None:
        return None
    try:
        child_result = json.loads(child_stdout)
    except (ValueError, RecursionError):
        child_run.write_failure("output was not JSON")
        return None
    result_text = child_result.get(REVIEW_RESULT_KEY) if isinstance(child_result, dict) else None
    if not isinstance(result_text, str):
        child_run.write_failure("output had no result text")
        return None
    return result_text


def _review_text(
    repository_root: Path, base_commit: str, turn_commit: str, review_deadline: float
) -> str | None:
    review_run = _ChildRun(
        repository_root,
        _review_command(base_commit, turn_commit),
        None,
        REVIEW_FAILURE_DIAGNOSTIC_TEMPLATE,
    )
    return _child_result_text(review_run, review_deadline)


def _record_prompt_baselines(
    session_id: object, all_roots: list[Path], prompt_text: object
) -> None:
    with _state_lock(session_id, STATE_LOCK_WAIT_SECONDS) as is_locked:
        if not is_locked:
            _log(STATE_LOCK_BUSY_DIAGNOSTIC_TEMPLATE.format(event=PROMPT_EVENT_NAME))
            return
        review_state = _load_state(session_id)
        now = time.time()
        review_state.all_baselines = _prompt_baselines(review_state, all_roots)
        review_state.open_turn_prompt_at = now if review_state.is_turn_open else None
        if not _is_wake_prompt(review_state, prompt_text, now):
            review_state.blocks_in_a_row = 0
        review_state.is_turn_open = True
        _save_state(session_id, review_state)


def _repository_findings(
    repository_root: Path, base_commit: str, turn_commit: str, review_deadline: float
) -> list[str] | None:
    all_changed_paths = turn_changed_paths(repository_root, base_commit, turn_commit)
    if len(all_changed_paths) > MAXIMUM_TURN_FILES:
        _log(
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
    return finding_lines(review_text or "", all_changed_paths) or None


def _claim_stop(
    session_id: object, all_roots: list[Path], all_dismiss_reasons: dict[str, str]
) -> _StopClaim:
    with _state_lock(session_id, STATE_LOCK_WAIT_SECONDS) as is_locked:
        if not is_locked:
            _log(STATE_LOCK_BUSY_DIAGNOSTIC_TEMPLATE.format(event=STOP_EVENT_NAME))
            return _StopClaim()
        return _claim_locked_stop(session_id, all_roots, all_dismiss_reasons)


def _repository_verdicts(
    repository_root: Path,
    all_requests: list[_JudgeRequest],
    all_user_messages: list[str],
    deadline: float,
) -> dict[str, JudgeVerdict]:
    judge_run = _ChildRun(
        repository_root,
        _judge_command(),
        _judge_prompt(repository_root, all_requests, all_user_messages),
        JUDGE_FAILURE_DIAGNOSTIC_TEMPLATE,
    )
    result_text = _child_result_text(judge_run, deadline)
    if result_text is None:
        return {}
    all_requested_ids = [each_request.finding_id for each_request in all_requests]
    all_verdicts = judge_verdicts(result_text, all_requested_ids)
    if all_verdicts is None:
        judge_run.write_failure("answer was not one JSON array of verdicts")
        return {}
    for each_id in all_requested_ids:
        if each_id not in all_verdicts:
            _log(NO_VERDICT_DIAGNOSTIC_TEMPLATE.format(finding_id=each_id))
    return all_verdicts


def _all_judge_verdicts(
    all_requests: list[_JudgeRequest],
    all_roots: list[Path],
    all_user_messages: list[str],
    deadline: float,
) -> dict[str, JudgeVerdict]:
    all_verdicts: dict[str, JudgeVerdict] = {}
    for each_root in all_roots:
        all_root_requests = [
            each_request
            for each_request in all_requests
            if each_request.finding.repository == str(each_root)
        ]
        if all_root_requests:
            all_verdicts.update(
                _repository_verdicts(each_root, all_root_requests, all_user_messages, deadline)
            )
    return all_verdicts


def _saved_stop_wake(
    session_id: object,
    all_repository_findings: list[tuple[Path, str, str, list[str]]],
    all_verdicts: dict[str, JudgeVerdict],
) -> str | None:
    with _state_lock(session_id, STATE_LOCK_OUTCOME_WAIT_SECONDS) as is_locked:
        if not is_locked:
            _log(STATE_LOCK_BUSY_DIAGNOSTIC_TEMPLATE.format(event=STOP_EVENT_NAME))
            return None
        return _locked_stop_wake(session_id, all_repository_findings, all_verdicts)


def _turn_block_reason(
    session_id: object, all_roots: list[Path], hook_input: dict | None = None
) -> str | None:
    stop_input = hook_input or {}
    transcript = _ReversedTranscript(stop_input)
    stop_claim = _claim_stop(
        session_id, all_roots, dismiss_requests(_reply_text(stop_input, transcript))
    )
    if not stop_claim.all_turn_ranges and not stop_claim.all_judge_requests:
        return None
    all_repository_findings: list[tuple[Path, str, str, list[str]]] = []
    deadline = time.monotonic() + min(REVIEW_TIMEOUT_SECONDS, remaining_seconds())
    for each_root, each_base_commit, each_turn_commit in stop_claim.all_turn_ranges:
        all_lines = _repository_findings(each_root, each_base_commit, each_turn_commit, deadline)
        if all_lines:
            all_repository_findings.append(
                (each_root, each_base_commit, each_turn_commit, all_lines)
            )
    all_user_messages = (
        _typed_user_messages(transcript) if stop_claim.all_judge_requests else []
    )
    all_verdicts = _all_judge_verdicts(
        stop_claim.all_judge_requests, all_roots, all_user_messages, deadline
    )
    return _saved_stop_wake(session_id, all_repository_findings, all_verdicts)


def _handle_event(hook_input: dict, hook_event_name: object) -> int:
    all_slugs = _opted_in_repository_slugs()
    if not all_slugs:
        return 0
    all_roots = _opted_in_repository_roots(all_slugs)
    if not all_roots:
        return 0
    session_id = hook_input.get(SESSION_ID_KEY)
    _log(
        RUN_DIAGNOSTIC_TEMPLATE.format(
            event=hook_event_name, stop_hook_active=hook_input.get(STOP_HOOK_ACTIVE_KEY)
        )
    )
    if hook_event_name == PROMPT_EVENT_NAME:
        _record_prompt_baselines(session_id, all_roots, hook_input.get(PROMPT_KEY))
        return 0
    block_reason = _turn_block_reason(session_id, all_roots, hook_input)
    if block_reason is None:
        return 0
    log_hook_block(Path(__file__).name, STOP_EVENT_NAME, block_reason)
    return hold_stop(hook_input, block_reason)


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return 0
    if os.environ.get(REVIEW_CHILD_ENVIRONMENT_VARIABLE) == REVIEW_CHILD_MARKER:
        return 0
    hook_event_name = hook_input.get(HOOK_EVENT_NAME_KEY)
    if hook_event_name == STOP_EVENT_NAME:
        run_budget_seconds = STOP_RUN_BUDGET_SECONDS
    elif hook_event_name == PROMPT_EVENT_NAME:
        run_budget_seconds = PROMPT_RUN_BUDGET_SECONDS
    else:
        return 0
    with time_budget(run_budget_seconds):
        return _handle_event(hook_input, hook_event_name)


if __name__ == "__main__":
    sys.exit(main())
