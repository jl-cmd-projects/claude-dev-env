"""Tests for transcript_root_search_starts, which reads where a search begins."""

from __future__ import annotations

import pytest

from blocking.transcript_root_search_starts import (
    SearchStart,
    file_search_tool_start,
    joined_path,
    normalized_path,
    walked_transcript_root,
)


@pytest.mark.parametrize(
    ("search_start", "expected_root"),
    [
        (SearchStart("~/.claude/projects", True), "~/.claude/projects"),
        (SearchStart("~/.claude/projects/", True), "~/.claude/projects"),
        (SearchStart("~/.claude/projects/.", True), "~/.claude/projects"),
        (SearchStart("~/.claude/projects/C--x/..", True), "~/.claude/projects"),
        (
            SearchStart(r"C:\Users\dev\.claude-work\projects", True),
            "C:/Users/dev/.claude-work/projects",
        ),
        (
            SearchStart("/h/.claude-profiles/work/projects/*/*.jsonl", False),
            "/h/.claude-profiles/work/projects",
        ),
        (SearchStart("~/.claude/projects/**", True), "~/.claude/projects"),
        (SearchStart("~/.claude/projects/**", False), None),
        (SearchStart("~/.claude/projects", False), None),
        (SearchStart("~/.claude/projects/*01WU*", False), None),
        (SearchStart("~/.claude/projects/C--repo", True), None),
        (SearchStart("~/.claude/skills", True), None),
        (SearchStart("~/notes/projects", True), None),
    ],
)
def test_walked_transcript_root_reads_the_root_a_start_walks(
    search_start: SearchStart, expected_root: str | None
) -> None:
    assert walked_transcript_root(search_start) == expected_root


def test_normalized_path_folds_quotes_backslashes_and_dot_segments() -> None:
    assert normalized_path('"C:\\h\\.claude\\projects\\C--x\\..\\"') == "C:/h/.claude/projects"


def test_joined_path_reads_a_relative_path_from_the_base_directory() -> None:
    assert joined_path("/home/u/.claude", "projects") == "/home/u/.claude/projects"


def test_joined_path_keeps_an_absolute_path() -> None:
    assert joined_path("/cwd", "~/.claude/projects") == "~/.claude/projects"


def test_file_search_tool_start_reads_grep_as_recursive_from_its_path() -> None:
    assert file_search_tool_start("Grep", {"path": "/h/.claude/projects"}, "/cwd") == SearchStart(
        "/h/.claude/projects", True
    )


def test_file_search_tool_start_reads_a_relative_grep_path_from_the_session_directory() -> None:
    assert file_search_tool_start("Grep", {"path": "projects"}, "/h/.claude") == SearchStart(
        "/h/.claude/projects", True
    )


def test_file_search_tool_start_reads_grep_with_no_path_from_the_session_directory() -> None:
    assert file_search_tool_start("Grep", {"pattern": "x"}, "/h/.claude/projects") == (
        SearchStart("/h/.claude/projects", True)
    )


def test_file_search_tool_start_joins_a_glob_pattern_below_its_path() -> None:
    assert file_search_tool_start(
        "Glob", {"pattern": "*/*.jsonl", "path": "C:\\h\\.claude\\projects\\"}, "/cwd"
    ) == SearchStart("C:/h/.claude/projects/*/*.jsonl", False)


def test_file_search_tool_start_keeps_an_absolute_glob_pattern_and_reads_its_recursion() -> None:
    assert file_search_tool_start("Glob", {"pattern": "/h/.claude/projects/**"}, "/cwd") == (
        SearchStart("/h/.claude/projects/**", True)
    )
