"""Behavior tests for the follow-up command."""

from __future__ import annotations

import io
import json
from pathlib import Path

from dev_env_scripts_constants.followup_constants import (
    BACKLOG_EXCEEDED_EXIT_CODE,
    BACKLOG_EXCEEDED_TEMPLATE,
    BACKLOG_WITHIN_TEMPLATE,
    DEDUPE_RESULT_TEMPLATE,
    FOLLOWUP_BACKLOG_THRESHOLD,
)
from followup_cli import main
from followup_ledger import (
    FollowupFinding,
    all_recorded_findings,
    finding_path,
    followup_directory,
    record_followup_finding,
)


def run_command(all_arguments: list[str]) -> tuple[int, str]:
    output_stream = io.StringIO()
    exit_code = main(all_arguments, stdout=output_stream)
    return exit_code, output_stream.getvalue()


def write_lint_report(
    report_path: Path, all_diagnostics: list[dict[str, object]]
) -> None:
    report_path.write_text(
        json.dumps(
            {"schema_version": 1, "diagnostics": all_diagnostics, "failed_rules": []}
        ),
        encoding="utf-8",
    )


def test_list_reports_nothing_outstanding_for_an_empty_ledger(tmp_path: Path) -> None:
    exit_code, output_text = run_command(["list", "--repository-root", str(tmp_path)])

    assert exit_code == 0
    assert "no follow-ups recorded" in output_text


def test_list_names_each_recorded_finding(tmp_path: Path) -> None:
    record_followup_finding(
        tmp_path, FollowupFinding("instruction-git-mode", "CLAUDE.md", "wrong mode")
    )

    exit_code, output_text = run_command(["list", "--repository-root", str(tmp_path)])

    assert exit_code == 0
    assert "instruction-git-mode" in output_text
    assert "CLAUDE.md" in output_text


def test_ingest_records_every_located_diagnostic(tmp_path: Path) -> None:
    report_path = tmp_path / "lint.json"
    write_lint_report(
        report_path,
        [
            {
                "rule_id": "line-length",
                "severity": "error",
                "message": "line runs past the limit",
                "location": {"path": "src/app.py", "start_line": 4, "start_column": 1},
            }
        ],
    )

    exit_code, _ = run_command(
        ["ingest", str(report_path), "--repository-root", str(tmp_path)]
    )

    assert exit_code == 0
    assert all_recorded_findings(tmp_path) == (
        FollowupFinding(
            "line-length", "src/app.py", "line runs past the limit", "line-length"
        ),
    )


def test_ingest_records_a_diagnostic_without_a_location(tmp_path: Path) -> None:
    report_path = tmp_path / "lint.json"
    write_lint_report(
        report_path,
        [
            {
                "rule_id": "inventory-drift",
                "severity": "error",
                "message": "inventory row missing",
                "location": None,
            }
        ],
    )

    run_command(["ingest", str(report_path), "--repository-root", str(tmp_path)])

    assert all_recorded_findings(tmp_path) == (
        FollowupFinding(
            "inventory-drift", "", "inventory row missing", "inventory-drift"
        ),
    )


def test_ingest_reports_an_unreadable_report(tmp_path: Path) -> None:
    exit_code, output_text = run_command(
        ["ingest", str(tmp_path / "absent.json"), "--repository-root", str(tmp_path)]
    )

    assert exit_code == 2
    assert "absent.json" in output_text


def test_brief_names_every_recorded_finding_and_the_repository(tmp_path: Path) -> None:
    record_followup_finding(
        tmp_path, FollowupFinding("instruction-git-mode", "CLAUDE.md", "wrong mode")
    )

    exit_code, output_text = run_command(["brief", "--repository-root", str(tmp_path)])

    assert exit_code == 0
    assert "instruction-git-mode" in output_text
    assert "wrong mode" in output_text
    assert "open a pull request for it" in output_text
    assert "draft pull request" not in output_text


def test_brief_asks_for_no_work_on_an_empty_ledger(tmp_path: Path) -> None:
    exit_code, output_text = run_command(["brief", "--repository-root", str(tmp_path)])

    assert exit_code == 0
    assert "no follow-ups recorded" in output_text


def test_clear_empties_the_ledger(tmp_path: Path) -> None:
    record_followup_finding(
        tmp_path, FollowupFinding("instruction-git-mode", "CLAUDE.md", "wrong mode")
    )

    exit_code, _ = run_command(["clear", "--repository-root", str(tmp_path)])

    assert exit_code == 0
    assert all_recorded_findings(tmp_path) == ()


def test_clear_on_an_empty_ledger_succeeds(tmp_path: Path) -> None:
    exit_code, _ = run_command(["clear", "--repository-root", str(tmp_path)])

    assert exit_code == 0


def test_an_unknown_command_reports_usage(tmp_path: Path) -> None:
    exit_code, output_text = run_command(
        ["stampede", "--repository-root", str(tmp_path)]
    )

    assert exit_code == 2
    assert "Usage" in output_text


def test_ingest_carries_the_check_identifier_a_diagnostic_names(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "lint.json"
    write_lint_report(
        report_path,
        [
            {
                "rule_id": "code-rules",
                "check_id": "code-rules/constant-outside-config",
                "severity": "error",
                "message": "Line 3: Constant TIMEOUT - move to config/",
                "location": {"path": "scripts/run.py", "start_line": 3},
            }
        ],
    )

    run_command(["ingest", str(report_path), "--repository-root", str(tmp_path)])

    recorded_finding = all_recorded_findings(tmp_path)[0]
    assert recorded_finding.check_id == "code-rules/constant-outside-config"
    assert recorded_finding.severity == "smell"


def test_ingest_records_the_revision_the_repository_has_checked_out(
    tmp_path: Path,
) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("f00dcafe\n", encoding="utf-8")
    report_path = tmp_path / "lint.json"
    write_lint_report(
        report_path,
        [
            {
                "rule_id": "code-rules",
                "check_id": "code-rules/function-length",
                "message": "Line 9: Function 'run' is 74 lines",
                "location": {"path": "scripts/run.py", "start_line": 9},
            }
        ],
    )

    run_command(["ingest", str(report_path), "--repository-root", str(tmp_path)])

    assert all_recorded_findings(tmp_path)[0].origin_commit == "f00dcafe"


def test_count_reports_an_empty_backlog(tmp_path: Path) -> None:
    exit_code, output_text = run_command(["count", "--repository-root", str(tmp_path)])

    assert exit_code == 0
    assert "0" in output_text


def test_count_passes_while_the_backlog_sits_under_the_threshold(
    tmp_path: Path,
) -> None:
    record_followup_finding(
        tmp_path, FollowupFinding("code-rules", "run.py", "one smell", "code-rules/x")
    )

    exit_code, output_text = run_command(["count", "--repository-root", str(tmp_path)])

    assert exit_code == 0
    assert "1" in output_text


def test_count_escalates_once_the_backlog_passes_the_threshold(
    tmp_path: Path,
) -> None:
    for each_index in range(FOLLOWUP_BACKLOG_THRESHOLD + 1):
        record_followup_finding(
            tmp_path,
            FollowupFinding(
                "code-rules",
                f"run{each_index}.py",
                "one smell",
                f"code-rules/x{each_index}",
            ),
        )

    exit_code, output_text = run_command(["count", "--repository-root", str(tmp_path)])

    assert exit_code == BACKLOG_EXCEEDED_EXIT_CODE
    assert str(FOLLOWUP_BACKLOG_THRESHOLD) in output_text


def test_count_writes_the_within_threshold_template_verbatim(
    tmp_path: Path,
) -> None:
    exit_code, output_text = run_command(["count", "--repository-root", str(tmp_path)])

    assert exit_code == 0
    assert output_text == (
        BACKLOG_WITHIN_TEMPLATE.format(
            finding_count=0, threshold=FOLLOWUP_BACKLOG_THRESHOLD
        )
        + "\n"
    )


def test_count_writes_the_exceeded_template_verbatim(tmp_path: Path) -> None:
    for each_index in range(FOLLOWUP_BACKLOG_THRESHOLD + 1):
        record_followup_finding(
            tmp_path,
            FollowupFinding(
                "code-rules",
                f"run{each_index}.py",
                "one smell",
                f"code-rules/x{each_index}",
            ),
        )

    exit_code, output_text = run_command(["count", "--repository-root", str(tmp_path)])

    assert exit_code == BACKLOG_EXCEEDED_EXIT_CODE
    assert output_text == (
        BACKLOG_EXCEEDED_TEMPLATE.format(
            finding_count=FOLLOWUP_BACKLOG_THRESHOLD + 1,
            threshold=FOLLOWUP_BACKLOG_THRESHOLD,
        )
        + "\n"
    )


def test_list_names_the_check_behind_each_finding(tmp_path: Path) -> None:
    record_followup_finding(
        tmp_path,
        FollowupFinding(
            "code-rules",
            "run.py",
            "one smell",
            "code-rules/constant-outside-config",
            "smell",
            "f00dcafe",
        ),
    )

    _, output_text = run_command(["list", "--repository-root", str(tmp_path)])

    assert "code-rules/constant-outside-config" in output_text
    assert "f00dcafe" in output_text


def test_dedupe_moves_a_legacy_ledger_into_one_file_per_finding(
    tmp_path: Path,
) -> None:
    first_line = json.dumps({"rule_id": "r1", "file_path": "a.py", "message": "m1"})
    second_line = json.dumps({"rule_id": "r2", "file_path": "b.py", "message": "m2"})
    legacy_path = followup_directory(tmp_path) / "smells.jsonl"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(
        f"{first_line}\n{second_line}\n{first_line}\n", encoding="utf-8"
    )

    exit_code, output_text = run_command(
        ["dedupe", "--repository-root", str(tmp_path)]
    )

    assert exit_code == 0
    assert output_text == (
        DEDUPE_RESULT_TEMPLATE.format(migrated_count=3, removed_count=0) + "\n"
    )
    assert not legacy_path.exists()
    assert [each.rule_id for each in all_recorded_findings(tmp_path)] == ["r1", "r2"]


def test_dedupe_removes_a_misnamed_copy_of_a_recorded_finding(tmp_path: Path) -> None:
    finding = FollowupFinding("r1", "a.py", "m1", "r1")
    record_followup_finding(tmp_path, finding)
    recorded_path = finding_path(tmp_path, finding)
    copy_path = recorded_path.with_name("copy.json")
    copy_path.write_text(recorded_path.read_text(encoding="utf-8"), encoding="utf-8")

    exit_code, output_text = run_command(
        ["dedupe", "--repository-root", str(tmp_path)]
    )

    assert exit_code == 0
    assert output_text == (
        DEDUPE_RESULT_TEMPLATE.format(migrated_count=0, removed_count=1) + "\n"
    )
    assert not copy_path.exists()
    assert all_recorded_findings(tmp_path) == (finding,)


def test_fix_followups_reads_the_brief_then_clears_every_finding(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "lint.json"
    write_lint_report(
        report_path,
        [
            {
                "rule_id": "code-rules",
                "check_id": "code-rules/constant-outside-config",
                "message": "Constant TIMEOUT",
                "location": {"path": "src/run.py"},
            },
            {
                "rule_id": "test-pairing",
                "message": "no paired test",
                "location": {"path": "src/app.py"},
            },
        ],
    )
    root_arguments = ["--repository-root", str(tmp_path)]

    ingest_exit_code, _ = run_command(["ingest", str(report_path), *root_arguments])
    _, brief_text = run_command(["brief", *root_arguments])
    clear_exit_code, _ = run_command(["clear", *root_arguments])
    _, brief_after_clear = run_command(["brief", *root_arguments])

    assert ingest_exit_code == 0
    assert "- [code-rules/constant-outside-config] src/run.py: Constant TIMEOUT" in (
        brief_text
    )
    assert "- [test-pairing] src/app.py: no paired test" in brief_text
    assert clear_exit_code == 0
    assert brief_after_clear == "no follow-ups recorded\n"
    assert not list(followup_directory(tmp_path).glob("*.json"))
