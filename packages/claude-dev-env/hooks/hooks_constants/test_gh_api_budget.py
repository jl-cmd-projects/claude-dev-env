"""Tests for gh_api_budget, which reads the GitHub core REST limit through a five minute cache."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HOOKS_ROOT = Path(__file__).resolve().parent.parent
if str(_HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOOKS_ROOT))

import hooks_constants.gh_api_budget as budget_reader

_RESET_EPOCH_SECONDS = 1_900_000_000


class _RateLimitQueries:
    """Stand-in for the ``gh api rate_limit`` subprocess that counts its calls."""

    def __init__(self, limit: int, used: int) -> None:
        self.call_count = 0
        self.stdout_text = json.dumps(
            {"resources": {"core": {"limit": limit, "used": used, "reset": _RESET_EPOCH_SECONDS}}}
        )

    def __call__(
        self, *all_arguments: object, **all_options: object
    ) -> subprocess.CompletedProcess[str]:
        self.call_count += 1
        return subprocess.CompletedProcess(
            args=all_arguments, returncode=0, stdout=self.stdout_text, stderr=""
        )


@pytest.fixture
def cache_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the managed root at a temporary folder and return the cache file inside it."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    return tmp_path / "cache" / "gh_api_budget.json"


@pytest.fixture
def rate_queries(monkeypatch: pytest.MonkeyPatch) -> _RateLimitQueries:
    """Replace the rate limit subprocess with a stand-in that reports 4200 of 5000 used."""
    queries = _RateLimitQueries(limit=5000, used=4200)
    monkeypatch.setattr(budget_reader.subprocess, "run", queries)
    return queries


def _write_cache(cache_path: Path, read_at: float, used: int) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {"read_at": read_at, "limit": 5000, "used": used, "reset": _RESET_EPOCH_SECONDS}
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("limit", "used", "is_spent"),
    [(5000, 3999, False), (5000, 4000, True), (60, 48, True), (60, 47, False), (0, 0, False)],
)
def test_should_count_the_budget_spent_at_four_fifths(
    limit: int, used: int, is_spent: bool
) -> None:
    budget = budget_reader.CoreRateBudget(limit=limit, used=used, reset=None)
    assert budget_reader.is_core_budget_spent(budget) is is_spent


def test_should_read_a_fresh_cache_without_a_query(
    cache_path: Path, rate_queries: _RateLimitQueries
) -> None:
    _write_cache(cache_path, time.time(), used=4000)
    assert budget_reader.read_core_rate_budget() == budget_reader.CoreRateBudget(
        limit=5000, used=4000, reset=_RESET_EPOCH_SECONDS
    )
    assert rate_queries.call_count == 0


def test_should_query_once_for_a_stale_cache_and_store_the_answer(
    cache_path: Path, rate_queries: _RateLimitQueries
) -> None:
    _write_cache(cache_path, time.time() - 301, used=10)
    expected_budget = budget_reader.CoreRateBudget(
        limit=5000, used=4200, reset=_RESET_EPOCH_SECONDS
    )
    assert budget_reader.read_core_rate_budget() == expected_budget
    assert budget_reader.read_core_rate_budget() == expected_budget
    assert rate_queries.call_count == 1
    assert json.loads(cache_path.read_text(encoding="utf-8"))["used"] == 4200


def test_should_return_none_and_cache_the_failure_when_gh_is_missing(
    cache_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_calls: list[object] = []

    def _missing_gh(*all_arguments: object, **all_options: object) -> None:
        all_calls.append(all_arguments)
        raise FileNotFoundError("gh")

    monkeypatch.setattr(budget_reader.subprocess, "run", _missing_gh)
    assert budget_reader.read_core_rate_budget() is None
    assert budget_reader.read_core_rate_budget() is None
    assert len(all_calls) == 1
    assert json.loads(cache_path.read_text(encoding="utf-8"))["limit"] is None
