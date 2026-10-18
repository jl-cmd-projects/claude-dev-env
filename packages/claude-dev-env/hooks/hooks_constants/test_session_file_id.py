"""Tests for the shared session id that names per-session temp files."""

from __future__ import annotations

from hooks_constants.session_file_id import session_file_id


def test_should_strip_path_characters_from_the_session_id() -> None:
    assert session_file_id("../a b/c-1_2") == "abc-1_2"


def test_should_fall_back_to_the_default_id_when_nothing_safe_remains() -> None:
    assert session_file_id("../ /") == "default"


def test_should_fall_back_to_the_default_id_for_a_missing_session_id() -> None:
    assert session_file_id(None) == "default"
