"""Read the findings, the dismissal requests and the judge's verdicts for the turn review gate.

A review either prints a JSON array of findings or prose that names each
problem by its changed path and line::

    '[{"file": "src/service.py", "line": 208, "summary": "drops the retry"}]'
        ->  ["src/service.py:208 drops the retry"]
    "- `src/service.py:208` - drops the retry"
        ->  ["- `src/service.py:208` - drops the retry"]
    "(none)"
        ->  []

The last non-empty array of objects with a ``file`` key wins. Its entries count
when ``file`` is a changed path and ``line`` is a number. With no such array,
each line that opens with a changed path, a colon and a line number counts,
after an optional list marker, backtick or emphasis mark.

The agent contests a finding with a reply line, and the judge answers in JSON::

    "Dismiss TR-3: the caller retries"  ->  {"TR-3": "the caller retries"}
    '[{"id": "TR-3", "verdict": "reject", "reason": "nothing retries"}]'
        ->  {"TR-3": JudgeVerdict(is_approved=False, reason="nothing retries")}

A dismiss line may open with a list marker, quote mark, backtick or emphasis
mark. The first line for an id wins, and its reason is cut to 2000 characters.
The judge's whole answer must be one JSON array, inside at most one code fence.
Each object holds exactly ``id``, ``verdict`` and ``reason`` once each, and
each id is one the judge was asked about. Any other answer gives None, such as
an object that repeats a key or a NaN or Infinity value. So an array or a key
that the agent planted in its reason and the judge echoed never counts. An entry
counts when its verdict is ``approve`` or ``reject``, its reason is not empty,
and no other entry names its id. A character in a reason that UTF-8 cannot
write, such as a lone surrogate, is kept as its escape text.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import TypeGuard

from hooks_constants.turn_review_gate_constants import (
    ALL_JUDGE_ENTRY_KEYS,
    DISMISS_LINE_PREFIX_PATTERN,
    FINDING_LINE_PATTERN_TEMPLATE,
    JSON_ARRAY_START,
    JUDGE_ANSWER_CONSTANT_REASON,
    JUDGE_ANSWER_FENCE_PATTERN,
    JUDGE_ANSWER_REPEATED_KEY_REASON,
    JUDGE_APPROVE_VERDICT,
    JUDGE_ID_KEY,
    JUDGE_REASON_KEY,
    JUDGE_REASON_TEXT_ENCODING,
    JUDGE_REASON_UNENCODABLE_HANDLER,
    JUDGE_REJECT_VERDICT,
    JUDGE_VERDICT_KEY,
    JSON_FINDING_FILE_KEY,
    JSON_FINDING_LINE_KEY,
    JSON_FINDING_LINE_TEMPLATE,
    JSON_FINDING_SUMMARY_KEY,
    MAXIMUM_DISMISS_REASON_CHARACTERS,
    NO_FINDINGS_MARKER,
    REASON_EDGE_CHARACTERS,
    REPLY_LINE_SEPARATOR,
)


@dataclass(frozen=True)
class JudgeVerdict:
    """The judge's answer on one dismissal request."""

    is_approved: bool
    reason: str


def _json_finding_lines(review_text: str, all_changed_paths: list[str]) -> list[str] | None:
    all_filled_arrays = _filled_object_arrays(review_text, JSON_FINDING_FILE_KEY)
    if not all_filled_arrays:
        return None
    return _entries_on_changed_paths(all_filled_arrays[-1], all_changed_paths)


def _filled_object_arrays(text: str, required_key: str) -> list[list[dict[str, object]]]:
    json_decoder = json.JSONDecoder()
    all_object_arrays: list[list[dict[str, object]]] = []
    array_start = text.find(JSON_ARRAY_START)
    while array_start >= 0:
        try:
            decoded_array, next_search_start = json_decoder.raw_decode(text, array_start)
        except (ValueError, RecursionError):
            decoded_array, next_search_start = None, array_start + 1
        if decoded_array and _is_object_array(decoded_array, required_key):
            all_object_arrays.append(decoded_array)
        array_start = text.find(JSON_ARRAY_START, next_search_start)
    return all_object_arrays


def _is_object_array(decoded_array: object, required_key: str) -> bool:
    return isinstance(decoded_array, list) and all(
        isinstance(each_entry, dict) and required_key in each_entry
        for each_entry in decoded_array
    )


def _entries_on_changed_paths(
    all_entries: list[dict[str, object]], all_changed_paths: list[str]
) -> list[str]:
    return [
        JSON_FINDING_LINE_TEMPLATE.format(
            path=each_entry[JSON_FINDING_FILE_KEY],
            line=each_entry[JSON_FINDING_LINE_KEY],
            summary=each_entry.get(JSON_FINDING_SUMMARY_KEY, ""),
        ).strip()
        for each_entry in all_entries
        if each_entry.get(JSON_FINDING_FILE_KEY) in all_changed_paths
        and isinstance(each_entry.get(JSON_FINDING_LINE_KEY), int)
    ]


def finding_lines(review_text: str, all_changed_paths: list[str]) -> list[str]:
    """Return one line per finding the review reports on a changed path.

    Args:
        review_text: The ``result`` text of the review run.
        all_changed_paths: The git-relative paths the turn changed.

    Returns:
        The finding lines, empty when the review found nothing.
    """
    if review_text.strip().startswith(NO_FINDINGS_MARKER):
        return []
    all_json_finding_lines = _json_finding_lines(review_text, all_changed_paths)
    if all_json_finding_lines is not None:
        return all_json_finding_lines
    all_patterns = [
        re.compile(FINDING_LINE_PATTERN_TEMPLATE.format(path=re.escape(each)))
        for each in all_changed_paths
    ]
    return [
        each_line.strip()
        for each_line in review_text.splitlines()
        if any(each_pattern.search(each_line) for each_pattern in all_patterns)
    ]


def dismiss_requests(reply_text: str) -> dict[str, str]:
    """Return the reason of each ``Dismiss TR-<n>: <reason>`` line in a reply, by finding id.

    Args:
        reply_text: The text of the agent's last reply.

    Returns:
        The reason for each finding id, cut to its first
        ``MAXIMUM_DISMISS_REASON_CHARACTERS``; the first line for an id wins.
    """
    prefix_pattern = re.compile(DISMISS_LINE_PREFIX_PATTERN)
    all_requests: dict[str, str] = {}
    for each_line in reply_text.split(REPLY_LINE_SEPARATOR):
        prefix_match = prefix_pattern.match(each_line)
        if prefix_match is None:
            continue
        reason = each_line[prefix_match.end() :].strip(REASON_EDGE_CHARACTERS)
        if reason and not reason[0].isspace():
            all_requests.setdefault(
                prefix_match.group(1), reason[:MAXIMUM_DISMISS_REASON_CHARACTERS]
            )
    return all_requests


def _object_without_repeated_keys(all_pairs: list[tuple[str, object]]) -> dict[str, object]:
    all_fields = dict(all_pairs)
    if len(all_fields) != len(all_pairs):
        raise ValueError(JUDGE_ANSWER_REPEATED_KEY_REASON)
    return all_fields


def _refused_constant(constant_name: str) -> object:
    raise ValueError(JUDGE_ANSWER_CONSTANT_REASON)


def _decoded_answer(result_text: str) -> object | None:
    answer_text = result_text.strip()
    fence_match = re.fullmatch(JUDGE_ANSWER_FENCE_PATTERN, answer_text, re.DOTALL)
    if fence_match is not None:
        answer_text = fence_match.group(1)
    try:
        return json.loads(
            answer_text,
            object_pairs_hook=_object_without_repeated_keys,
            parse_constant=_refused_constant,
        )
    except (ValueError, RecursionError):
        return None


def _is_verdict_array(
    decoded_answer: object, all_requested_ids: list[str]
) -> TypeGuard[list[dict[str, object]]]:
    return (
        isinstance(decoded_answer, list)
        and bool(decoded_answer)
        and all(
            isinstance(each_entry, dict)
            and set(each_entry) == ALL_JUDGE_ENTRY_KEYS
            and each_entry[JUDGE_ID_KEY] in all_requested_ids
            for each_entry in decoded_answer
        )
    )


def _entry_verdict(all_entry_fields: dict[str, object]) -> JudgeVerdict | None:
    verdict_word = all_entry_fields[JUDGE_VERDICT_KEY]
    reason = all_entry_fields[JUDGE_REASON_KEY]
    if (
        verdict_word in (JUDGE_APPROVE_VERDICT, JUDGE_REJECT_VERDICT)
        and isinstance(reason, str)
        and reason.strip()
    ):
        return JudgeVerdict(
            verdict_word == JUDGE_APPROVE_VERDICT, _encodable_text(reason.strip())
        )
    return None


def _encodable_text(reason: str) -> str:
    return reason.encode(
        JUDGE_REASON_TEXT_ENCODING, JUDGE_REASON_UNENCODABLE_HANDLER
    ).decode(JUDGE_REASON_TEXT_ENCODING)


def judge_verdicts(
    result_text: str, all_requested_ids: list[str]
) -> dict[str, JudgeVerdict] | None:
    """Return the judge's verdict for each requested finding its answer covers.

    Args:
        result_text: The ``result`` text of the judge run.
        all_requested_ids: The finding ids the judge was asked about.

    Returns:
        The verdicts by finding id. An id the answer names twice gets none. None when
        the whole answer, inside at most one code fence, is not one strict JSON array
        of objects with exactly an id the judge was asked about, a verdict and a
        reason, each named once.
    """
    decoded_answer = _decoded_answer(result_text)
    if not _is_verdict_array(decoded_answer, all_requested_ids):
        return None
    all_entry_counts = Counter(each_entry[JUDGE_ID_KEY] for each_entry in decoded_answer)
    all_verdicts: dict[str, JudgeVerdict] = {}
    for each_entry in decoded_answer:
        entry_id = each_entry[JUDGE_ID_KEY]
        entry_verdict = _entry_verdict(each_entry)
        if (
            isinstance(entry_id, str)
            and entry_verdict is not None
            and all_entry_counts[entry_id] == 1
        ):
            all_verdicts[entry_id] = entry_verdict
    return all_verdicts
