"""Shared attempt identity and process launch for one review."""

from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from tools.config import efficient_review_constants as c
from tools.efficient_review_request import ReviewRequest, ReviewRequestRunFatal


@dataclass(frozen=True)
class ReviewAttemptIdentity:
    invocation_id: uuid.UUID
    attempt_id: uuid.UUID
    candidate_head: str


def new_attempt_identity(repository: Path) -> ReviewAttemptIdentity:
    """Return a fresh invocation identity and the candidate head.

    Args:
        repository: The candidate repository to review.

    Returns:
        The identity recorded with the review.
    """
    return ReviewAttemptIdentity(
        invocation_id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        candidate_head=read_candidate_head(repository),
    )


def read_candidate_head(repository: Path) -> str:
    """Return the candidate repository's current HEAD.

    Args:
        repository: The candidate repository to review.

    Returns:
        The HEAD commit.

    Raises:
        ReviewRequestRunFatal: git rev-parse HEAD failed.
    """
    completed = subprocess.run(
        ["git", *c.ALL_HEAD_ARGUMENTS],
        cwd=repository,
        capture_output=True,
        text=True,
        encoding=c.TEXT_ENCODING,
        errors="replace",
        check=False,
    )
    candidate_head = completed.stdout.strip()
    if completed.returncode != 0 or not candidate_head:
        raise ReviewRequestRunFatal(
            f"git rev-parse HEAD failed: {completed.stderr.strip()}"
        )
    return candidate_head


def run_command(
    all_command: list[str],
    prompt: str,
    all_environment: dict[str, str],
    request: ReviewRequest, repository: Path,
) -> subprocess.CompletedProcess[str]:
    """Run one review command and capture its streams.

    Args:
        all_command: The executable and its arguments.
        prompt: The text passed on standard input.
        all_environment: The environment for the process.
        request: The normalized review request.
        repository: The candidate repository to review.

    Returns:
        The completed process.
    """
    return subprocess.run(
        all_command,
        cwd=repository,
        input=prompt,
        env=all_environment,
        capture_output=True,
        text=True,
        encoding=c.TEXT_ENCODING,
        errors="replace",
        timeout=request.timeout_minutes * c.SECONDS_PER_MINUTE,
        check=False,
    )
