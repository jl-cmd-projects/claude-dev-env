"""Tests for transcript_root_shell_starts, which reads where a shell search begins."""

from __future__ import annotations

import pytest

from blocking.transcript_root_search_starts import SearchStart, walked_transcript_root
from blocking.transcript_root_shell_starts import shell_command_search_starts

ROOT = "C:/Users/dev/.claude/projects"


def _walked_roots(command: str, cwd: str = "", is_powershell: bool = False) -> list[str]:
    return [
        each_root
        for each_root in (
            walked_transcript_root(each_start)
            for each_start in shell_command_search_starts(command, cwd, is_powershell)
        )
        if each_root
    ]


def test_expands_a_variable_the_command_assigns() -> None:
    all_starts = shell_command_search_starts(
        f'$p="{ROOT}"; Get-ChildItem $p -Recurse -Filter *.jsonl', "", True
    )
    assert SearchStart(ROOT, True) in all_starts


def test_reads_a_name_listing_as_one_level() -> None:
    all_starts = shell_command_search_starts(
        f'Get-ChildItem {ROOT} -Directory -Filter "*01WUQeBG*"', "", True
    )
    assert SearchStart(ROOT, False) in all_starts


def test_skips_a_command_that_never_names_a_projects_folder() -> None:
    assert shell_command_search_starts("grep -r needle /src", "/home/u", False) == []


@pytest.mark.parametrize(
    ("command", "cwd"),
    [
        pytest.param(f"grep -rC2 needle {ROOT}", "", id="short-cluster-with-digit"),
        pytest.param(f"grep -R1 needle {ROOT}", "", id="short-cluster-r-digit"),
        pytest.param(f"grep -r needle {ROOT}/.", "", id="dot-segment"),
        pytest.param("cd ~/.claude/projects && grep -r needle", "", id="cd-then-default-path"),
        pytest.param("cd ~/.claude/projects && grep -rn -C 2 needle", "", id="grep-option-value"),
        pytest.param("cd ~/.claude/projects && rg -g '*.jsonl' needle", "", id="rg-option-value"),
        pytest.param("grep -r -e a -e b", "/home/u/.claude/projects", id="grep-pattern-options"),
        pytest.param("grep -r needle", "/home/u/.claude/projects", id="session-directory"),
        pytest.param("cd && grep -r needle .claude/projects", "/x", id="bare-cd-goes-home"),
        pytest.param(f"p={ROOT}; grep -r x $p; p={ROOT}/C--x", "", id="assignment-after-use"),
        pytest.param(f"grep -d recurse needle {ROOT}", "", id="grep-directories-recurse"),
        pytest.param(f"grep --directories=recurse needle {ROOT}", "", id="grep-glued-directories"),
        pytest.param(f"rg needle {ROOT}", "", id="rg-default"),
        pytest.param(f"rg --files {ROOT}", "", id="rg-files"),
        pytest.param(f"rg --files -g '*.jsonl' {ROOT}", "", id="rg-files-glob"),
        pytest.param(f"fd . {ROOT}", "", id="fd"),
        pytest.param(f"tree {ROOT}", "", id="tree"),
        pytest.param(f"find {ROOT} -name '*.jsonl'", "", id="find"),
        pytest.param(f"ls -R {ROOT}", "", id="ls-recursive"),
        pytest.param(f"cat {ROOT}/*/*.jsonl | grep needle", "", id="cat-every-transcript"),
        pytest.param(f"pushd {ROOT} && grep -r needle .", "", id="pushd-then-walk"),
        pytest.param(
            f"pushd {ROOT} && pushd {ROOT}/C--x && popd && grep -r needle .",
            "",
            id="popd-one-level",
        ),
    ],
)
def test_reads_a_bash_walk_of_the_root(command: str, cwd: str) -> None:
    assert _walked_roots(command, cwd)


@pytest.mark.parametrize(
    ("command", "cwd"),
    [
        pytest.param(f'$P="{ROOT}"; gci $p -Recurse', "", id="variable-case"),
        pytest.param(
            '$h="C:/Users/dev"; $p="$h/.claude/projects"; gci $p -Recurse', "", id="chained"
        ),
        pytest.param(
            r"Set-Location C:\Users\dev\.claude\projects; Get-ChildItem -Recurse -Filter *.jsonl",
            "",
            id="backslash-set-location",
        ),
        pytest.param("Set-Location C:/Users/dev/.claude; gci projects -Recurse", "", id="relative"),
        pytest.param("Get-ChildItem -Recurse -ea 0 -Filter *.jsonl", ROOT, id="unknown-option"),
        pytest.param(f"gci C:/x,{ROOT} -Recurse", "", id="comma-path-list"),
        pytest.param(f"gci {ROOT} -Depth:3", "", id="glued-depth"),
        pytest.param(f"ls -r {ROOT}", "", id="ls-alias-recurse"),
        pytest.param(f"ls {ROOT} -Depth 2", "", id="ls-alias-depth"),
        pytest.param(f"Get-Content {ROOT}/*/*.jsonl | Select-String x", "", id="get-content"),
    ],
)
def test_reads_a_powershell_walk_of_the_root(command: str, cwd: str) -> None:
    assert _walked_roots(command, cwd, is_powershell=True)


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"rg --max-depth 1 needle {ROOT}", id="rg-spaced-max-depth"),
        pytest.param(f"rg --max-depth=1 needle {ROOT}", id="rg-glued-max-depth"),
        pytest.param(f"find {ROOT} -maxdepth 1 -type d", id="find-maxdepth"),
        pytest.param(f"tree -L 1 {ROOT}", id="tree-one-level"),
        pytest.param(f"ls {ROOT}/**", id="ls-double-star"),
        pytest.param(f"grep -r needle {ROOT}/C--repo", id="one-project-folder"),
        pytest.param(f"grep -eremote {ROOT}", id="glued-pattern-is-no-recursion"),
        pytest.param(f"git status {ROOT}", id="plain-program-on-the-root"),
        pytest.param(f"p={ROOT}/C--x; grep -r x $p; p={ROOT}", id="assignment-after-scoped-use"),
        pytest.param(f"pushd {ROOT} && popd && grep -r needle .", id="popd-returns"),
    ],
)
def test_reads_a_scoped_bash_search_as_no_walk(command: str) -> None:
    assert _walked_roots(command) == []


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"gci {ROOT} -Recurse -Depth 0", id="depth-zero-after-recurse"),
        pytest.param(f"gci {ROOT} -Depth 0 -Recurse", id="depth-zero-before-recurse"),
        pytest.param(f"ls {ROOT} -ReadOnly", id="ls-alias-switch"),
        pytest.param(f"Select-String -Path {ROOT}/*01WU*/x.jsonl -Pattern a", id="select-string"),
    ],
)
def test_reads_a_scoped_powershell_search_as_no_walk(command: str) -> None:
    assert _walked_roots(command, is_powershell=True) == []
