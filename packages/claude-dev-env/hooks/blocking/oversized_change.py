"""Deny a new pull request that changes more than 1,000 lines against its own base, unless its body says why it stays one.

::

    branch changes 1,500 lines against main, plain body          -> OVERSIZED_PULL_REQUEST_REASON
    same branch, body has a 'Why one pull request' section       -> None
    stacked level, --base parent, 200 lines of its own           -> None
    compare API at its file cap, listed files over the bar       -> OVERSIZED_PULL_REQUEST_REASON
    compare API at its file cap, listed files under the bar      -> None
    size unreadable or no base                                   -> None

Generated files, marked ``linguist-generated`` in ``.gitattributes``, and
lockfiles are left out. A binary file counts zero lines.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.gate_run_reads import answer_once
from blocking.pull_request_proof import (
    CreateCall,
    _all_section_texts,
    _cached_head_reference,
    _compare_lines,
    _create_calls,
    _first_merge_base,
    _git_lines,
    _git_output,
    _merge_base_and_head,
    checkout_is_for,
)
from hooks_constants.pull_request_proof_constants import (
    COMPARE_FILE_LIST_LIMIT,
    REMOTE_BRANCH_PREFIX,
)
from hooks_constants.oversized_change_constants import (
    ALL_GENERATED_ATTRIBUTE_VALUES,
    ALL_LOCKFILE_NAMES,
    BINARY_NUMSTAT_COUNT,
    MEASURED_LINE_BAR,
    CHECK_ATTR_FIELD_COUNT,
    COMPARE_LINE_COUNT_QUERY,
    LINGUIST_GENERATED_ATTRIBUTE,
    NUMSTAT_FIELD_COUNT,
    NUMSTAT_FIELD_SEPARATOR,
    ONE_PULL_REQUEST_HEADING_PATTERN,
    OVERSIZED_PULL_REQUEST_REASON,
    RENAME_DETECTION_LIMIT_OPTION,
)


def oversized_pull_request_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a deny reason when a new pull request changes more lines than the bar, else None.

    ::

        create, 1,500 changed lines, no 'Why one pull request' section -> OVERSIZED_PULL_REQUEST_REASON
        create, 1,500 changed lines, the section states a reason      -> None
        create, 900 changed lines                                      -> None
        create whose size git and the compare API cannot read          -> None
        a body edit, a merge, any other tool                           -> None

    A body that holds the section passes with no read. Each create is measured
    against its own base, so a stacked level counts only its own lines.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    working_directory = str(all_payload_fields.get("cwd") or "")
    for each_call in _create_calls(all_payload_fields):
        if each_call.body is None or any(
            _all_section_texts(each_call.body, ONE_PULL_REQUEST_HEADING_PATTERN)
        ):
            continue
        measured_line_count = _measured_line_count_for_create(each_call, working_directory)
        if measured_line_count is not None and measured_line_count > MEASURED_LINE_BAR:
            return OVERSIZED_PULL_REQUEST_REASON.format(
                measured_line_count=measured_line_count, measured_line_bar=MEASURED_LINE_BAR
            )
    return None


def _measured_line_count_for_create(create_call: CreateCall, working_directory: str) -> int | None:
    repository, base_branch, head_branch = (
        create_call.repository,
        create_call.base,
        create_call.head,
    )
    return answer_once(
        ("changed line count", working_directory, repository, base_branch, head_branch),
        lambda: _read_measured_line_count(working_directory, repository, base_branch, head_branch),
    )


def _read_measured_line_count(
    working_directory: str, repository: str | None, base_branch: str | None, head_branch: str | None
) -> int | None:
    measured_line_count = None
    if working_directory and checkout_is_for(working_directory, repository):
        measured_line_count = local_measured_line_count(working_directory, base_branch, head_branch)
    if measured_line_count is None:
        measured_line_count = remote_measured_line_count(repository, base_branch, head_branch)
    return measured_line_count


def local_measured_line_count(
    working_directory: str, base_branch: str | None, head_branch: str | None
) -> int | None:
    """Return the lines the head branch adds and deletes since it left its base, or None when git cannot tell.

    ::

        feature adds 1,200 lines to tool.py over main         -> 1200
        stacked level, base "parent", 200 lines of its own     -> 200
        feature also adds a 5,000-line linguist-generated file -> 1200
        base names a branch the clone does not hold            -> None

    The head is the checked-out branch, or the named branch or its origin copy.
    The base is ``origin/<base>`` or ``<base>``, else the first of origin/HEAD,
    origin/main and main. A rename counts only its edited lines.

    Args:
        working_directory: The session directory the hook payload names.
        base_branch: The base branch the create call names, or None.
        head_branch: The head branch the create call names, or None.
    """
    merge_base_and_head = _merge_base_and_head_for_base(working_directory, base_branch, head_branch)
    if merge_base_and_head is None:
        return None
    merge_base, head_reference = merge_base_and_head
    numstat_output = _numstat_output(working_directory, merge_base, head_reference)
    if numstat_output is None:
        return None
    count_by_path = _counts_without_lockfiles(numstat_output)
    if count_by_path is None:
        return None
    if sum(count_by_path.values()) <= MEASURED_LINE_BAR:
        return sum(count_by_path.values())
    all_generated_paths = _generated_paths(working_directory, head_reference, list(count_by_path))
    if all_generated_paths is None:
        return None
    return sum(
        each_count
        for each_path, each_count in count_by_path.items()
        if each_path not in all_generated_paths
    )


def _numstat_output(working_directory: str, merge_base: str, head_reference: str) -> str | None:
    return _git_output(
        working_directory,
        "diff",
        "--numstat",
        "--no-relative",
        "-z",
        "-M",
        RENAME_DETECTION_LIMIT_OPTION,
        merge_base,
        head_reference,
    )


def _counts_without_lockfiles(numstat_output: str) -> dict[str, int] | None:
    count_by_path = _numstat_counts(numstat_output)
    if count_by_path is None:
        return None
    return {
        each_path: each_count
        for each_path, each_count in count_by_path.items()
        if not _is_lockfile(each_path)
    }


def _merge_base_and_head_for_base(
    working_directory: str, base_branch: str | None, head_branch: str | None
) -> tuple[str, str] | None:
    if not base_branch:
        return _merge_base_and_head(working_directory, head_branch)
    head_reference = _cached_head_reference(working_directory, head_branch)
    if head_reference is None:
        return None
    merge_base = _first_merge_base(
        working_directory, head_reference, (REMOTE_BRANCH_PREFIX + base_branch, base_branch)
    )
    return None if merge_base is None else (merge_base, head_reference)


def _numstat_counts(numstat_output: str) -> dict[str, int] | None:
    count_by_path: dict[str, int] = {}
    all_fields = iter(numstat_output.split("\0"))
    for each_field in all_fields:
        if not each_field:
            return count_by_path
        all_counts_and_path = each_field.split(NUMSTAT_FIELD_SEPARATOR, NUMSTAT_FIELD_COUNT - 1)
        if len(all_counts_and_path) != NUMSTAT_FIELD_COUNT:
            return None
        added_text, deleted_text, path = all_counts_and_path
        path = path or _new_path_of_rename(all_fields)
        line_count = _numstat_line_count(added_text, deleted_text)
        if not path or line_count is None:
            return None
        count_by_path[path] = count_by_path.get(path, 0) + line_count
    return count_by_path


def _new_path_of_rename(all_fields: Iterator[str]) -> str | None:
    next(all_fields, None)
    return next(all_fields, None)


def _numstat_line_count(added_text: str, deleted_text: str) -> int | None:
    if added_text == BINARY_NUMSTAT_COUNT and deleted_text == BINARY_NUMSTAT_COUNT:
        return 0
    if not added_text.isdigit() or not deleted_text.isdigit():
        return None
    return int(added_text) + int(deleted_text)


def _generated_paths(
    working_directory: str, head_reference: str, all_paths: list[str]
) -> set[str] | None:
    if not all_paths:
        return set()
    all_top_level_lines = _git_lines(working_directory, "rev-parse", "--show-toplevel")
    if not all_top_level_lines:
        return None
    check_attr_output = _generated_attribute_output(
        all_top_level_lines[0], head_reference, all_paths
    )
    if check_attr_output is None:
        return None
    all_fields = check_attr_output.split("\0")
    return {
        all_fields[each_index]
        for each_index in range(
            0, len(all_fields) - CHECK_ATTR_FIELD_COUNT + 1, CHECK_ATTR_FIELD_COUNT
        )
        if all_fields[each_index + 2] in ALL_GENERATED_ATTRIBUTE_VALUES
    }


def _generated_attribute_output(
    top_level_directory: str, head_reference: str, all_paths: list[str]
) -> str | None:
    standard_input = "".join(each_path + "\0" for each_path in all_paths)
    for each_source_arguments in (("--source=" + head_reference,), ()):
        check_attr_output = _git_output(
            top_level_directory,
            "check-attr",
            "-z",
            "--stdin",
            *each_source_arguments,
            LINGUIST_GENERATED_ATTRIBUTE,
            standard_input=standard_input,
        )
        if check_attr_output is not None:
            return check_attr_output
    return None


def _is_lockfile(path: str) -> bool:
    return path.rsplit("/", 1)[-1] in ALL_LOCKFILE_NAMES


def remote_measured_line_count(
    repository: str | None, base_branch: str | None, head_branch: str | None
) -> int | None:
    """Return the lines the GitHub compare API reports between base and head, or None when it cannot tell.

    ::

        compare lists tool.py +1200 -0                 -> 1200
        compare lists only uv.lock +3000 -0            -> 0
        compare returns 300 files listing 5000 lines   -> 5000
        compare returns 300 files listing 500 lines    -> None
        repository or head missing                     -> None

    The base is the named base branch, else the repository's default branch.
    The compare API does not read ``.gitattributes``, so only lockfiles are left out.
    At its file cap the listed files are a lower bound, so the count stands only over the bar.

    Args:
        repository: The owner/name the create call names, or None.
        base_branch: The base branch the create call names, or None.
        head_branch: The head branch the create call names, or None.
    """
    all_lines = _compare_lines(repository, base_branch, head_branch, COMPARE_LINE_COUNT_QUERY)
    if not all_lines or not all_lines[0].isdigit():
        return None
    measured_line_count = 0
    for each_line in all_lines[1:]:
        try:
            path, added_count, deleted_count = json.loads(each_line)
        except (ValueError, TypeError):
            return None
        if not isinstance(added_count, int) or not isinstance(deleted_count, int):
            return None
        if not _is_lockfile(str(path)):
            measured_line_count += added_count + deleted_count
    if int(all_lines[0]) >= COMPARE_FILE_LIST_LIMIT and measured_line_count <= MEASURED_LINE_BAR:
        return None
    return measured_line_count
