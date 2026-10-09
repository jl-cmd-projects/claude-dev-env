"""Behavior tests for the non-breaking-finding follow-up ledger."""

import json
import subprocess
import sys
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

from followup_ledger import (
    FollowupFinding,
    all_recorded_findings,
    deduplicate_ledger,
    deduplicated_lines,
    followup_ledger_path,
    head_commit,
    record_followup_finding,
)


def test_record_followup_finding_appends_one_readable_record(tmp_path: Path) -> None:
    finding = FollowupFinding(
        rule_id="instruction-filename",
        file_path="docs/Claude.md",
        message="Use the canonical filename: docs/Claude.md",
        check_id="instruction-filename",
    )

    record_followup_finding(tmp_path, finding)

    assert all_recorded_findings(tmp_path) == (finding,)


def test_record_followup_finding_keeps_distinct_findings_apart(tmp_path: Path) -> None:
    first = FollowupFinding(
        "instruction-filename", "docs/Claude.md", "wrong name", "instruction-filename"
    )
    second = FollowupFinding(
        "instruction-mode", "docs/AGENTS.md", "wrong mode", "instruction-mode"
    )

    record_followup_finding(tmp_path, first)
    record_followup_finding(tmp_path, second)

    assert all_recorded_findings(tmp_path) == (first, second)


def test_record_followup_finding_records_a_repeat_once(tmp_path: Path) -> None:
    finding = FollowupFinding(
        "instruction-mode", "docs/AGENTS.md", "wrong mode", "instruction-mode"
    )

    record_followup_finding(tmp_path, finding)
    record_followup_finding(tmp_path, finding)

    assert all_recorded_findings(tmp_path) == (finding,)


def test_all_recorded_findings_is_empty_without_a_ledger(tmp_path: Path) -> None:
    assert all_recorded_findings(tmp_path) == ()


def test_all_recorded_findings_skips_an_unreadable_line(tmp_path: Path) -> None:
    finding = FollowupFinding(
        "instruction-mode", "docs/AGENTS.md", "wrong mode", "instruction-mode"
    )
    record_followup_finding(tmp_path, finding)
    ledger_path = followup_ledger_path(tmp_path)
    with ledger_path.open("a", encoding="utf-8") as ledger_file:
        ledger_file.write("{ not json\n")

    assert all_recorded_findings(tmp_path) == (finding,)


def test_record_followup_finding_writes_one_json_object_per_line(tmp_path: Path) -> None:
    record_followup_finding(
        tmp_path, FollowupFinding("instruction-mode", "docs/AGENTS.md", "wrong mode")
    )

    all_lines = followup_ledger_path(tmp_path).read_text(encoding="utf-8").splitlines()

    assert len(all_lines) == 1
    assert json.loads(all_lines[0])["rule_id"] == "instruction-mode"


def test_a_recorded_ledger_stays_out_of_git_status(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)

    record_followup_finding(
        tmp_path, FollowupFinding("instruction-mode", "docs/AGENTS.md", "wrong mode")
    )

    status_result = subprocess.run(
        ["git", "-C", str(tmp_path), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert followup_ledger_path(tmp_path).is_file()
    assert status_result.stdout == ""


def test_record_followup_finding_swallows_a_write_failure(tmp_path: Path) -> None:
    blocking_file = tmp_path / ".claude"
    blocking_file.write_text("not a directory", encoding="utf-8")

    record_followup_finding(
        tmp_path, FollowupFinding("instruction-mode", "docs/AGENTS.md", "wrong mode")
    )

    assert all_recorded_findings(tmp_path) == ()


def test_a_recorded_finding_carries_its_check_severity_and_origin(
    tmp_path: Path,
) -> None:
    finding = FollowupFinding(
        rule_id="code-rules",
        file_path="scripts/run.py",
        message="Line 3: Constant TIMEOUT - move to config/",
        check_id="code-rules/constant-outside-config",
        severity="smell",
        origin_commit="abc1234",
    )

    record_followup_finding(tmp_path, finding)

    assert all_recorded_findings(tmp_path) == (finding,)


def test_a_record_written_without_the_tracking_fields_still_reads(
    tmp_path: Path,
) -> None:
    ledger_path = followup_ledger_path(tmp_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps(
            {
                "rule_id": "instruction-mode",
                "file_path": "docs/AGENTS.md",
                "message": "wrong mode",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    recorded_finding = all_recorded_findings(tmp_path)[0]

    assert recorded_finding.check_id == "instruction-mode"
    assert recorded_finding.severity == "smell"
    assert recorded_finding.origin_commit == ""


def test_one_smell_seen_under_a_later_commit_stays_one_record(tmp_path: Path) -> None:
    first = FollowupFinding(
        "code-rules", "run.py", "Line 3: x", "code-rules/x", "smell", "aaa1111"
    )
    same_smell_later = first._replace(origin_commit="bbb2222")

    record_followup_finding(tmp_path, first)
    record_followup_finding(tmp_path, same_smell_later)

    assert all_recorded_findings(tmp_path) == (first,)


def test_head_commit_reads_the_checked_out_revision(tmp_path: Path) -> None:
    git_directory = tmp_path / ".git"
    (git_directory / "refs" / "heads").mkdir(parents=True)
    (git_directory / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git_directory / "refs" / "heads" / "main").write_text(
        "0123456789abcdef0123456789abcdef01234567\n", encoding="utf-8"
    )

    assert head_commit(tmp_path) == "0123456789abcdef0123456789abcdef01234567"


def test_head_commit_reads_a_detached_revision(tmp_path: Path) -> None:
    git_directory = tmp_path / ".git"
    git_directory.mkdir()
    (git_directory / "HEAD").write_text(
        "0123456789abcdef0123456789abcdef01234567\n", encoding="utf-8"
    )

    assert head_commit(tmp_path) == "0123456789abcdef0123456789abcdef01234567"


def test_head_commit_is_empty_outside_a_repository(tmp_path: Path) -> None:
    assert head_commit(tmp_path) == ""


def test_deduplicated_lines_keeps_the_first_of_each_exact_line_in_order() -> None:
    assert deduplicated_lines(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]


def test_record_followup_finding_removes_lines_a_union_merge_repeated(
    tmp_path: Path,
) -> None:
    ledger_path = followup_ledger_path(tmp_path)
    ledger_path.parent.mkdir(parents=True)
    first_line = '{"rule_id": "r1", "file_path": "a.py", "message": "m1"}'
    second_line = '{"rule_id": "r2", "file_path": "b.py", "message": "m2"}'
    ledger_path.write_text(
        f"{first_line}\n{second_line}\n{first_line}\n", encoding="utf-8"
    )

    record_followup_finding(tmp_path, FollowupFinding("r3", "c.py", "m3", "r3"))

    all_ledger_lines = ledger_path.read_text(encoding="utf-8").splitlines()
    assert all_ledger_lines[:2] == [first_line, second_line]
    assert [json.loads(each_line)["rule_id"] for each_line in all_ledger_lines] == [
        "r1",
        "r2",
        "r3",
    ]


def test_record_followup_finding_removes_a_repeat_of_an_already_recorded_finding(
    tmp_path: Path,
) -> None:
    finding = FollowupFinding("r1", "a.py", "m1", "r1")
    record_followup_finding(tmp_path, finding)
    ledger_path = followup_ledger_path(tmp_path)
    recorded_text = ledger_path.read_text(encoding="utf-8")
    ledger_path.write_text(recorded_text * 2, encoding="utf-8")

    record_followup_finding(tmp_path, finding)

    assert ledger_path.read_text(encoding="utf-8") == recorded_text


def test_deduplicate_ledger_reports_how_many_lines_it_removed(tmp_path: Path) -> None:
    ledger_path = followup_ledger_path(tmp_path)
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text("x\ny\nx\nx\n", encoding="utf-8")

    removed_count = deduplicate_ledger(tmp_path)

    assert removed_count == 2
    assert ledger_path.read_text(encoding="utf-8") == "x\ny\n"


def test_deduplicate_ledger_leaves_an_absent_ledger_absent(tmp_path: Path) -> None:
    assert deduplicate_ledger(tmp_path) == 0
    assert not followup_ledger_path(tmp_path).exists()
