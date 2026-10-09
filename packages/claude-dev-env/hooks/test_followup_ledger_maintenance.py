"""Behavior tests for clearing and normalizing the follow-up ledger."""

import json
import sys
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

from followup_ledger import (
    FollowupFinding,
    all_recorded_findings,
    finding_path,
    followup_directory,
    record_followup_finding,
)
from followup_ledger_maintenance import clear_recorded_findings, normalize_ledger


def test_clear_removes_every_finding_and_the_legacy_ledger_but_keeps_the_ignore(
    tmp_path: Path,
) -> None:
    record_followup_finding(tmp_path, FollowupFinding("r1", "a.py", "m1", "r1"))
    record_followup_finding(tmp_path, FollowupFinding("r2", "b.py", "m2", "r2"))
    legacy_path = followup_directory(tmp_path) / "smells.jsonl"
    legacy_path.write_text("{}\n", encoding="utf-8")

    clear_recorded_findings(tmp_path)

    assert all_recorded_findings(tmp_path) == ()
    assert not legacy_path.exists()
    assert (followup_directory(tmp_path) / ".gitignore").is_file()


def test_normalize_splits_a_legacy_ledger_and_keeps_the_first_origin(
    tmp_path: Path,
) -> None:
    first_record = {
        "rule_id": "r1",
        "file_path": "a.py",
        "message": "m1",
        "origin_commit": "aaa1111",
    }
    later_record = {**first_record, "origin_commit": "bbb2222"}
    legacy_path = followup_directory(tmp_path) / "smells.jsonl"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(
        f"{json.dumps(first_record)}\n{json.dumps(later_record)}\nnot json\n",
        encoding="utf-8",
    )

    normalization = normalize_ledger(tmp_path)

    assert normalization.migrated_count == 2
    assert normalization.removed_count == 0
    assert not legacy_path.exists()
    assert [each.origin_commit for each in all_recorded_findings(tmp_path)] == [
        "aaa1111"
    ]


def test_normalize_renames_a_misnamed_finding_file(tmp_path: Path) -> None:
    finding = FollowupFinding("r1", "a.py", "m1", "r1")
    record_followup_finding(tmp_path, finding)
    expected_path = finding_path(tmp_path, finding)
    misnamed_path = expected_path.with_name("misnamed.json")
    expected_path.rename(misnamed_path)

    normalization = normalize_ledger(tmp_path)

    assert normalization.removed_count == 0
    assert expected_path.is_file()
    assert not misnamed_path.exists()


def test_normalize_keeps_the_legacy_ledger_when_a_finding_cannot_be_written(
    tmp_path: Path,
) -> None:
    legacy_path = followup_directory(tmp_path) / "smells.jsonl"
    legacy_path.parent.mkdir(parents=True)
    legacy_text = json.dumps({"rule_id": "r1", "file_path": "a.py", "message": "m1"})
    legacy_path.write_text(legacy_text + "\n", encoding="utf-8")
    blocked_path = finding_path(tmp_path, FollowupFinding("r1", "a.py", "m1", "r1"))
    blocked_path.mkdir()

    normalization = normalize_ledger(tmp_path)

    assert normalization.migrated_count == 0
    assert legacy_path.read_text(encoding="utf-8") == legacy_text + "\n"
