"""Plan and run one /efficient-review code review."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

from tools.config import efficient_review_constants as c
from tools.efficient_review_attempt import (
    ReviewAttemptIdentity,
    new_attempt_identity,
    read_candidate_head,
    run_command,
)
from tools.efficient_review_codex import run_codex_review
from tools.efficient_review_launch import (
    broker_account,
    claude_review_launch,
    discover_accounts,
    launcher_path,
)
from tools.efficient_review_request import (
    ReviewRequest,
    ReviewRequestRunFatal,
    load_defaults,
    parse_request,
)
from tools.force_remove import force_remove_tree
from tools.review_stream import claude_record_from_stream

logger = logging.getLogger(__name__)


def run_claude_review(
    request: ReviewRequest,
    account: str,
    home: Path,
    repository: Path,
    work_directory: Path,
) -> dict:
    """Run one Claude review and return its record.

    Args:
        request: The normalized review request.
        account: The selected Claude account.
        home: The user home that contains the account launcher.
        repository: The candidate repository to review.
        work_directory: The temporary directory for review files.

    Returns:
        The Claude review result record.
    """
    identity = new_attempt_identity(repository)
    launcher = launcher_path(home, account)
    command, prompt, environment = claude_review_launch(
        request, launcher, repository, work_directory
    )
    logger.info("launcher: %s", launcher.name)
    completed = run_command(command, prompt, environment, request, repository)
    return _claude_review_record(launcher, completed, identity, repository)


def _claude_review_record(
    launcher: Path,
    completed: subprocess.CompletedProcess[str],
    identity: ReviewAttemptIdentity,
    repository: Path,
) -> dict:
    outcome = claude_record_from_stream(completed.stdout.splitlines())
    observed_head = read_candidate_head(repository)
    is_head_changed = observed_head != identity.candidate_head
    return {
        "launcher": launcher.name,
        "exit_code": completed.returncode,
        "review_text": outcome["review_text"],
        "is_error": _is_claude_error(outcome, completed.returncode, is_head_changed),
        "all_served_models": outcome["all_served_models"],
        "cost_usd": outcome["cost_usd"],
        "stderr_tail": completed.stderr[-c.STDERR_TAIL_CHARACTERS :],
        "invocation_id": identity.invocation_id.hex,
        "attempt_id": identity.attempt_id.hex,
        "candidate_head": identity.candidate_head,
        "candidate_head_after": observed_head,
        "candidate_head_changed": is_head_changed,
    }


def _is_claude_error(outcome: dict, return_code: int, is_head_changed: bool) -> bool:
    return (
        outcome["is_error"]
        or return_code != 0
        or not str(outcome["review_text"]).strip()
        or is_head_changed
    )


def review_save_directory(requested: Path | None, repository: Path) -> Path:
    """Return the save folder after rejecting paths inside the repository.

    Args:
        requested: The requested output folder, or None for a temp folder.
        repository: The repository that must not contain the output folder.

    Returns:
        The resolved folder used to save the review.

    Raises:
        ReviewRequestRunFatal: The folder sits inside the repository.
    """
    if requested is None:
        return Path(tempfile.mkdtemp(prefix=c.SAVE_DIRECTORY_PREFIX))
    review_directory = requested.resolve()
    if review_directory.is_relative_to(repository.resolve()):
        raise ReviewRequestRunFatal(
            f"{requested} is inside the repository {repository}"
        )
    return review_directory


def save_review(all_record: Mapping, review_directory: Path) -> Path:
    """Write a review and its record into the checked save folder.

    Args:
        all_record: The review result and request data to persist.
        review_directory: The folder where the review artifacts are written.

    Returns:
        The path to the saved review text.
    """
    review_directory.mkdir(parents=True, exist_ok=True)
    review_path = review_directory / c.REVIEW_FILENAME
    review_path.write_text(str(all_record["review_text"]), encoding=c.TEXT_ENCODING)
    (review_directory / c.RECORD_FILENAME).write_text(
        json.dumps(all_record, indent=c.JSON_INDENT), encoding=c.TEXT_ENCODING
    )
    return review_path


def _run(parsed: argparse.Namespace, request: ReviewRequest) -> int:
    if request.profile != "slim":
        raise ReviewRequestRunFatal(
            f"profile {request.profile!r} is not supported; use slim"
        )
    repository = parsed.repository.resolve()
    save_directory = review_save_directory(parsed.output, repository)
    work_directory = Path(tempfile.mkdtemp(prefix=c.WORK_DIRECTORY_PREFIX))
    try:
        all_record = _review_record(request, Path.home(), repository, work_directory)
    finally:
        force_remove_tree(work_directory)
    return _report_review(all_record, save_directory)


def _report_review(all_record: dict, save_directory: Path) -> int:
    review_path = save_review(all_record, save_directory)
    logger.info("%s", all_record["review_text"])
    logger.info(
        "served models: %s", c.LIST_SEPARATOR.join(all_record["all_served_models"])
    )
    logger.info("saved: %s", review_path)
    if not all_record["is_error"]:
        return 0
    logger.error(
        "review failed: exit code %s\nreviewer stderr tail:\n%s",
        all_record["exit_code"],
        all_record["stderr_tail"],
    )
    return 1


def _review_record(
    request: ReviewRequest, home: Path, repository: Path, work_directory: Path
) -> dict:
    all_request = asdict(request)
    if request.harness == c.HARNESS_CODEX:
        provider_record = run_codex_review(request, repository, work_directory)
    else:
        provider_record = _claude_record(request, home, repository, work_directory)
        all_request["account"] = provider_record.pop("account")
    return {"request": all_request, **provider_record}


def _claude_record(
    request: ReviewRequest, home: Path, repository: Path, work_directory: Path
) -> dict:
    account = request.account
    if request.mode == c.MODE_AUTO:
        account, reason = broker_account(subprocess.run, home)
        logger.info("broker picked %s: %s", account, reason)
    if account is None:
        raise ReviewRequestRunFatal("headless needs an account; name one or use auto")
    return {
        "account": account,
        **run_claude_review(request, account, home, repository, work_directory),
    }


def main() -> int:
    """Plan, list accounts, or run one review.

    Returns:
        Zero when the plan, the account list, or the review succeeds.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subcommands = parser.add_subparsers(dest="command", required=True)
    for each_name in (c.PLAN_COMMAND, "run"):
        subcommand = subcommands.add_parser(each_name)
        subcommand.add_argument("request", nargs="*")
        if each_name == "run":
            subcommand.add_argument("--repository", type=Path, default=Path.cwd())
            subcommand.add_argument("--output", type=Path)
    subcommands.add_parser("accounts")
    parsed = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    if parsed.command == "accounts":
        return _print_accounts()
    request = parse_request(parsed.request, load_defaults())
    if parsed.command == c.PLAN_COMMAND:
        logger.info("%s", json.dumps(asdict(request), indent=c.JSON_INDENT))
        return 0
    return _run(parsed, request)


def _print_accounts() -> int:
    all_accounts, source = discover_accounts(Path.home())
    logger.info("%s", json.dumps({"accounts": all_accounts, "source": source}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
