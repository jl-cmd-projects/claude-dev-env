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
    MINIMUM_TIMEOUT_MINUTES,
    MODEL_FLAG,
    OUTPUT_FORMAT_FLAG,
    OUTPUT_FORMAT_JSON,
    PERMISSION_MODE_FLAG,
    PROMPT_FILE_FLAG,
    REPORT_FILE_FLAG,
    SINGLE_PROMPT_FLAG,
    TIMEOUT_ATTEMPT_STATUS,
    TIMEOUT_EXIT_CODE,
    TIMEOUT_MINUTES_FLAG,
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
    return parser


def _invocation(*, model: str | None, permission_mode: str) -> list[str]:
    arguments = [
        CLAUDE_BINARY_NAME,
        SINGLE_PROMPT_FLAG,
        OUTPUT_FORMAT_FLAG,
        OUTPUT_FORMAT_JSON,
        PERMISSION_MODE_FLAG,
        permission_mode,
    ]
    if model is not None:
        arguments.extend([MODEL_FLAG, model])
    return arguments


def _wait_reason(outcome: JobOutcome) -> str:
    if outcome.wait_reset_at is None:
        return "no account has room"
    return f"no account has room; next reset at {outcome.wait_reset_at.isoformat()}"


def run_worker(
    *,
    prompt_file: Path,
    cwd: Path,
    report_file: Path,
    model: str | None,
    permission_mode: str,
    timeout_minutes: int,
) -> int:
    """Run one worker and write its structured report."""
    try:
        prompt_text = prompt_file.read_text(encoding=UTF8_ENCODING)
    except (OSError, UnicodeError):
        report = pre_launch_failure_report("none", "prompt file is unreadable", LAUNCH_FAILURE_EXIT_CODE)
        return finalize_report(report_file, report)
    try:
        outcome, duration_seconds = invoke_worker(
            all_arguments=_invocation(model=model, permission_mode=permission_mode),
            cwd=cwd,
            prompt_text=prompt_text,
            timeout_minutes=timeout_minutes,
            runner=worker_job_runner,
        )
    except BrokerConfigurationError as error:
        report = pre_launch_failure_report("none", str(error), CONFIGURATION_FAILURE_EXIT_CODE)
        return finalize_report(report_file, report)
    if outcome.status in {"wait", "exhausted"}:
        report = wait_report("wait", _wait_reason(outcome), outcome.wait_reset_at)
        return finalize_report(report_file, report)
    is_timed_out = bool(outcome.attempts) and outcome.attempts[-1][1] == TIMEOUT_ATTEMPT_STATUS
    report = make_report(
        outcome.account_name or "none",
        TIMEOUT_ATTEMPT_STATUS if is_timed_out else outcome.status,
        exit_code=TIMEOUT_EXIT_CODE if is_timed_out else outcome.returncode,
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
    )


if __name__ == "__main__":
    sys.exit(main())
