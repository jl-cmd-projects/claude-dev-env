"""Change the session's review state for a prompt and a stop, for the turn review gate.

The gate calls these while it holds the lock on the session's state file. A
stop claims its range before the review starts. It moves the baseline to
snapshot B, marks the turn closed, and saves both. A second stop during the
review starts from B, so no range is reviewed twice.

A prompt marks the turn open. When the last turn is still open, no stop has
claimed it yet: its stop is racing this prompt, or the user interrupted it::

    prompt 1  ->  baseline A, turn open
    stop 1    ->  starts; the next prompt runs before its claim
    prompt 2  ->  turn still open, so A stays the baseline
    stop 1    ->  claims A..B and reviews turn 1's edits

Edits the user made between those two turns are then reviewed too. When a
prompt found the turn open less than 10 seconds before the claim, that prompt
began the next turn, so the stop leaves it open. A later claim closes it,
which ends the open turn an interrupt left behind.

The claim also lists the findings the reply contests. The judge gets the
checkout path and one JSON object of data::

    {"requests": [{"id": "TR-1", "commit_range": "A..B",
                   "finding": "src/service.py:3 - ...", "reason_to_dismiss": "..."}],
     "user_messages": ["the last five messages the user typed, cut to 2000 characters"]}

The judge gets no other part of the
conversation. A ``Dismiss`` line for an id that is not open, or
one sent at the hold cap, is logged and not judged.

After the review, each new finding gets the next id of the session and is
saved as open. An approved dismissal marks its finding dismissed. A rejection
marks it upheld and adds one line to the wake. A stop with a wake adds one to
the hold count. A stop below the cap with no
finding, no rejection and no dismissal to judge resets the count. A prompt within 10 seconds
of the last wake, or one that starts with ``<task-notification``, belongs to
the wake.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from hooks_constants.turn_review_gate_constants import (
    BLOCK_REASON_TEMPLATE,
    DISMISS_AT_CAP_DIAGNOSTIC_TEMPLATE,
    DISMISS_IGNORED_DIAGNOSTIC_TEMPLATE,
    FINDING_DISMISSED_DIAGNOSTIC_TEMPLATE,
    FINDING_LINE_SEPARATOR,
    FINDING_LINE_WITH_ID_TEMPLATE,
    FINDING_STATUS_DISMISSED,
    FINDING_STATUS_OPEN,
    FINDING_STATUS_UPHELD,
    FINDING_UPHELD_DIAGNOSTIC_TEMPLATE,
    JUDGE_COMMIT_RANGE_TEMPLATE,
    JUDGE_DATA_INDENT,
    JUDGE_DATA_REQUESTS_KEY,
    JUDGE_DATA_USER_MESSAGES_KEY,
    JUDGE_ID_KEY,
    JUDGE_PROMPT_TEMPLATE,
    JUDGE_REQUEST_FINDING_KEY,
    JUDGE_REQUEST_RANGE_KEY,
    JUDGE_REQUEST_REASON_KEY,
    MACHINE_PROMPT_PREFIX,
    MAXIMUM_BLOCKS_IN_A_ROW,
    MAXIMUM_USER_MESSAGE_CHARACTERS,
    OUTSIDE_REPOSITORY_LABEL,
    RACING_STOP_WINDOW_SECONDS,
    REJECTION_LINE_SEPARATOR,
    REJECTION_LINE_TEMPLATE,
    REPOSITORY_FINDINGS_SEPARATOR,
    REPOSITORY_FINDINGS_TEMPLATE,
    SENTENCE_END_CHARACTERS,
    UNKNOWN_FINDING_LABEL,
    WAKE_PART_SEPARATOR,
    WAKE_PROMPT_WINDOW_SECONDS,
    WORD_SEPARATOR,
)
from turn_review_findings import JudgeVerdict
from turn_review_snapshot import working_tree_snapshot
from turn_review_state import (
    _Finding,
    _ReviewState,
    _finding_number,
    _load_state,
    _log,
    _next_finding_id,
    _save_state,
)


def _is_wake_prompt(review_state: _ReviewState, prompt_text: object, now: float) -> bool:
    if isinstance(prompt_text, str) and prompt_text.lstrip().startswith(MACHINE_PROMPT_PREFIX):
        return True
    if review_state.last_wake_at is None:
        return False
    return now - review_state.last_wake_at < WAKE_PROMPT_WINDOW_SECONDS


def _prompt_baselines(review_state: _ReviewState, all_roots: list[Path]) -> dict[str, str]:
    all_baselines = dict(review_state.all_baselines) if review_state.is_turn_open else {}
    for each_root in all_roots:
        if str(each_root) in all_baselines:
            continue
        snapshot_commit = working_tree_snapshot(each_root, None)
        if snapshot_commit is not None:
            all_baselines[str(each_root)] = snapshot_commit
    return all_baselines


@dataclass(frozen=True)
class _JudgeRequest:
    finding_id: str
    finding: _Finding
    reason: str


@dataclass(frozen=True)
class _StopClaim:
    all_turn_ranges: list[tuple[Path, str, str]] = field(default_factory=list)
    all_judge_requests: list[_JudgeRequest] = field(default_factory=list)


def _judge_requests(
    review_state: _ReviewState,
    all_dismiss_reasons: dict[str, str],
    all_roots: list[Path],
    is_capped: bool,
) -> list[_JudgeRequest]:
    all_root_names = {str(each_root) for each_root in all_roots}
    all_requests: list[_JudgeRequest] = []
    for each_id, each_reason in all_dismiss_reasons.items():
        finding = review_state.all_findings.get(each_id)
        skip_diagnostic = _dismiss_skip_diagnostic(each_id, finding, all_root_names, is_capped)
        if skip_diagnostic is not None:
            _log(skip_diagnostic)
            continue
        if finding is not None:
            all_requests.append(_JudgeRequest(each_id, finding, each_reason))
    return all_requests


def _dismiss_skip_diagnostic(
    finding_id: str, finding: _Finding | None, all_root_names: set[str], is_capped: bool
) -> str | None:
    if finding is None:
        return DISMISS_IGNORED_DIAGNOSTIC_TEMPLATE.format(
            finding_id=finding_id, status=UNKNOWN_FINDING_LABEL
        )
    if finding.status != FINDING_STATUS_OPEN:
        return DISMISS_IGNORED_DIAGNOSTIC_TEMPLATE.format(
            finding_id=finding_id, status=finding.status
        )
    if finding.repository not in all_root_names:
        return DISMISS_IGNORED_DIAGNOSTIC_TEMPLATE.format(
            finding_id=finding_id, status=OUTSIDE_REPOSITORY_LABEL
        )
    if is_capped:
        return DISMISS_AT_CAP_DIAGNOSTIC_TEMPLATE.format(finding_id=finding_id)
    return None


def _claim_locked_stop(
    session_id: object, all_roots: list[Path], all_dismiss_reasons: dict[str, str]
) -> _StopClaim:
    review_state = _load_state(session_id)
    is_capped = review_state.blocks_in_a_row >= MAXIMUM_BLOCKS_IN_A_ROW
    all_judge_requests = _judge_requests(review_state, all_dismiss_reasons, all_roots, is_capped)
    all_next_baselines: dict[str, str] = {}
    all_turn_ranges: list[tuple[Path, str, str]] = []
    for each_root in all_roots:
        base_commit = review_state.all_baselines.get(str(each_root))
        turn_commit = working_tree_snapshot(each_root, base_commit)
        if turn_commit is None:
            continue
        all_next_baselines[str(each_root)] = turn_commit
        if base_commit is not None and base_commit != turn_commit and not is_capped:
            all_turn_ranges.append((each_root, base_commit, turn_commit))
    if not all_turn_ranges and not all_judge_requests and not is_capped:
        review_state.blocks_in_a_row = 0
    review_state.all_baselines = all_next_baselines
    review_state.is_turn_open = (
        review_state.open_turn_prompt_at is not None
        and time.time() - review_state.open_turn_prompt_at < RACING_STOP_WINDOW_SECONDS
    )
    review_state.open_turn_prompt_at = None
    _save_state(session_id, review_state)
    return _StopClaim(all_turn_ranges, all_judge_requests)


def _judge_prompt(
    repository_root: Path, all_requests: list[_JudgeRequest], all_user_messages: list[str]
) -> str:
    judge_data = {
        JUDGE_DATA_REQUESTS_KEY: [
            {
                JUDGE_ID_KEY: each_request.finding_id,
                JUDGE_REQUEST_RANGE_KEY: JUDGE_COMMIT_RANGE_TEMPLATE.format(
                    base_commit=each_request.finding.base_commit,
                    turn_commit=each_request.finding.turn_commit,
                ),
                JUDGE_REQUEST_FINDING_KEY: each_request.finding.text,
                JUDGE_REQUEST_REASON_KEY: each_request.reason,
            }
            for each_request in all_requests
        ],
        JUDGE_DATA_USER_MESSAGES_KEY: all_user_messages,
    }
    return JUDGE_PROMPT_TEMPLATE.format(
        repository=repository_root,
        user_message_characters=MAXIMUM_USER_MESSAGE_CHARACTERS,
        judge_data=json.dumps(judge_data, indent=JUDGE_DATA_INDENT, ensure_ascii=True),
    )


def _one_line(judge_reason: str) -> str:
    return WORD_SEPARATOR.join(judge_reason.split())


def _one_sentence(judge_reason: str) -> str:
    return _one_line(judge_reason).rstrip(SENTENCE_END_CHARACTERS)


def _apply_verdicts(
    review_state: _ReviewState, all_verdicts: dict[str, JudgeVerdict]
) -> list[str]:
    all_rejection_lines: list[str] = []
    for each_id in sorted(all_verdicts, key=_finding_number):
        finding = review_state.all_findings.get(each_id)
        if finding is None or finding.status != FINDING_STATUS_OPEN:
            continue
        verdict = all_verdicts[each_id]
        finding.judge_reason = verdict.reason
        if verdict.is_approved:
            finding.status = FINDING_STATUS_DISMISSED
            _log(
                FINDING_DISMISSED_DIAGNOSTIC_TEMPLATE.format(
                    finding_id=each_id, reason=_one_line(verdict.reason)
                )
            )
            continue
        finding.status = FINDING_STATUS_UPHELD
        _log(
            FINDING_UPHELD_DIAGNOSTIC_TEMPLATE.format(
                finding_id=each_id, reason=_one_line(verdict.reason)
            )
        )
        all_rejection_lines.append(
            REJECTION_LINE_TEMPLATE.format(
                finding_id=each_id, reason=_one_sentence(verdict.reason)
            )
        )
    return all_rejection_lines


def _record_new_findings(
    review_state: _ReviewState, all_repository_findings: list[tuple[Path, str, str, list[str]]]
) -> list[str]:
    all_repository_blocks: list[str] = []
    for each_root, each_base_commit, each_turn_commit, each_finding_lines in all_repository_findings:
        all_lines_with_ids: list[str] = []
        for each_line in each_finding_lines:
            finding_id = _next_finding_id(review_state)
            review_state.all_findings[finding_id] = _Finding(
                each_line, str(each_root), each_base_commit, each_turn_commit
            )
            all_lines_with_ids.append(
                FINDING_LINE_WITH_ID_TEMPLATE.format(finding_id=finding_id, finding=each_line)
            )
        all_repository_blocks.append(
            REPOSITORY_FINDINGS_TEMPLATE.format(
                repository=each_root.name,
                findings=FINDING_LINE_SEPARATOR.join(all_lines_with_ids),
            )
        )
    return all_repository_blocks


def _locked_stop_wake(
    session_id: object,
    all_repository_findings: list[tuple[Path, str, str, list[str]]],
    all_verdicts: dict[str, JudgeVerdict],
) -> str | None:
    review_state = _load_state(session_id)
    all_wake_parts: list[str] = []
    all_rejection_lines = _apply_verdicts(review_state, all_verdicts)
    if all_rejection_lines:
        all_wake_parts.append(REJECTION_LINE_SEPARATOR.join(all_rejection_lines))
    all_repository_blocks = _record_new_findings(review_state, all_repository_findings)
    if all_repository_blocks:
        all_wake_parts.append(
            BLOCK_REASON_TEMPLATE.format(
                all_findings=REPOSITORY_FINDINGS_SEPARATOR.join(all_repository_blocks)
            )
        )
    if all_wake_parts:
        review_state.blocks_in_a_row += 1
        review_state.last_wake_at = time.time()
    elif review_state.blocks_in_a_row < MAXIMUM_BLOCKS_IN_A_ROW:
        review_state.blocks_in_a_row = 0
    _save_state(session_id, review_state)
    return WAKE_PART_SEPARATOR.join(all_wake_parts) or None
