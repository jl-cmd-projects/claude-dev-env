import json
import tempfile
from pathlib import Path

import pytest

from hooks_constants.once_per_session import (
    claim_first_showing,
    clear_showings,
    compaction_count,
)

CLAUDE_COMPACTION_LINE = json.dumps({"type": "system", "subtype": "compact_boundary"})
CODEX_COMPACTION_LINE = json.dumps({"type": "compacted", "payload": {"message": ""}})
QUOTED_COMPACTION_LINE = json.dumps(
    {"type": "user", "message": {"content": 'grep output: {"subtype": "compact_boundary"}'}}
)


@pytest.fixture
def transcript_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    session_transcript = tmp_path / "session.jsonl"
    session_transcript.write_text(json.dumps({"type": "user"}) + "\n", encoding="utf-8")
    return session_transcript


def _append(transcript_path: Path, transcript_line: str) -> None:
    with transcript_path.open("a", encoding="utf-8") as transcript:
        transcript.write(transcript_line + "\n")


def _fields(transcript_path: Path, **all_extra_fields: object) -> dict[str, object]:
    return {"session_id": "s1", "transcript_path": str(transcript_path), **all_extra_fields}


def test_should_show_once_per_session(transcript_path: Path) -> None:
    assert claim_first_showing("hook", _fields(transcript_path)) is True
    assert claim_first_showing("hook", _fields(transcript_path)) is False


def test_should_keep_each_hook_and_session_apart(transcript_path: Path) -> None:
    assert claim_first_showing("hook", _fields(transcript_path)) is True
    assert claim_first_showing("other_hook", _fields(transcript_path)) is True
    assert claim_first_showing("hook", _fields(transcript_path, session_id="s2")) is True


def test_should_give_a_subagent_its_own_showing(transcript_path: Path) -> None:
    assert claim_first_showing("hook", _fields(transcript_path)) is True
    assert claim_first_showing("hook", _fields(transcript_path, agent_id="a1")) is True
    assert claim_first_showing("hook", _fields(transcript_path, agent_id="a1")) is False


@pytest.mark.parametrize("compaction_line", [CLAUDE_COMPACTION_LINE, CODEX_COMPACTION_LINE])
def test_should_show_again_after_a_compaction(transcript_path: Path, compaction_line: str) -> None:
    assert claim_first_showing("hook", _fields(transcript_path)) is True
    _append(transcript_path, compaction_line)
    assert claim_first_showing("hook", _fields(transcript_path)) is True
    assert claim_first_showing("hook", _fields(transcript_path)) is False


def test_should_not_count_a_quoted_compaction_marker(transcript_path: Path) -> None:
    _append(transcript_path, QUOTED_COMPACTION_LINE)
    _append(transcript_path, "not json compact_boundary")
    assert compaction_count(str(transcript_path)) == 0
    _append(transcript_path, CLAUDE_COMPACTION_LINE)
    assert compaction_count(str(transcript_path)) == 1


def test_should_skip_a_line_that_is_not_utf8(transcript_path: Path) -> None:
    with transcript_path.open("ab") as transcript:
        transcript.write(b'{"subtype": "compact_boundary\xff"}\n')
    _append(transcript_path, CLAUDE_COMPACTION_LINE)
    assert compaction_count(str(transcript_path)) == 1


@pytest.mark.parametrize("transcript_value", [None, "", 7])
def test_should_count_no_compaction_without_a_readable_transcript(
    tmp_path: Path, transcript_value: object
) -> None:
    assert compaction_count(transcript_value) == 0
    assert compaction_count(str(tmp_path / "absent.jsonl")) == 0


@pytest.mark.parametrize("session_value", [None, "", 7])
def test_should_show_every_time_without_a_session_id(
    transcript_path: Path, session_value: object
) -> None:
    all_fields = _fields(transcript_path, session_id=session_value)
    assert claim_first_showing("hook", all_fields) is True
    assert claim_first_showing("hook", all_fields) is True


def test_should_clear_only_the_ended_session_markers(transcript_path: Path) -> None:
    claim_first_showing("hook", _fields(transcript_path))
    claim_first_showing("other_hook", _fields(transcript_path, agent_id="a1"))
    claim_first_showing("hook", _fields(transcript_path, session_id="s2"))
    clear_showings("s1")
    assert claim_first_showing("hook", _fields(transcript_path)) is True
    assert claim_first_showing("other_hook", _fields(transcript_path, agent_id="a1")) is True
    assert claim_first_showing("hook", _fields(transcript_path, session_id="s2")) is False


def test_should_show_every_time_when_the_marker_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "absent_directory"))
    assert claim_first_showing("hook", {"session_id": "s1"}) is True
    assert claim_first_showing("hook", {"session_id": "s1"}) is True
