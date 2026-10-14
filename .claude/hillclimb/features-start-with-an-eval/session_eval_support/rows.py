"""Read and append the JSON-lines files a run writes, and pick the variant and cases it runs."""

import json
import logging
import os
import threading
from collections.abc import Mapping
from pathlib import Path

from session_eval_support.config.constants import (
    ID_LIST_SEPARATOR,
    RUN_DIGEST_FIELD,
    META_FIELD,
    NEWLINE,
)

logger = logging.getLogger(__name__)
write_lock = threading.Lock()


def _parsed_row(line: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def read_rows(path: Path) -> list[dict[str, object]]:
    """Return every JSON object row in a JSON-lines file.

    ::

        '{"rep": 0}\\n{"rep": 1' -> [{"rep": 0}], with a warning naming line 2

    Args:
        path: The JSON-lines file; a missing file has no rows.

    Returns:
        Each line that parses as a JSON object. A line that does not, such as
        a partial line left by a killed run, is skipped with a warning that
        names it, so its (case, rep) runs again.
    """
    if not path.is_file():
        return []
    all_lines = path.read_text(encoding="utf-8").splitlines()
    all_parsed = [_parsed_row(each_line) for each_line in all_lines]
    for each_number, each_line, each_row in zip(range(1, len(all_lines) + 1), all_lines, all_parsed):
        if each_row is None and each_line.strip():
            logger.warning("skipped unreadable line %d of %s", each_number, path)
    return [each_row for each_row in all_parsed if each_row is not None]


def rows_for_install(
    path: Path, digest: str, all_case_ids: set[str]
) -> list[dict[str, object]]:
    """Return the rows one run digest wrote for the selected cases.

    ::

        rows tagged meta.run_digest "aaa" and "bbb", digest "aaa" -> the "aaa" rows

    Args:
        path: A results or errors JSON-lines file.
        digest: The current run digest from session.run_digest.
        all_case_ids: The ids of the cases this run selected.

    Returns:
        Each row whose ``meta.run_digest`` equals the digest and whose
        ``prompt_id`` is selected. A row with no digest belongs to no run.
    """
    return [
        each_row
        for each_row in read_rows(path)
        if each_row.get("prompt_id") in all_case_ids
        and isinstance(each_row.get(META_FIELD), dict)
        and each_row[META_FIELD].get(RUN_DIGEST_FIELD) == digest
    ]


def open_errors(
    all_error_rows: list[dict[str, object]], all_scored_rows: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Return the error rows whose (case, rep) never produced a scored row.

    Args:
        all_error_rows: Rows from the errors file.
        all_scored_rows: Rows from the results file.

    Returns:
        The errors still open; one a later retry scored is dropped.
    """
    all_scored = {(each_row["prompt_id"], each_row["rep"]) for each_row in all_scored_rows}
    return [
        each_row
        for each_row in all_error_rows
        if (each_row["prompt_id"], each_row["rep"]) not in all_scored
    ]


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
        select_cases(cases, "w02, b02") -> [w02 case, b02 case]
        select_cases(cases, "w02,b02x") -> ValueError naming b02x

    Args:
        all_cases: Every case in the flow's cases file.
        case_ids: The ``--cases`` argument.

    Returns:
        The named cases in file order.

    Raises:
        ValueError: An id names no case.
    """
    all_wanted_ids = {each_id.strip() for each_id in case_ids.split(",") if each_id.strip()}
    all_unknown_ids = all_wanted_ids - {each_case["id"] for each_case in all_cases}
    if all_unknown_ids:
        raise ValueError(f"unknown case ids: {ID_LIST_SEPARATOR.join(sorted(all_unknown_ids))}")
    return [
        each_case
        for each_case in all_cases
        if not all_wanted_ids or each_case["id"] in all_wanted_ids
    ]


def select_variant(
    variant_by_name: dict[str, dict[str, object]], variant_name: str
) -> dict[str, object]:
    """Return one variant's settings from the flow's state file.

    Args:
        variant_by_name: The state file's ``variants`` map.
        variant_name: The ``--variant`` argument.

    Returns:
        That variant's settings.

    Raises:
        ValueError: The name matches no variant.
    """
    if variant_name not in variant_by_name:
        known_names = ID_LIST_SEPARATOR.join(sorted(variant_by_name))
        raise ValueError(f"unknown variant: {variant_name} (known: {known_names})")
    return variant_by_name[variant_name]


def failure_row(
    case_by_field: Mapping[str, str],
    rep: int,
    digest: str,
    failure_class: str,
    detail: object,
) -> dict[str, object]:
    """Return the errors-file row for a session that could not be scored.

    Args:
        case_by_field: The case, with its ``id``.
        rep: The repetition number.
        digest: The run digest.
        failure_class: Why the session could not be scored.
        detail: The evidence for that class.

    Returns:
        The row, tagged with the digest so rows_for_install can scope it.
    """
    return {
        "prompt_id": case_by_field["id"],
        "rep": rep,
        "failure_class": failure_class,
        "detail": detail,
        META_FIELD: {RUN_DIGEST_FIELD: digest},
    }
