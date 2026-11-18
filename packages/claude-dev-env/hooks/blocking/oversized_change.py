"""Refuse the first create of a pull request that changes more than 1,000 lines against its own base.

::

    branch changes 1,500 lines against main, first create          -> OVERSIZED_PULL_REQUEST_REASON
    same repository, head and base, second or later create         -> None
    first create, the user typed "keep it as one PR" this session  -> None
    stacked level, --base parent, 200 lines of its own             -> None
    compare API at its file cap, listed files over the bar         -> OVERSIZED_PULL_REQUEST_REASON
    compare API at its file cap, listed files under the bar        -> None
    size unreadable or no base                                     -> None

Generated files, marked ``linguist-generated`` in ``.gitattributes``, and
lockfiles are left out. A binary file counts zero lines. Each refusal is
recorded in ``oversized-create-attempts-<session id>.json`` in the system
temp directory, so the next create for the same pull request passes.
"""

from __future__ import annotations

import json
import sys
import tempfile
from collections.abc import Iterator, Mapping
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from atomic_file_writer import write_text_atomically
from blocking.gate_run_reads import answer_once
from blocking.oversized_change_approval import has_user_approved_oversized_pull_request
from blocking.pull_request_proof import (
    CreateCall,
    _compare_lines,
    _create_calls,
    _git_lines,
    _git_output,
    _merge_base_and_head,
    read_named_base_first,
)
from hooks_constants.atomic_file_writer_constants import ATOMIC_WRITE_TEMPORARY_SUFFIX
from hooks_constants.pull_request_proof_constants import COMPARE_FILE_LIST_LIMIT
from hooks_constants.oversized_change_constants import (
    ALL_GENERATED_ATTRIBUTE_VALUES,
    ALL_LOCKFILE_NAMES,
    ATTEMPT_RECORD_ENCODING,
    ATTEMPT_RECORD_FILE_TEMPLATE,
    ATTEMPT_RECORD_TEMPORARY_PREFIX,
    BINARY_NUMSTAT_COUNT,
    MEASURED_LINE_BAR,
    CHECK_ATTR_FIELD_COUNT,
    COMPARE_LINE_COUNT_QUERY,
    GH_MERGE_BASE_CONFIG_KEY,
    HEAD_OWNER_SEPARATOR,
    LINGUIST_GENERATED_ATTRIBUTE,
    NUMSTAT_FIELD_COUNT,
    NUMSTAT_FIELD_SEPARATOR,
    OVERSIZED_PULL_REQUEST_REASON,
    RENAME_DETECTION_LIMIT_OPTION,
    SESSION_ID_FIELD,
    TRANSCRIPT_PATH_FIELD,
    WORKING_DIRECTORY_FIELD,
)
from hooks_constants.session_file_id import session_file_id
from hooks_constants.state_file_lock import hold_state_file_lock


def oversized_pull_request_reason(all_payload_fields: Mapping[str, object]) -> str | None:
    """Return a refusal when a first create of a pull request changes more lines than the bar, else None.

    ::

        create, 1,500 changed lines, first create for this pull request -> OVERSIZED_PULL_REQUEST_REASON
        same create again, any size                                      -> None
        create, 1,500 changed lines, the user approved it this session   -> None
        create, 900 changed lines                                        -> None
        named base neither origin/<base> nor the compare API can read    -> measured against main
        no --base, gh-merge-base set for the branch                      -> measured against that branch
        create whose size git and the compare API cannot read            -> None
        a body edit, a merge, any other tool                             -> None

    One pull request is the repository, head and base the create names.
    Repository falls back to the checkout's top-level folder, then the session
    folder. Head falls back to the checked-out branch. Base falls back to the
    branch ``gh-merge-base`` names for the head. A refusal records that
    key for the session, so the next create for it passes.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    working_directory = str(all_payload_fields.get(WORKING_DIRECTORY_FIELD) or "")
    for each_call in _create_calls(all_payload_fields):
        if each_call.body is None:
            continue
        line_count = _line_count_for_create(each_call, working_directory)
        if line_count is None or line_count <= MEASURED_LINE_BAR:
            continue
        if has_user_approved_oversized_pull_request(all_payload_fields.get(TRANSCRIPT_PATH_FIELD)):
            continue
        if _is_repeat_attempt(
            all_payload_fields.get(SESSION_ID_FIELD),
            _pull_request_key(each_call, working_directory),
        ):
            continue
        return OVERSIZED_PULL_REQUEST_REASON.format(
            measured_line_count=line_count, measured_line_bar=MEASURED_LINE_BAR
        )
    return None


def _pull_request_key(create_call: CreateCall, working_directory: str) -> list[str]:
    repository = create_call.repository or _first_git_line(
        working_directory, "rev-parse", "--show-toplevel"
    )
    head_branch = create_call.head or _first_git_line(working_directory, "branch", "--show-current")
    base_branch = create_call.base or _configured_merge_base(working_directory, create_call.head)
    return [repository or working_directory, head_branch or "", base_branch or ""]


def _first_git_line(working_directory: str, *all_git_arguments: str) -> str | None:
    if not working_directory:
        return None
    all_lines = _git_lines(working_directory, *all_git_arguments)
    return all_lines[0] if all_lines else None


def _is_repeat_attempt(session_id: object, all_key_parts: list[str]) -> bool:
    record_path = Path(tempfile.gettempdir()) / ATTEMPT_RECORD_FILE_TEMPLATE.format(
        session_id=session_file_id(session_id)
    )
    try:
        with hold_state_file_lock(record_path):
            return _is_recorded_or_record(record_path, all_key_parts)
    except (OSError, ValueError):
        return False


def _is_recorded_or_record(record_path: Path, all_key_parts: list[str]) -> bool:
    all_attempted_keys = _attempted_keys(record_path)
    if all_key_parts in all_attempted_keys:
        return True
    write_text_atomically(
        record_path,
        json.dumps([*all_attempted_keys, all_key_parts]),
        ATTEMPT_RECORD_ENCODING,
        ATTEMPT_RECORD_TEMPORARY_PREFIX,
        ATOMIC_WRITE_TEMPORARY_SUFFIX,
        should_reap_orphans=False,
    )
    return False


def _attempted_keys(record_path: Path) -> list[list[str]]:
    try:
        all_recorded_values = json.loads(record_path.read_text(encoding=ATTEMPT_RECORD_ENCODING))
    except (OSError, ValueError):
        return []
    if not isinstance(all_recorded_values, list):
        return []
    return [each_value for each_value in all_recorded_values if isinstance(each_value, list)]


def _line_count_for_create(create_call: CreateCall, working_directory: str) -> int | None:
    repository, base_branch, head_branch = (
        create_call.repository,
        create_call.base,
        create_call.head,
    )
    return answer_once(
        ("changed line count", working_directory, repository, base_branch, head_branch),
        lambda: _read_measurement(working_directory, repository, base_branch, head_branch),
    )


def _read_measurement(
    working_directory: str, repository: str | None, base_branch: str | None, head_branch: str | None
) -> int | None:
    own_base_branch = base_branch or _configured_merge_base(working_directory, head_branch)
    return read_named_base_first(
        working_directory,
        repository,
        head_branch,
        own_base_branch,
        lambda each_base_branch: local_measured_line_count(
            working_directory, each_base_branch, head_branch
        ),
        lambda: remote_measured_line_count(repository, own_base_branch, head_branch),
    )


def _configured_merge_base(working_directory: str, head_branch: str | None) -> str | None:
    if not working_directory:
        return None
    branch_name = head_branch.rsplit(HEAD_OWNER_SEPARATOR, 1)[-1] if head_branch else None
    if not branch_name:
        all_branch_lines = _git_lines(working_directory, "branch", "--show-current")
        branch_name = all_branch_lines[0] if all_branch_lines else None
    if not branch_name:
        return None
    all_configured_lines = _git_lines(
        working_directory,
        "config",
        "--get",
        GH_MERGE_BASE_CONFIG_KEY.format(branch_name=branch_name),
    )
    return all_configured_lines[0] if all_configured_lines and all_configured_lines[0] else None
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
    A named base is read only as ``origin/<base>``. With no base named, it is
    the first of origin/HEAD, origin/main and main. A rename counts only its
    edited lines.

    Args:
        working_directory: The session directory the hook payload names.
        base_branch: The base branch the create call names, or None.
        head_branch: The head branch the create call names, or None.
    """
    merge_base_and_head = _merge_base_and_head(working_directory, head_branch, base_branch)
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


def _numstat_counts(numstat_output: str) -> dict[str, int] | None:
    count_by_path: dict[str, int] = {}
    all_fields = iter(numstat_output.split("\0"))
    for each_field in all_fields:
        if not each_field:
            return count_by_path
        all_counts_and_path = each_field.split(NUMSTAT_FIELD_SEPARATOR, NUMSTAT_FIELD_COUNT - 1)
        if len(all_counts_and_path) != NUMSTAT_FIELD_COUNT:
            return None
        added_text, deleted_text, listed_path = all_counts_and_path
        path = listed_path or _new_path_of_rename(all_fields)
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
    """Return the lines the compare API lists for the create, or None when it cannot tell.

    ::

        compare lists 2 files, 1200 lines     -> 1200
        compare lists only uv.lock +3000 -0   -> 0
        compare lists 300 files, 1500 lines   -> 1500, a lower bound over the bar
        compare lists 300 files, 500 lines    -> None

    The count is against the named base, else the repository's default branch.
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
    is_complete = int(all_lines[0]) < COMPARE_FILE_LIST_LIMIT
    if not is_complete and measured_line_count <= MEASURED_LINE_BAR:
        return None
    return measured_line_count
