"""Tests for gh_api_budget_gate, which keeps agents from draining the GitHub API limit."""

from __future__ import annotations

import json
import subprocess
import time
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

import gh_api_budget_gate as gate
import hooks_constants.gh_api_budget as budget_reader

_FIVE_MINUTES_IN_SECONDS = 300
_RESET_EPOCH_SECONDS = 1_900_000_000


class _RateLimitQueries:
    """Stand-in for the ``gh api rate_limit`` subprocess that counts its calls."""

    def __init__(self) -> None:
        self.call_count = 0
        self.stdout_text = ""
        self.raised_error: BaseException | None = None
        self.return_code = 0

    def answer_with(self, limit: int, used: int) -> None:
        self.stdout_text = json.dumps(
            {"resources": {"core": {"limit": limit, "used": used, "reset": _RESET_EPOCH_SECONDS}}}
        )

    def __call__(
        self, *all_arguments: object, **all_options: object
    ) -> subprocess.CompletedProcess[str]:
        self.call_count += 1
        if self.raised_error is not None:
            raise self.raised_error
        return subprocess.CompletedProcess(
            args=all_arguments, returncode=self.return_code, stdout=self.stdout_text, stderr=""
        )


@pytest.fixture
def config_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the managed root at a temporary folder."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def rate_queries(monkeypatch: pytest.MonkeyPatch, config_root: Path) -> _RateLimitQueries:
    """Replace the rate limit subprocess with a counting stand-in that reports a fresh limit."""
    queries = _RateLimitQueries()
    queries.answer_with(limit=5000, used=10)
    monkeypatch.setattr(budget_reader.subprocess, "run", queries)
    return queries


def _cache_path(config_root: Path) -> Path:
    return config_root / "cache" / "gh_api_budget.json"


def _write_cache(config_root: Path, read_at: float, limit: int | None, used: int | None) -> None:
    cache_path = _cache_path(config_root)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {"read_at": read_at, "limit": limit, "used": used, "reset": _RESET_EPOCH_SECONDS}
        ),
        encoding="utf-8",
    )


def _stdout_from_main(payload: dict[str, object]) -> str:
    """Return what main() wrote to stdout for one hook payload."""
    captured_stdout = StringIO()
    with (
        patch("sys.stdin", StringIO(json.dumps(payload))),
        patch("sys.stdout", captured_stdout),
        patch.object(gate, "log_hook_block"),
    ):
        gate.main()
    return captured_stdout.getvalue()


def _bash_reason(command: str) -> str:
    """Return the deny reason main() gives a Bash command, or an empty string when it passes."""
    stdout_text = _stdout_from_main({"tool_name": "Bash", "tool_input": {"command": command}})
    if not stdout_text:
        return ""
    specific_output = json.loads(stdout_text)["hookSpecificOutput"]
    assert specific_output["permissionDecision"] == "deny"
    return specific_output["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        "gh run watch 123",
        "gh run watch",
        "gh -R o/r run watch 123 --exit-status",
        "gh.exe run watch 123",
        "gh pr checks 12 --watch",
        "gh pr checks --watch --interval 10",
        "cd repo && gh run watch 123",
        'bash -c "gh run watch 1"',
        'pwsh -Command "gh pr checks 12 --watch"',
    ],
)
def test_should_detect_watch_commands(command: str) -> None:
    assert gate.runs_gh_watch_command(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "gh pr checks 12",
        "gh run view 123",
        "gh run watch --help",
        'echo "gh run watch"',
        'git commit -m "gh run watch"',
        'grep "gh pr checks --watch" notes.md',
        "watch -n 120 date",
    ],
)
def test_should_not_detect_watch_in_other_commands(command: str) -> None:
    assert gate.runs_gh_watch_command(command) is False


@pytest.mark.parametrize(
    "command",
    [
        "while true; do gh run view 1; sleep 30; done",
        "while true; do gh run view 1; sleep 0.5; done",
        "while true; do gh run view 1; sleep 30s; sleep 20; done",
        'while true; do gh run view "1"; sleep "30"; done',
        "sleep 120 && while :; do gh run view 1; sleep 10; done",
        'while :; do bash -c "gh run view 1"; sleep 10; done',
        "until gh run view 1 --exit-status; do sleep 10; done",
        "for i in 1 2 3; do gh run view 1; sleep 5; done",
        "while true\ndo\n  gh run view 1\n  sleep 30\ndone",
        "while true; do gh run view 1; done",
        "while :; do gh api repos/o/r/actions/runs; done",
        "for ((;;)); do gh run view 1; done",
        "until gh run view 1 --exit-status; do :; done",
        'while [ "$(gh run view 1 --json status -q .status)" != completed ]; do sleep 5; done',
        'bash -c "while true; do gh run view 1; sleep 5; done"',
        "while ($true) { gh run view 1; Start-Sleep 30 }",
        "while ($true) { gh run view 1; Start-Sleep -Seconds 30 }",
        "for (;;) { gh run view 1; Start-Sleep -Milliseconds 500 }",
        "while ($true) { gh run view 1 }",
        "do { gh run view 1; Start-Sleep 5 } while ($true)",
        "foreach ($each in 1..5) { gh run view 1; Start-Sleep -s 2 }",
        "watch -n 5 gh run view 1",
        "watch -n5 'gh run view 1'",
        "watch gh run view 1",
        "watch --interval=30 gh pr checks 12",
        "while :; do for i in 1 2; do gh run view $i; done; sleep 5; done",
    ],
)
def test_should_detect_tight_gh_polling_loops(command: str) -> None:
    assert gate.runs_tight_gh_polling_loop(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "while ($true) { gh run view 1; Start-Sleep 5}",
        "while ($true) { gh run view 1; Start-Sleep -Seconds 5}",
        "while ($true) {gh run view 1}",
        "while($true){gh run view 1; Start-Sleep 5}",
        "foreach ($i in 1..9) {gh run view $i; Start-Sleep 5}",
    ],
)
def test_should_detect_powershell_loops_with_glued_braces(command: str) -> None:
    assert gate.runs_tight_gh_polling_loop(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "1..100 | ForEach-Object { gh run view $_; Start-Sleep 5 }",
        "1..100 | % { gh run view $_; Start-Sleep 5 }",
    ],
)
def test_should_detect_tight_powershell_pipeline_loops(command: str) -> None:
    assert gate.runs_tight_gh_polling_loop(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "1..100 | ForEach-Object { gh run view $_; Start-Sleep 60 }",
        "1..100 | % { gh run view $_; Start-Sleep 60 }",
        "1..100 | ForEach-Object { gh run view $_ }",
        "1..100 | % { gh run view $_ }",
    ],
)
def test_should_pass_slow_and_sleepless_powershell_pipeline_loops(command: str) -> None:
    assert gate.runs_tight_gh_polling_loop(command) is False


@pytest.mark.parametrize(
    "command",
    [
        "for i in 1 2 3; do gh pr view $i; done; while [ ! -f x ]; do sleep 5; done",
        "for i in 1 2 3; do gh pr view $i; done; for j in 1 2; do sleep 2; done",
        "while :; do gh run view ${id}; sleep 60; done",
        "while :; do { gh run view 1; }; sleep 90; done",
        "while ($true) { if ($x) { gh run view 1 }; Start-Sleep 90 }",
        "while ($true) { do { gh run view 1 } while ($x); Start-Sleep 90 }",
    ],
)
def test_should_read_each_separate_loop_on_its_own(command: str) -> None:
    assert gate.runs_tight_gh_polling_loop(command) is False


@pytest.mark.parametrize(
    "command",
    [
        "while ($true) { gh run view 1 }; Start-Sleep 60",
        "while ($true) { gh run view 1 }\nStart-Sleep 60",
        "while ($true) { $s = gh run view 1; Start-Sleep 5 }",
        "while ($true) { $s = gh run view 1 | ConvertFrom-Json; Start-Sleep 5 }",
    ],
)
def test_should_close_a_one_segment_loop_body_and_read_assigned_gh_in_loops(
    command: str,
) -> None:
    assert gate.runs_tight_gh_polling_loop(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "foreach ($i in 1..9) { gh run view $i }; Start-Sleep 5",
        "while ($x) { gh run view 1 }; Start-Sleep 5",
        "1..100 | ForEach-Object { gh run view $_ }; Start-Sleep 5",
        "1..100 | ForEach-Object { gh run view $_ } | Out-Null; Start-Sleep 5",
    ],
)
def test_should_not_count_a_sleep_after_a_one_segment_loop_body(command: str) -> None:
    assert gate.runs_tight_gh_polling_loop(command) is False


@pytest.mark.parametrize(
    "command",
    ["$s = gh run watch 1", "$script:s = gh run watch 1", "$s += gh run watch 1"],
)
def test_should_deny_a_watch_assigned_to_a_powershell_variable(
    config_root: Path, rate_queries: _RateLimitQueries, command: str
) -> None:
    assert _bash_reason(command) == _bash_reason("gh run watch 1") != ""


@pytest.mark.parametrize("command", ['$s = "gh run watch 1"', "$s = 'gh'"])
def test_should_pass_gh_text_assigned_to_a_powershell_variable(
    config_root: Path, rate_queries: _RateLimitQueries, command: str
) -> None:
    _write_cache(config_root, time.time(), limit=5000, used=4999)
    assert _bash_reason(command) == ""


def test_should_deny_an_assigned_read_on_a_spent_budget(
    config_root: Path, rate_queries: _RateLimitQueries
) -> None:
    _write_cache(config_root, time.time(), limit=5000, used=4000)
    assert "4000 of 5000" in _bash_reason("$s = gh pr view 1")


def test_should_pass_an_assigned_read_just_under_four_fifths(
    config_root: Path, rate_queries: _RateLimitQueries
) -> None:
    _write_cache(config_root, time.time(), limit=5000, used=3999)
    assert _bash_reason("$s = gh pr view 1") == ""


def test_should_pass_a_token_assignment_with_no_cache_and_no_gh_on_path(
    config_root: Path, rate_queries: _RateLimitQueries
) -> None:
    rate_queries.raised_error = FileNotFoundError("gh")
    command = "$env:GH_TOKEN = gh auth token -u account-a; gh repo list; Remove-Item Env:GH_TOKEN"
    assert _bash_reason(command) == ""
    assert rate_queries.call_count == 1


@pytest.mark.parametrize(
    "command",
    ["if ($x) {gh run watch 1}", "try {gh run watch 1} catch {}"],
)
def test_should_detect_watch_behind_a_glued_brace(command: str) -> None:
    assert gate.runs_gh_watch_command(command) is True


def test_should_not_detect_watch_in_quoted_braced_text() -> None:
    assert gate.runs_gh_watch_command('echo "{gh run watch}"') is False


def test_should_classify_a_read_behind_a_glued_brace_as_budgeted() -> None:
    assert gate.runs_budgeted_gh_read("if ($x) {gh pr view 1}") is True


@pytest.mark.parametrize(
    "command",
    [
        "for x in a b c; do gh pr view $x; done",
        "foreach ($x in $all) { gh pr view $x }",
        "while read pr; do gh pr view $pr; done < prs.txt",
        "while true; do gh run view 1; sleep 60; done",
        "while true; do gh run view 1; sleep 1m; done",
        "while :; do gh run view 1; sleep 30; sleep 30; done",
        "gh pr list | while read n; do echo $n; sleep 1; done",
        "gh run view 1; for f in a b; do echo $f; sleep 1; done",
        "until gh run view 1 --exit-status; do sleep 60; done",
        "while ($true) { gh run view 1; Start-Sleep -Seconds 90 }",
        "while ($true) { gh run view 1; Start-Sleep -Milliseconds 60000 }",
        "while true; do gh run view 1; sleep $delay; done",
        "while true; do date; sleep 1; done",
        "watch -n 60 gh run view 1",
        "watch -n 1 date",
        "gh run view 1",
        'echo "while true; do gh run view 1; sleep 1; done"',
    ],
)
def test_should_pass_finite_slow_and_gh_free_loops(command: str) -> None:
    assert gate.runs_tight_gh_polling_loop(command) is False


def test_watch_reason_names_a_loop_form_that_passes_the_loop_check(config_root: Path) -> None:
    reason = _bash_reason("gh run watch 123")
    assert "60" in reason
    assert "gh run view" in reason
    suggested_loop = reason.split("`")[1]
    assert "gh run view" in suggested_loop
    assert gate.runs_tight_gh_polling_loop(suggested_loop) is False
    assert gate.runs_gh_watch_command(suggested_loop) is False


@pytest.mark.parametrize(
    "command",
    [
        "gh api repos/o/r/pulls",
        "gh api -X GET repos/o/r/pulls -f state=open",
        "gh api --paginate repos/o/r/issues",
        "gh pr view 12",
        "gh pr list",
        "gh pr status",
        "gh pr checks 12",
        "gh pr diff 12",
        "gh issue view 4",
        "gh run view 123",
        "gh run list -L 5",
        "gh run download 123",
        "gh release view v1",
        "gh search prs repo:o/r",
        "gh status",
        "gh -R o/r repo view",
        "cd repo && gh pr view 12",
        "x=$(gh api user -q .login)",
    ],
)
def test_should_classify_remote_reads_as_budgeted(command: str) -> None:
    assert gate.runs_budgeted_gh_read(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create --title t --body b",
        "gh pr merge 12 --squash",
        "gh pr comment 12 --body hi",
        "gh pr ready 12",
        "gh workflow run ci.yml",
        "gh api -X POST repos/o/r/issues -f title=t",
        "gh api --method=PATCH repos/o/r/issues/1",
        "gh api repos/o/r/issues -f title=t",
        "gh api repos/o/r/issues --input body.json",
        "gh api graphql -f query='query{viewer{login}}'",
        "gh api rate_limit",
        "gh auth status",
        "gh auth token",
        "gh --version",
        "gh help",
        "gh pr view 12 --help",
        "gh",
        'echo "gh pr view 12"',
        "git log --oneline",
    ],
)
def test_should_not_budget_writes_local_calls_and_other_buckets(command: str) -> None:
    assert gate.runs_budgeted_gh_read(command) is False


def test_fresh_cache_at_four_fifths_denies_a_read_with_used_limit_and_reset(
    config_root: Path, rate_queries: _RateLimitQueries
) -> None:
    _write_cache(config_root, time.time(), limit=5000, used=4000)
    reason = _bash_reason("gh pr view 12")
    assert "4000" in reason
    assert "5000" in reason
    assert time.strftime("%H:%M", time.gmtime(_RESET_EPOCH_SECONDS)) in reason
    assert "git" in reason
    assert "wait" in reason.lower()
    assert rate_queries.call_count == 0


def test_out_of_range_reset_still_denies_without_a_reset_time(
    config_root: Path, rate_queries: _RateLimitQueries
) -> None:
    cache_path = _cache_path(config_root)
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(
        json.dumps({"read_at": time.time(), "limit": 5000, "used": 4500, "reset": 10**30}),
        encoding="utf-8",
    )
    reason = _bash_reason("gh pr view 12")
    assert "4500 of 5000" in reason
    assert "resets at" not in reason


def test_fresh_cache_just_under_four_fifths_passes(
    config_root: Path, rate_queries: _RateLimitQueries
) -> None:
    _write_cache(config_root, time.time(), limit=5000, used=3999)
    assert _bash_reason("gh pr view 12") == ""
    assert rate_queries.call_count == 0


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create --title t --body b",
        "gh pr merge 12 --squash",
        "gh api -X POST repos/o/r/issues -f title=t",
        "gh api graphql -f query='query{viewer{login}}'",
        "gh api rate_limit",
        "gh auth status",
        "gh --version",
        "gh pr view 12 --help",
    ],
)
def test_spent_budget_still_passes_writes_and_unbudgeted_calls(
    config_root: Path, rate_queries: _RateLimitQueries, command: str
) -> None:
    _write_cache(config_root, time.time(), limit=5000, used=4999)
    assert _bash_reason(command) == ""


def test_stale_cache_triggers_one_query_and_rewrites_the_file(
    config_root: Path, rate_queries: _RateLimitQueries
) -> None:
    _write_cache(config_root, time.time() - _FIVE_MINUTES_IN_SECONDS - 1, limit=5000, used=4500)
    assert _bash_reason("gh pr view 12") == ""
    assert _bash_reason("gh pr view 13") == ""
    assert rate_queries.call_count == 1
    rewritten_cache = json.loads(_cache_path(config_root).read_text(encoding="utf-8"))
    assert rewritten_cache["used"] == 10
    assert rewritten_cache["limit"] == 5000
    assert rewritten_cache["reset"] == _RESET_EPOCH_SECONDS
    assert time.time() - rewritten_cache["read_at"] < _FIVE_MINUTES_IN_SECONDS


def test_missing_cache_query_that_reports_a_spent_budget_denies(
    config_root: Path, rate_queries: _RateLimitQueries
) -> None:
    rate_queries.answer_with(limit=5000, used=4800)
    assert "4800" in _bash_reason("gh run view 1")
    assert rate_queries.call_count == 1


@pytest.mark.parametrize(
    "raised_error",
    [
        subprocess.TimeoutExpired(cmd="gh", timeout=10),
        FileNotFoundError("gh"),
        PermissionError("gh"),
    ],
)
def test_failed_query_allows_and_is_not_retried_inside_five_minutes(
    config_root: Path, rate_queries: _RateLimitQueries, raised_error: BaseException
) -> None:
    rate_queries.raised_error = raised_error
    assert _bash_reason("gh pr view 12") == ""
    assert _bash_reason("gh pr view 12") == ""
    assert rate_queries.call_count == 1


def test_nonzero_query_exit_allows(config_root: Path, rate_queries: _RateLimitQueries) -> None:
    rate_queries.answer_with(limit=5000, used=4900)
    rate_queries.return_code = 1
    assert _bash_reason("gh pr view 12") == ""
    assert rate_queries.call_count == 1


@pytest.mark.parametrize(
    "stdout_text",
    [
        "not json",
        "{}",
        json.dumps({"resources": {"core": {"limit": 0, "used": 0}}}),
        json.dumps({"resources": {"core": {"used": 4900}}}),
        json.dumps([1, 2]),
    ],
)
def test_unreadable_query_output_allows(
    config_root: Path, rate_queries: _RateLimitQueries, stdout_text: str
) -> None:
    rate_queries.stdout_text = stdout_text
    assert _bash_reason("gh pr view 12") == ""
    assert rate_queries.call_count == 1


@pytest.mark.parametrize(
    "cache_text", ["{", "[]", '{"read_at": "soon", "limit": 5000, "used": 4900}', ""]
)
def test_corrupt_cache_counts_as_stale(
    config_root: Path, rate_queries: _RateLimitQueries, cache_text: str
) -> None:
    cache_path = _cache_path(config_root)
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(cache_text, encoding="utf-8")
    assert _bash_reason("gh pr view 12") == ""
    assert rate_queries.call_count == 1


def test_unwritable_cache_folder_allows(
    config_root: Path, rate_queries: _RateLimitQueries, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _refuse_replace(*all_arguments: object) -> None:
        raise PermissionError("cache")

    monkeypatch.setattr(budget_reader.os, "replace", _refuse_replace)
    rate_queries.answer_with(limit=5000, used=10)
    assert _bash_reason("gh pr view 12") == ""


def test_unreadable_cache_file_allows(
    config_root: Path, rate_queries: _RateLimitQueries, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_cache(config_root, time.time(), limit=5000, used=4900)

    def _refuse_read(*all_arguments: object, **all_options: object) -> str:
        raise PermissionError("cache")

    monkeypatch.setattr(Path, "read_text", _refuse_read)
    assert _bash_reason("gh pr view 12") == ""


def test_command_without_gh_reads_no_cache_and_runs_no_query(
    config_root: Path, rate_queries: _RateLimitQueries
) -> None:
    _write_cache(config_root, time.time() - _FIVE_MINUTES_IN_SECONDS - 1, limit=5000, used=4900)
    assert _bash_reason("git log --oneline; while true; do date; sleep 1; done") == ""
    assert rate_queries.call_count == 0


def test_watch_command_is_denied_with_the_timed_read_advice(
    config_root: Path, rate_queries: _RateLimitQueries
) -> None:
    reason = _bash_reason("gh run watch 123")
    assert "watch" in reason
    assert "60" in reason
    assert "task notification" in reason
    assert rate_queries.call_count == 0


def test_tight_loop_is_denied_with_the_sixty_second_advice(
    config_root: Path, rate_queries: _RateLimitQueries
) -> None:
    reason = _bash_reason("while true; do gh run view 1; sleep 10; done")
    assert "60" in reason
    assert "sleep" in reason
    assert reason != _bash_reason("gh run watch 1")


def test_watch_refusal_comes_before_the_loop_refusal(
    config_root: Path, rate_queries: _RateLimitQueries
) -> None:
    watch_reason = _bash_reason("gh run watch 1")
    assert _bash_reason("while true; do gh run watch 1; sleep 5; done") == watch_reason


def test_powershell_payload_with_watch_is_denied(
    config_root: Path, rate_queries: _RateLimitQueries
) -> None:
    stdout_text = _stdout_from_main(
        {"tool_name": "PowerShell", "tool_input": {"command": "gh pr checks 12 --watch"}}
    )
    assert json.loads(stdout_text)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_other_tool_payload_emits_nothing(
    config_root: Path, rate_queries: _RateLimitQueries
) -> None:
    _write_cache(config_root, time.time(), limit=5000, used=4900)
    assert (
        _stdout_from_main({"tool_name": "Write", "tool_input": {"command": "gh run watch 1"}}) == ""
    )
    assert rate_queries.call_count == 0
