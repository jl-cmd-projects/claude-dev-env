"""Tests for check_windows_api_none."""

from __future__ import annotations

from code_rules_enforcer import check_windows_api_none


def test_should_flag_win32gui_call_passing_none() -> None:
    source = "win32gui.SetWindowPos(window_handle, " + "None)\n"
    assert check_windows_api_none(source) == [
        "Line 1: win32gui call with None - use 0 for unused int params"
    ]


def test_should_allow_win32gui_call_passing_zero() -> None:
    source = "win32gui.SetWindowPos(window_handle, 0)\n"
    assert check_windows_api_none(source) == []
