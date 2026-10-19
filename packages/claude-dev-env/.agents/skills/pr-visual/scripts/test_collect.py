"""Check immutable capture and stale-head rejection with synthetic GitHub data."""
import base64
import copy
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

import collect

REPOSITORY = "example/project"
PR_URL = "https://github.com/example/project/pull/1"
HEAD_SHA = "b" * 40
BASE_SHA = "c" * 40
MERGE_BASE_SHA = "a" * 40
CONTENT = b"print('captured')\n"
METADATA = {"head": {"sha": HEAD_SHA, "repo": {"full_name": REPOSITORY}}, "base": {"sha": BASE_SHA, "repo": {"full_name": REPOSITORY}}, "changed_files": 1, "state": "open"}
CHANGED_FILES = [{"filename": "handler.py", "status": "modified", "patch": "fixture patch"}]
BLOB = {"encoding": "base64", "content": base64.b64encode(CONTENT).decode()}


def test_capture_uses_merge_base_and_hashes_saved_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Both saved sides match the immutable revisions used by the diff."""
    github = Mock(side_effect=[METADATA, {"merge_base_commit": {"sha": MERGE_BASE_SHA}}, CHANGED_FILES, BLOB, BLOB, METADATA])
    monkeypatch.setattr(collect, "_api", github)
    collect.collect(PR_URL, tmp_path)
    destination = tmp_path / "pr-1" / HEAD_SHA
    snapshot = json.loads((destination / "snapshot.json").read_text())
    assert snapshot["diff_base"] == MERGE_BASE_SHA
    for each_side in ("base", "head"):
        assert (destination / each_side / "handler.py").read_bytes() == CONTENT
        assert snapshot["files"][0]["captures"][each_side]["sha256"] == hashlib.sha256(CONTENT).hexdigest()
    all_endpoints = [each_call.args[0] for each_call in github.call_args_list]
    assert any(each_endpoint.endswith(f"?ref={MERGE_BASE_SHA}") for each_endpoint in all_endpoints)


def test_moved_head_never_saves_a_complete_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A changed PR head requires another capture before rendering."""
    moved = copy.deepcopy(METADATA)
    moved["head"]["sha"] = "d" * 40
    github = Mock(side_effect=[METADATA, {"merge_base_commit": {"sha": MERGE_BASE_SHA}}, CHANGED_FILES, BLOB, BLOB, moved])
    monkeypatch.setattr(collect, "_api", github)
    with pytest.raises(collect.CaptureRunFatal, match="changed during capture"):
        collect.collect(PR_URL, tmp_path)
    assert not list(tmp_path.rglob("snapshot.json"))


def test_incomplete_changed_file_list_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """A truncated file listing cannot imply complete coverage."""
    monkeypatch.setattr(collect, "_api", Mock(return_value=[]))
    with pytest.raises(collect.CaptureRunFatal, match="incomplete"):
        collect._changed_files(REPOSITORY, "1", 1)
