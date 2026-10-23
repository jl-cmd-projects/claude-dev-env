"""Read the findings out of a turn review's text, for the turn review Stop gate.

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
"""

from __future__ import annotations

import json
import re

from hooks_constants.turn_review_gate_constants import (
    FINDING_LINE_PATTERN_TEMPLATE,
    JSON_ARRAY_START,
    JSON_FINDING_FILE_KEY,
    JSON_FINDING_LINE_KEY,
    JSON_FINDING_LINE_TEMPLATE,
    JSON_FINDING_SUMMARY_KEY,
    NO_FINDINGS_MARKER,
)


def _json_finding_lines(review_text: str, all_changed_paths: list[str]) -> list[str] | None:
    all_filled_arrays = _filled_finding_arrays(review_text)
    if not all_filled_arrays:
        return None
    return _entries_on_changed_paths(all_filled_arrays[-1], all_changed_paths)


def _filled_finding_arrays(review_text: str) -> list[list[dict[str, object]]]:
    json_decoder = json.JSONDecoder()
    all_finding_arrays: list[list[dict[str, object]]] = []
    array_start = review_text.find(JSON_ARRAY_START)
    while array_start >= 0:
        try:
            decoded_array, next_search_start = json_decoder.raw_decode(review_text, array_start)
        except ValueError:
            decoded_array, next_search_start = None, array_start + 1
        if decoded_array and _is_finding_array(decoded_array):
            all_finding_arrays.append(decoded_array)
        array_start = review_text.find(JSON_ARRAY_START, next_search_start)
    return all_finding_arrays


def _is_finding_array(decoded_array: object) -> bool:
    return isinstance(decoded_array, list) and all(
        isinstance(each_entry, dict) and JSON_FINDING_FILE_KEY in each_entry
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
