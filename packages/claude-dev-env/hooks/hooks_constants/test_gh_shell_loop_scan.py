"""Pin how gh_shell_loop_scan reads shell loops and ``watch`` calls that poll gh."""

from __future__ import annotations

import pytest

from hooks_constants import gh_shell_loop_scan


@pytest.mark.parametrize(
    ("command_text", "is_tight"),
    [
        ("while :; do gh run view 1; sleep 30; done", True),
        ("while ($true) { gh run view 1 }", True),
        ("for (;;) { gh run view 1; Start-Sleep -Milliseconds 500 }", True),
        ("while :; do gh run view 1; sleep .5; done", True),
        ("while ($true) { gh run view 1; Start-Sleep -Seconds 5 -Verbose }", True),
        ("while ($true) { gh run view 1; Start-Sleep -Duration 00:00:05 }", True),
        ("while ($true) { gh run view 1; Start-Sleep -Duration 00:01:30 }", False),
        ("while :; do gh run view 1; sleep 30; sleep 30; done", False),
        ("while :; do gh run view 1; sleep 1m; done", False),
        ("for x in a b c; do gh pr view $x; done", False),
        ("while :; do gh run view 1; sleep $delay; done", False),
        ("while :; do date; sleep 5; done", False),
    ],
)
def test_should_flag_a_loop_that_calls_gh_with_too_little_sleep(
    command_text: str, is_tight: bool
) -> None:
    assert gh_shell_loop_scan.is_tight_gh_loop_text(command_text) is is_tight


@pytest.mark.parametrize(
    ("all_segment_tokens", "is_tight"),
    [
        (["watch", "-n", "5", "gh", "run", "view", "1"], True),
        (["watch", "gh", "run", "view", "1"], True),
        (["watch", "-n", "60", "gh", "run", "view", "1"], False),
        (["watch", "-n", "5", "date"], False),
        (["gh", "run", "view", "1"], False),
    ],
)
def test_should_flag_a_watch_on_gh_under_sixty_seconds(
    all_segment_tokens: list[str], is_tight: bool
) -> None:
    assert gh_shell_loop_scan.is_tight_gh_watch_segment(all_segment_tokens) is is_tight
