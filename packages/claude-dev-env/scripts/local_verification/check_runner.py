from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias

from .check_support import (
    _prepare_check_invocation,
    _record_missing_check,
    _write_logs,
)
from .command_runner import run_command as _run_command
from .config import (
    ALL_COLLECTED_RUN_EXIT_CODES,
    CLI_CHECK_FINISH_MESSAGE_TEMPLATE,
    CLI_CHECK_START_MESSAGE_TEMPLATE,
    COLLECTION_ERROR_KIND,
    CRASH_ERROR_KIND,
    FAILED_STATUS,
    INCOMPLETE_STATUS,
    MINIMUM_TESTS_ERROR_KIND,
    NO_TESTS_COLLECTED_EXIT_CODE,
    NONZERO_EXIT_ERROR_KIND,
    PASSED_STATUS,
    RUN_OUTCOME_PATTERN,
    RUN_SUMMARY_DURATION_PATTERN,
    SAFE_LOG_NAME_PATTERN,
    SKIPPED_TESTS_ERROR_KIND,
    SKIPPED_TESTS_PATTERN,
    STDERR_LOG_SUFFIX,
    STDOUT_LOG_SUFFIX,
    SUCCESS_EXIT_CODE,
)
from .model import (
    CheckLogPaths,
    CheckRecord,
    CheckSpec,
    CommandCapture,
    VerificationManifest,
)

ProgressCallback: TypeAlias = Callable[[str], None]


def execute_all_checks(
    manifest: VerificationManifest,
    repository_path: Path,
    base_revision: str,
    logs_directory: Path,
    progress_callback: ProgressCallback | None,
) -> tuple[CheckRecord, ...]:
    """Execute every check in the manifest.

    Args:
        manifest: Checks to execute.

    Returns:
        One record for each check.
    """
    return tuple(
        _execute_check(
            each_check,
            repository_path,
            base_revision,
            logs_directory,
            progress_callback,
        )
        for each_check in manifest.checks
    )


def _execute_check(
    check: CheckSpec,
    repository_path: Path,
    base_revision: str,
    logs_directory: Path,
    progress_callback: ProgressCallback | None,
) -> CheckRecord:
    _emit_progress(
        progress_callback,
        CLI_CHECK_START_MESSAGE_TEMPLATE.format(check_id=check.check_id),
    )
    check_log_paths = _build_check_log_paths(check, logs_directory)
    check_directory, all_arguments = _prepare_check_invocation(
        check, repository_path, base_revision
    )
    if not check_directory.is_dir():
        check_record = _record_missing_check(
            check, all_arguments, check_directory, check_log_paths
        )
        return _finish_with_progress(progress_callback, check, check_record)
    check_record = _run_existing_check(
        check, all_arguments, check_directory, check_log_paths
    )
    return _finish_with_progress(progress_callback, check, check_record)


def _build_check_log_paths(check: CheckSpec, logs_directory: Path) -> CheckLogPaths:
    safe_check_id = SAFE_LOG_NAME_PATTERN.sub("_", check.check_id)
    return CheckLogPaths(
        logs_directory / (safe_check_id + STDOUT_LOG_SUFFIX),
        logs_directory / (safe_check_id + STDERR_LOG_SUFFIX),
    )


def _run_existing_check(
    check: CheckSpec,
    all_arguments: tuple[str, ...],
    check_directory: Path,
    check_log_paths: CheckLogPaths,
) -> CheckRecord:
    started_at = time.monotonic()
    command_capture = _run_command(
        all_arguments, check_directory, check.timeout_seconds
    )
    duration_seconds = time.monotonic() - started_at
    all_collection_capture = _collection_from_run(check, command_capture)
    return _finish_check(
        check,
        all_arguments,
        check_directory,
        check_log_paths,
        all_collection_capture,
        command_capture,
        duration_seconds,
    )


def _finish_with_progress(
    progress_callback: ProgressCallback | None,
    check: CheckSpec,
    check_record: CheckRecord,
) -> CheckRecord:
    _emit_progress(
        progress_callback,
        CLI_CHECK_FINISH_MESSAGE_TEMPLATE.format(
            check_id=check.check_id, status=check_record.status
        ),
    )
    return check_record


def _emit_progress(
    progress_callback: ProgressCallback | None, progress_message: str
) -> None:
    if progress_callback is not None:
        progress_callback(progress_message)


def _finish_check(
    check: CheckSpec,
    all_arguments: tuple[str, ...],
    check_directory: Path,
    check_log_paths: CheckLogPaths,
    all_collection_capture: tuple[CommandCapture, int | None] | None,
    command_capture: CommandCapture,
    duration_seconds: float,
) -> CheckRecord:
    _write_logs(
        check_log_paths.stdout,
        check_log_paths.stderr,
        command_capture.stdout_text,
        command_capture.stderr_text,
    )
    return _build_finished_record(
        check,
        all_arguments,
        check_directory,
        check_log_paths,
        all_collection_capture,
        command_capture,
        duration_seconds,
    )


def _build_finished_record(
    check: CheckSpec,
    all_arguments: tuple[str, ...],
    check_directory: Path,
    check_log_paths: CheckLogPaths,
    all_collection_capture: tuple[CommandCapture, int | None] | None,
    command_capture: CommandCapture,
    duration_seconds: float,
) -> CheckRecord:
    status, error_kind, error_message = _classify_record(
        check, all_collection_capture, command_capture
    )
    return CheckRecord(
        check.check_id,
        status,
        all_arguments,
        str(check_directory),
        command_capture.exit_code,
        duration_seconds,
        check_log_paths.stdout,
        check_log_paths.stderr,
        error_kind,
        error_message,
        check.minimum_tests,
        all_collection_capture[1] if all_collection_capture is not None else None,
        all_collection_capture[0].exit_code
        if all_collection_capture is not None
        else None,
    )


def _classify_record(
    check: CheckSpec,
    all_collection_capture: tuple[CommandCapture, int | None] | None,
    command_capture: CommandCapture,
) -> tuple[str, str | None, str | None]:
    status, error_kind, error_message = _classify_command(command_capture)
    if all_collection_capture is None or command_capture.error_kind is not None:
        return status, error_kind, error_message
    status, error_kind, error_message = _classify_collection(
        check, all_collection_capture, status, error_kind, error_message
    )
    return _classify_skipped_tests(
        check,
        all_collection_capture,
        command_capture,
        status,
        error_kind,
        error_message,
    )


def _collection_from_run(
    check: CheckSpec, command_capture: CommandCapture
) -> tuple[CommandCapture, int | None] | None:
    """Read the collection outcome from the check's own pytest run.

    A check with a test floor needs the number of tests pytest collected.
    The run's summary line already holds it, so no second pytest start is
    needed. Exit 0 and 1 mean collection worked; any other exit is kept::

        exit 1, "2 failed, 9 passed, 1 deselected in 3.1s" -> (exit 0, 12 tests)
        exit 5, "no tests ran in 0.1s"                     -> (exit 5, 0 tests)
        exit 2, "1 error in 0.3s"                          -> (exit 2, 1 test)

    Args:
        check: The check that ran.
        command_capture: The check's own run.

    Returns:
        The collection outcome and its test count, or None for a check
        without a test floor.
    """
    if check.minimum_tests is None:
        return None
    collection_exit_code = (
        SUCCESS_EXIT_CODE
        if command_capture.exit_code in ALL_COLLECTED_RUN_EXIT_CODES
        else command_capture.exit_code
    )
    collection_capture = CommandCapture(collection_exit_code, "", "", None, None)
    return collection_capture, _parse_run_tests(command_capture)


def _parse_run_tests(command_capture: CommandCapture) -> int | None:
    all_summary_lines = [
        each_line
        for each_line in (
            command_capture.stdout_text + command_capture.stderr_text
        ).splitlines()
        if RUN_SUMMARY_DURATION_PATTERN.search(each_line)
    ]
    all_outcomes = (
        RUN_OUTCOME_PATTERN.findall(all_summary_lines[-1]) if all_summary_lines else []
    )
    if not all_outcomes:
        return 0 if command_capture.exit_code == NO_TESTS_COLLECTED_EXIT_CODE else None
    return sum(int(each_count) for each_count, _outcome in all_outcomes)


def _parse_skipped_tests(command_capture: CommandCapture) -> int:
    all_text = command_capture.stdout_text + command_capture.stderr_text
    skipped_match = SKIPPED_TESTS_PATTERN.search(all_text)
    if skipped_match is None:
        return 0
    return int(skipped_match.group("count"))


def _classify_skipped_tests(
    check: CheckSpec,
    all_collection_capture: tuple[CommandCapture, int | None],
    command_capture: CommandCapture,
    status: str,
    error_kind: str | None,
    error_message: str | None,
) -> tuple[str, str | None, str | None]:
    if status != PASSED_STATUS:
        return status, error_kind, error_message
    if not _has_skipped_required_tests(check, all_collection_capture, command_capture):
        return status, error_kind, error_message
    return INCOMPLETE_STATUS, SKIPPED_TESTS_ERROR_KIND, "Required tests were skipped"


def _has_skipped_required_tests(
    check: CheckSpec,
    all_collection_capture: tuple[CommandCapture, int | None],
    command_capture: CommandCapture,
) -> bool:
    if check.minimum_tests is None:
        return False
    collection_capture, collected_tests = all_collection_capture
    if collection_capture.exit_code != SUCCESS_EXIT_CODE:
        return False
    if collected_tests is None or collected_tests == 0:
        return False
    return _parse_skipped_tests(command_capture) > 0


def _classify_collection(
    check: CheckSpec,
    all_collection_capture: tuple[CommandCapture, int | None],
    status: str,
    error_kind: str | None,
    error_message: str | None,
) -> tuple[str, str | None, str | None]:
    command_capture, collected_tests = all_collection_capture
    if (
        check.minimum_tests is not None
        and collected_tests is not None
        and collected_tests < check.minimum_tests
    ):
        return FAILED_STATUS, MINIMUM_TESTS_ERROR_KIND, "Minimum test count was not met"
    if status == FAILED_STATUS:
        return status, error_kind, error_message
    if command_capture.error_kind is not None:
        return INCOMPLETE_STATUS, COLLECTION_ERROR_KIND, command_capture.error_message
    if command_capture.exit_code != SUCCESS_EXIT_CODE:
        return INCOMPLETE_STATUS, COLLECTION_ERROR_KIND, "Pytest collection failed"
    if collected_tests is None:
        return (
            INCOMPLETE_STATUS,
            COLLECTION_ERROR_KIND,
            "Pytest collection count is missing",
        )
    return status, error_kind, error_message


def _classify_command(
    command_capture: CommandCapture,
) -> tuple[str, str | None, str | None]:
    if command_capture.error_kind is not None:
        return (
            INCOMPLETE_STATUS,
            command_capture.error_kind,
            command_capture.error_message,
        )
    if command_capture.exit_code is None:
        return INCOMPLETE_STATUS, CRASH_ERROR_KIND, "Command ended without an exit code"
    if command_capture.exit_code < 0:
        return INCOMPLETE_STATUS, CRASH_ERROR_KIND, "Command ended from a signal"
    if command_capture.exit_code != SUCCESS_EXIT_CODE:
        return (
            FAILED_STATUS,
            NONZERO_EXIT_ERROR_KIND,
            "Command returned a nonzero exit code",
        )
    return PASSED_STATUS, None, None
