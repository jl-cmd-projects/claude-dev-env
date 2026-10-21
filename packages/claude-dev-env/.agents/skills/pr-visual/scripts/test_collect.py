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


ISSUE_URL = "https://github.com/example/project/issues/10"
EPIC = {"number": 10, "title": "Synthetic epic", "state": "open", "updated_at": "2026-10-19T12:00:00Z", "labels": [], "body": "Tasks below."}
TASK_WITH_FIX = {"number": 11, "title": "Task with a fix", "state": "open", "updated_at": "2026-10-19T12:00:00Z", "labels": [], "body": "Fix: https://github.com/example/project/pull/20"}
TASK_IN_FLIGHT = {"number": 12, "title": "Task in flight", "state": "open", "updated_at": "2026-10-19T12:00:00Z", "labels": [], "body": "Fix: https://github.com/example/project/pull/21"}
TASK_LEFT = {"number": 13, "title": "Task left", "state": "closed", "updated_at": "2026-10-19T12:00:00Z", "labels": [], "body": None}
FINISHED_PULL = {"number": 20, "title": "Finished fix", "state": "closed", "draft": False, "merged_at": "2026-10-19T11:00:00Z"}
OPEN_PULL = {"number": 21, "title": "Open fix", "state": "open", "draft": True, "merged_at": None}


def _tracker_github(refreshed_epic: dict) -> Mock:
    responses = {
        "repos/example/project/issues/10": [EPIC, refreshed_epic],
        "repos/example/project/issues/10/sub_issues?per_page=100&page=1": [[TASK_WITH_FIX, TASK_IN_FLIGHT, TASK_LEFT]],
        "repos/example/project/issues/11/sub_issues?per_page=100&page=1": [[]],
        "repos/example/project/issues/12/sub_issues?per_page=100&page=1": [[]],
        "repos/example/project/issues/13/sub_issues?per_page=100&page=1": [[]],
        "repos/example/project/pulls/20": [FINISHED_PULL],
        "repos/example/project/pulls/21": [OPEN_PULL],
    }
    return Mock(side_effect=lambda endpoint, *options: responses[endpoint].pop(0))


def test_issue_capture_counts_each_task_by_its_linked_pull_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An epic snapshot records each task's fix state and hashes every captured record."""
    monkeypatch.setattr(collect, "_api", _tracker_github(EPIC))
    collect.collect_issue(ISSUE_URL, tmp_path)
    destination = next((tmp_path / "issue-10").iterdir())
    snapshot = json.loads((destination / "snapshot.json").read_text())
    tracker = json.loads((destination / "head/tracker.json").read_text())
    assert tracker["counts"] == {"open": 2, "closed": 1, "merged_pull": 1, "open_pull": 1, "no_pull": 1}
    assert [each_child["progress"] for each_child in tracker["children"]] == ["merged_pull", "open_pull", "no_pull"]
    assert snapshot["kind"] == "issue"
    assert snapshot["metadata"]["tracked_issues"] == 4
    assert (destination / "head/issues/11.md").read_text() == TASK_WITH_FIX["body"] + "\n"
    assert json.loads((destination / "head/pulls/21.json").read_text())["draft"] is True
    for each_file in snapshot["files"]:
        assert hashlib.sha256((destination / each_file["captures"]["head"]["path"]).read_bytes()).hexdigest() == each_file["captures"]["head"]["sha256"]


def test_edited_issue_never_saves_a_tracker_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An epic edited during capture requires another capture before rendering."""
    edited = {**EPIC, "updated_at": "2026-10-19T12:05:00Z"}
    monkeypatch.setattr(collect, "_api", _tracker_github(edited))
    with pytest.raises(collect.CaptureRunFatal, match="changed during capture"):
        collect.collect_issue(ISSUE_URL, tmp_path)
    assert not list(tmp_path.rglob("snapshot.json"))
