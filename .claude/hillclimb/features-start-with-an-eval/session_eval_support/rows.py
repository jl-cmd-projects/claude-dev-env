"""Read and append the JSON-lines files a run writes, and pick the cases it runs."""

import json
import os
import threading
from pathlib import Path

from session_eval_support.config.constants import ID_LIST_SEPARATOR, NEWLINE

write_lock = threading.Lock()


def read_rows(path: Path) -> list[dict[str, object]]:
    """Return every JSON object row in a JSON-lines file.

    ::

        '{"rep": 0}\\n{"rep": 1' -> [{"rep": 0}]

    Args:
        path: The JSON-lines file; a missing file has no rows.

    Returns:
        Each line that parses as a JSON object. A partial line left by a
        killed run is skipped, so its (case, rep) runs again.
    """
    if not path.is_file():
        return []
    all_rows: list[dict[str, object]] = []
    for each_line in path.read_text(encoding="utf-8").splitlines():
        try:
            each_row = json.loads(each_line)
        except json.JSONDecodeError:
            continue
        if isinstance(each_row, dict):
            all_rows.append(each_row)
    return all_rows


def _ends_mid_line(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    with path.open("rb") as jsonl_file:
        jsonl_file.seek(-1, os.SEEK_END)
        return jsonl_file.read(1) != NEWLINE.encode()


def append_row(path: Path, row_by_field: dict[str, object]) -> None:
    """Append one row as its own line, ending any partial line first.

    Args:
        path: The JSON-lines file.
        row_by_field: The row to write.
    """
    with write_lock:
        line_start = NEWLINE if _ends_mid_line(path) else ""
        with path.open("a", encoding="utf-8") as jsonl_file:
            jsonl_file.write(line_start + json.dumps(row_by_field) + NEWLINE)


def select_cases(
    all_cases: list[dict[str, str]], case_ids: str
) -> list[dict[str, str]]:
    """Return the cases a comma-separated id list names, or every case for an empty list.

    ::

        select_cases(cases, "w02,b02") -> [w02 case, b02 case]
        select_cases(cases, "w02,b02x") -> ValueError naming b02x

    Args:
        all_cases: Every case in the flow's cases file.
        case_ids: The ``--cases`` argument.

    Returns:
        The named cases in file order.

    Raises:
        ValueError: An id names no case.
    """
    all_wanted_ids = {each_id for each_id in case_ids.split(",") if each_id}
    all_unknown_ids = all_wanted_ids - {each_case["id"] for each_case in all_cases}
    if all_unknown_ids:
        raise ValueError(f"unknown case ids: {ID_LIST_SEPARATOR.join(sorted(all_unknown_ids))}")
    return [
        each_case
        for each_case in all_cases
        if not all_wanted_ids or each_case["id"] in all_wanted_ids
    ]
