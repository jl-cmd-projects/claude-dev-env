"""Tests for the deepen turn-one marker."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import deepen_turn_marker as marker
from hooks_constants.deepen_first_prompt_constants import (
    DEEPEN_SESSION_MARKER_PREFIX,
    DEEPEN_TURN_MARKER_SUFFIX,
)


def test_should_name_the_marker_after_the_transcript_when_there_is_one(tmp_path: Path) -> None:
    transcript_path = str(tmp_path / "session.jsonl")
    assert marker.turn_marker_path({"transcript_path": transcript_path, "session_id": "s"}) == Path(
        transcript_path + DEEPEN_TURN_MARKER_SUFFIX
    )


def test_should_name_the_marker_after_the_session_in_the_temp_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    assert marker.turn_marker_path({"transcript_path": None, "session_id": "abc"}) == (
        tmp_path / f"{DEEPEN_SESSION_MARKER_PREFIX}abc"
    )


def test_should_let_only_the_first_claim_win(tmp_path: Path) -> None:
    fields = {"transcript_path": str(tmp_path / "session.jsonl")}
    assert marker.claim_turn_marker(fields) is True
    assert marker.claim_turn_marker(fields) is False
    assert marker.turn_marker_exists(fields)


def test_should_allow_a_claim_when_the_payload_names_no_session() -> None:
    assert marker.claim_turn_marker({}) is True


def test_should_allow_a_claim_when_the_marker_cannot_be_written(tmp_path: Path) -> None:
    fields = {"transcript_path": str(tmp_path / "missing-folder" / "session.jsonl")}
    assert marker.claim_turn_marker(fields) is True


def test_should_see_the_session_marker_once_a_transcript_path_appears(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    assert marker.claim_turn_marker({"transcript_path": None, "session_id": "abc"}) is True
    later_fields = {"transcript_path": str(tmp_path / "cursor.jsonl"), "session_id": "abc"}
    assert marker.turn_marker_exists(later_fields)
