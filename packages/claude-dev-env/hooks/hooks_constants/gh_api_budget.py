"""Read the GitHub core REST limit for the gh API budget gate, at most once every five minutes.

::

    cache under five minutes old    CoreRateBudget(limit=5000, used=4000, reset=...)
    cache stale or missing          runs gh api rate_limit, then caches the answer
    gh missing, slow or broken      None, and the failure is cached for five minutes

The cache file is ``<managed root>/cache/gh_api_budget.json``, where the
managed root is ``CLAUDE_CONFIG_DIR``, else ``~/.claude``. It holds
``{"read_at": <epoch seconds>, "limit": 5000, "used": 4000, "reset": <epoch
seconds>}``, and a failed read holds null limit, used and reset. A cache file
that does not parse counts as stale.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from hooks_constants.subprocess_window import hidden_window_creation_flags
from hooks_constants.gh_api_budget_gate_constants import (
    ALL_RATE_LIMIT_QUERY_ARGUMENTS,
    CACHE_DIRECTORY_NAME,
    CACHE_FILE_NAME,
    CACHE_MAXIMUM_AGE_SECONDS,
    CACHE_READ_AT_KEY,
    CACHE_TEMPORARY_SUFFIX,
    LIMIT_KEY,
    RATE_LIMIT_CORE_KEY,
    RATE_LIMIT_QUERY_TIMEOUT_SECONDS,
    RATE_LIMIT_RESOURCES_KEY,
    RESET_KEY,
    SPENT_FRACTION_DENOMINATOR,
    SPENT_FRACTION_NUMERATOR,
    USED_KEY,
)
from hooks_constants.mod_handoff_constants import (
    CLAUDE_CONFIG_DIR_ENV_VAR,
    DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME,
)

__all__ = ["CoreRateBudget", "is_core_budget_spent", "read_core_rate_budget"]


@dataclass(frozen=True)
class CoreRateBudget:
    """The core REST limit, the calls used against it, and its reset time in epoch seconds."""

    limit: int
    used: int
    reset: int | None


@dataclass(frozen=True)
class _CachedRead:
    """One rate limit read as the cache file holds it; a failed read has no budget."""

    read_at: float
    budget: CoreRateBudget | None


def is_core_budget_spent(budget: CoreRateBudget) -> bool:
    """Return True when four fifths or more of a readable core limit is used.

    Args:
        budget: The core limit and the calls used against it.
    """
    if budget.limit <= 0:
        return False
    return budget.used * SPENT_FRACTION_DENOMINATOR >= budget.limit * SPENT_FRACTION_NUMERATOR


def _budget_cache_path() -> Path:
    configured_directory = os.environ.get(CLAUDE_CONFIG_DIR_ENV_VAR, "").strip()
    managed_root = (
        Path(configured_directory)
        if configured_directory
        else Path.home() / DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME
    )
    return managed_root / CACHE_DIRECTORY_NAME / CACHE_FILE_NAME


def _whole_number(candidate: object) -> int | None:
    if isinstance(candidate, bool) or not isinstance(candidate, int):
        return None
    return candidate


def _budget_from_fields(all_fields: dict[str, object]) -> CoreRateBudget | None:
    """Return the budget the limit, used and reset fields hold, or None when limit or used is missing."""
    limit = _whole_number(all_fields.get(LIMIT_KEY))
    used = _whole_number(all_fields.get(USED_KEY))
    if limit is None or used is None:
        return None
    return CoreRateBudget(limit=limit, used=used, reset=_whole_number(all_fields.get(RESET_KEY)))


def _fresh_cached_read(cache_path: Path, now: float) -> _CachedRead | None:
    """Return the cached read when it is under five minutes old and well formed, else None."""
    try:
        cached_fields = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(cached_fields, dict):
        return None
    read_at = cached_fields.get(CACHE_READ_AT_KEY)
    if isinstance(read_at, bool) or not isinstance(read_at, (int, float)):
        return None
    if not 0 <= now - read_at < CACHE_MAXIMUM_AGE_SECONDS:
        return None
    return _CachedRead(read_at=float(read_at), budget=_budget_from_fields(cached_fields))


def _queried_core_budget() -> CoreRateBudget | None:
    """Run ``gh api rate_limit`` and return its core budget, or None when the read fails."""
    try:
        completed = subprocess.run(
            list(ALL_RATE_LIMIT_QUERY_ARGUMENTS),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=RATE_LIMIT_QUERY_TIMEOUT_SECONDS,
            check=False,
            creationflags=hidden_window_creation_flags(),
        )
        if completed.returncode != 0:
            return None
        rate_limit_report = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not isinstance(rate_limit_report, dict):
        return None
    all_resources = rate_limit_report.get(RATE_LIMIT_RESOURCES_KEY)
    core_fields = (
        all_resources.get(RATE_LIMIT_CORE_KEY) if isinstance(all_resources, dict) else None
    )
    if not isinstance(core_fields, dict):
        return None
    return _budget_from_fields(core_fields)


def _write_cached_read(cache_path: Path, cached_read: _CachedRead) -> None:
    """Write the read to the cache file through a temporary file, leaving the old file on failure."""
    budget = cached_read.budget
    cached_fields = {
        CACHE_READ_AT_KEY: cached_read.read_at,
        LIMIT_KEY: budget.limit if budget else None,
        USED_KEY: budget.used if budget else None,
        RESET_KEY: budget.reset if budget else None,
    }
    temporary_path: str | None = None
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_path = tempfile.mkstemp(
            dir=cache_path.parent, prefix=cache_path.name, suffix=CACHE_TEMPORARY_SUFFIX
        )
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
            json.dump(cached_fields, temporary_file)
        os.replace(temporary_path, cache_path)
    except OSError:
        if temporary_path is not None:
            Path(temporary_path).unlink(missing_ok=True)


def read_core_rate_budget() -> CoreRateBudget | None:
    """Return the core REST budget from a cache under five minutes old, else from ``gh api rate_limit``.

    A fresh read, failed or not, is written back to the cache, so a broken gh
    is asked again only after five minutes. Returns None when the limit cannot
    be read.
    """
    cache_path = _budget_cache_path()
    now = time.time()
    cached_read = _fresh_cached_read(cache_path, now)
    if cached_read is not None:
        return cached_read.budget
    fresh_read = _CachedRead(read_at=now, budget=_queried_core_budget())
    _write_cached_read(cache_path, fresh_read)
    return fresh_read.budget
