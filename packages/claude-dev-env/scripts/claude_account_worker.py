"""Run a headless Claude worker through the account broker."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from account_broker import run_job
from claude_account_worker_process import invoke_worker
from claude_account_worker_report import finalize_report, make_report, pre_launch_failure_report, wait_report
from dev_env_scripts_constants.account_broker_constants import BrokerConfigurationError, JobOutcome
from dev_env_scripts_constants.claude_account_worker_constants import (
    CLAUDE_BINARY_NAME,
    CLI_DESCRIPTION,
    CONFIGURATION_FAILURE_EXIT_CODE,
    CWD_FLAG,
    DEFAULT_PERMISSION_MODE,
    DEFAULT_TIMEOUT_MINUTES,
    INVALID_TIMEOUT_MESSAGE,
    LAUNCH_FAILURE_EXIT_CODE,
    LIVE_LOG_FLAG,
    MINIMUM_TIMEOUT_MINUTES,
    MODEL_FLAG,
    OUTPUT_FORMAT_FLAG,
    OUTPUT_FORMAT_JSON,
    OUTPUT_FORMAT_STREAM_JSON,
    PERMISSION_MODE_FLAG,
    PROMPT_FILE_FLAG,
    REPORT_FILE_FLAG,
    SINGLE_PROMPT_FLAG,
    TIMEOUT_MINUTES_FLAG,
    VERBOSE_FLAG,
    UTF8_ENCODING,
)

worker_job_runner = run_job


def _positive_timeout_minutes(candidate_text: str) -> int:
    timeout_minutes = int(candidate_text)
    if timeout_minutes < MINIMUM_TIMEOUT_MINUTES:
        raise argparse.ArgumentTypeError(INVALID_TIMEOUT_MESSAGE)
    return timeout_minutes


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for one headless worker invocation."""
    parser = argparse.ArgumentParser(description=CLI_DESCRIPTION)
    parser.add_argument(PROMPT_FILE_FLAG, type=Path, required=True)
    parser.add_argument(CWD_FLAG, type=Path, default=Path.cwd())
    parser.add_argument(REPORT_FILE_FLAG, type=Path, required=True)
    parser.add_argument(MODEL_FLAG)
    parser.add_argument(PERMISSION_MODE_FLAG, default=DEFAULT_PERMISSION_MODE)
    parser.add_argument(TIMEOUT_MINUTES_FLAG, type=_positive_timeout_minutes, default=DEFAULT_TIMEOUT_MINUTES)
    parser.add_argument(LIVE_LOG_FLAG, type=Path)
    return parser


def _invocation(*, model: str | None, permission_mode: str, is_streamed: bool) -> list[str]:
    output_arguments = [OUTPUT_FORMAT_FLAG, OUTPUT_FORMAT_STREAM_JSON, VERBOSE_FLAG] if is_streamed else [OUTPUT_FORMAT_FLAG, OUTPUT_FORMAT_JSON]
    arguments = [
        CLAUDE_BINARY_NAME,
        SINGLE_PROMPT_FLAG,
        *output_arguments,
        PERMISSION_MODE_FLAG,
        permission_mode,
    ]
    if model is not None:
        arguments.extend([MODEL_FLAG, model])
    return arguments


def _wait_reason(outcome: JobOutcome) -> str:
    if outcome.wait_reason is None:
        return "no account has room"
    return outcome.wait_reason


def run_worker(
    *,
    prompt_file: Path,
    cwd: Path,
    report_file: Path,
    model: str | None,
    permission_mode: str,
    timeout_minutes: int,
    live_log: Path | None = None,
) -> int:
    """Run one worker and write its structured report.

    With ``live_log`` set, the worker streams one JSON event per line into that
    file while it runs, so a watching session can read progress before the end.
    """
    try:
        prompt_text = prompt_file.read_text(encoding=UTF8_ENCODING)
    except (OSError, UnicodeError):
        report = pre_launch_failure_report("none", "prompt file is unreadable", LAUNCH_FAILURE_EXIT_CODE)
        return finalize_report(report_file, report)
    try:
        outcome, duration_seconds = invoke_worker(
            all_arguments=_invocation(model=model, permission_mode=permission_mode, is_streamed=live_log is not None),
            cwd=cwd,
            prompt_text=prompt_text,
            timeout_minutes=timeout_minutes,
            runner=worker_job_runner,
            live_log=live_log,
        )
    except BrokerConfigurationError as error:
        report = pre_launch_failure_report("none", str(error), CONFIGURATION_FAILURE_EXIT_CODE)
        return finalize_report(report_file, report)
    if outcome.status in {"wait", "exhausted"}:
        report = wait_report("wait", _wait_reason(outcome), outcome.wait_reset_at)
        return finalize_report(report_file, report)
    report = make_report(
        outcome.account_name or "none",
        outcome.status,
        exit_code=outcome.returncode,
        duration_seconds=duration_seconds,
        stdout_text=outcome.stdout,
    )
    return finalize_report(report_file, report)


def main() -> int:
    """Parse CLI arguments and run one headless worker."""
    arguments = build_argument_parser().parse_args()
    return run_worker(
        prompt_file=arguments.prompt_file,
        cwd=arguments.cwd,
        report_file=arguments.report_file,
        model=arguments.model,
        permission_mode=arguments.permission_mode,
        timeout_minutes=arguments.timeout_minutes,
        live_log=arguments.live_log,
    )


if __name__ == "__main__":
    sys.exit(main())
