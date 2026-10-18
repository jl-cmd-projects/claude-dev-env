"""Run one Codex review in an isolated home."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from importlib import import_module
from pathlib import Path
from typing import Protocol

from tools.config import efficient_review_constants as c
from tools.config import review_run_constants as run_constants
from tools.config.efficient_review_settings import load_settings
from tools.efficient_review_attempt import (
    ReviewAttemptIdentity,
    new_attempt_identity,
    read_candidate_head,
    run_command,
)
from tools.efficient_review_request import ReviewRequest, ReviewRequestRunFatal
from tools.review_codex import codex_home, codex_record_from_rollouts
from tools.review_command import review_command
from tools.review_rules import review_rules_text

logger = logging.getLogger(__name__)


class CodexModelResolution(Protocol):
    model: str
    source: str


def run_codex_review(
    request: ReviewRequest, repository: Path, work_directory: Path
) -> dict:
    """Run codex review in a home isolated to this attempt.

    Args:
        request: The normalized Codex review request.
        repository: The candidate repository to review.
        work_directory: The temporary directory for review files.

    Returns:
        The Codex review record with its invocation and candidate identity.
    """
    identity = new_attempt_identity(repository)
    environment, home = _codex_attempt_environment(identity, work_directory)
    resolution = _discover_codex_model(request, repository, environment)
    logger.info("codex model: %s from %s", resolution.model, resolution.source)
    command, prompt = _codex_review_command(request, resolution.model)
    started_at, completed = _run_timed_command(
        command, prompt, request, repository, environment
    )
    return _codex_review_record(
        identity, resolution, completed, home, started_at, repository
    )


def _codex_attempt_environment(
    identity: ReviewAttemptIdentity, work_directory: Path
) -> tuple[dict[str, str], Path]:
    environment = dict(os.environ)
    home = work_directory / f"{c.CODEX_RUN_HOME_NAME}-{identity.attempt_id.hex}"
    home.mkdir(parents=True)
    shutil.copyfile(
        codex_home(environment) / c.CODEX_LOGIN_FILENAME,
        home / c.CODEX_LOGIN_FILENAME,
    )
    environment[c.CODEX_HOME_ENVIRONMENT] = str(home)
    return environment, home


def _discover_codex_model(
    request: ReviewRequest, repository: Path, all_environment: dict[str, str]
) -> CodexModelResolution:
    module_name = str(load_settings()["codex_catalog_module"])
    if not module_name:
        raise ReviewRequestRunFatal(
            "set codex_catalog_module in settings to the module that resolves sol and luna"
        )
    executable = os.environ.get(c.CODEX_EXECUTABLE_ENVIRONMENT, c.CODEX_EXECUTABLE_NAME)
    return import_module(module_name).discover_model(
        subprocess.run,
        executable,
        all_environment,
        repository,
        request.model,
        request.effort,
        c.CODEX_DISCOVERY_TIMEOUT_SECONDS,
    )


def _codex_review_command(
    request: ReviewRequest, resolved_model: str
) -> tuple[list[str], str]:
    executable = os.environ.get(c.CODEX_EXECUTABLE_ENVIRONMENT, c.CODEX_EXECUTABLE_NAME)
    command, _prompt = review_command(
        run_constants.HARNESS_CODEX,
        resolved_model,
        request.effort,
        request.level,
        "",
        executable,
    )
    prompt = run_constants.PROMPT_SECTION_SEPARATOR.join(
        [
            run_constants.CODEX_BASE_BRANCH_PROMPT_TEMPLATE.format(
                base_branch=request.base
            ),
            review_rules_text(),
            c.CONFIRMED_FINDINGS_INSTRUCTION,
        ]
    )
    return command, prompt


def _run_timed_command(
    all_command: list[str],
    prompt: str,
    request: ReviewRequest,
    repository: Path,
    all_environment: dict[str, str],
) -> tuple[float, subprocess.CompletedProcess[str]]:
    started_at = time.time()
    completed = run_command(all_command, prompt, all_environment, request, repository)
    return started_at, completed


def _codex_review_record(
    identity: ReviewAttemptIdentity,
    resolution: CodexModelResolution,
    completed: subprocess.CompletedProcess[str],
    home: Path,
    started_at: float,
    repository: Path,
) -> dict:
    observed_head = read_candidate_head(repository)
    outcome = codex_record_from_rollouts(home, started_at, repository)
    is_head_changed = observed_head != identity.candidate_head
    return {
        "launcher": c.CODEX_ACCOUNT_LABEL,
        "resolved_model": resolution.model,
        "exit_code": completed.returncode,
        "review_text": outcome["review_text"],
        "is_error": _is_codex_error(completed.returncode, outcome, is_head_changed),
        "all_served_models": outcome["all_served_models"],
        "stderr_tail": completed.stderr[-c.STDERR_TAIL_CHARACTERS :],
        "invocation_id": identity.invocation_id.hex,
        "attempt_id": identity.attempt_id.hex,
        "candidate_head": identity.candidate_head,
        "candidate_head_after": observed_head,
        "candidate_head_changed": is_head_changed,
    }


def _is_codex_error(return_code: int, outcome: dict, is_head_changed: bool) -> bool:
    return return_code != 0 or outcome["review_output"] is None or is_head_changed
