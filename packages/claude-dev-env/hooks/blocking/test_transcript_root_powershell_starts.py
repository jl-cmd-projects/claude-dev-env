"""Tests for transcript_root_powershell_starts, which reads a cmdlet call's search starts."""

from __future__ import annotations

from blocking.transcript_root_powershell_starts import (
    powershell_listing_search_starts,
    select_string_search_starts,
)
from blocking.transcript_root_search_starts import SearchStart


def test_reads_an_unknown_option_value_as_no_path() -> None:
    assert powershell_listing_search_starts(["-Recurse", "-ea", "0", "-Filter", "*.jsonl"]) == [
        SearchStart(".", True)
    ]


def test_splits_a_comma_path_list() -> None:
    assert powershell_listing_search_starts(["-Path", "a,b"]) == [
        SearchStart("a", False),
        SearchStart("b", False),
    ]


def test_lets_depth_zero_override_recurse() -> None:
    assert powershell_listing_search_starts(["x", "-Recurse", "-Depth", "0"]) == [
        SearchStart("x", False)
    ]


def test_reads_a_glued_depth_as_recursive() -> None:
    assert powershell_listing_search_starts(["x", "-Depth:3"]) == [SearchStart("x", True)]


def test_reads_a_false_recurse_value_as_one_level() -> None:
    assert powershell_listing_search_starts(["x", "-Recurse:$false"]) == [SearchStart("x", False)]


def test_select_string_search_starts_reads_only_its_named_paths() -> None:
    assert select_string_search_starts(["-Path", "p/*.jsonl", "-Pattern", "needle"]) == [
        SearchStart("p/*.jsonl", False)
    ]


def test_reads_recurse_after_a_switch_off_the_list() -> None:
    assert powershell_listing_search_starts(["x", "-Verbose", "-Recurse"]) == [
        SearchStart("x", True)
    ]


def test_reads_a_switch_abbreviation_as_its_switch() -> None:
    assert powershell_listing_search_starts(["x", "-Recu", "-Filter", "*.jsonl"]) == [
        SearchStart("x", True)
    ]


def test_reads_a_directory_abbreviation_without_taking_the_path() -> None:
    assert powershell_listing_search_starts(["-Dire", "x"]) == [SearchStart("x", False)]


def test_reads_a_depth_abbreviation_as_depth() -> None:
    assert powershell_listing_search_starts(["x", "-Dep", "2"]) == [SearchStart("x", True)]


def test_reads_the_path_after_a_common_parameter_switch() -> None:
    assert powershell_listing_search_starts(["-Verbose", "x", "-Recurse"]) == [
        SearchStart("x", True)
    ]
    assert powershell_listing_search_starts(["-WhatIf", "x", "-Recurse"]) == [
        SearchStart("x", True)
    ]
