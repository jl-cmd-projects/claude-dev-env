"""Behavior tests for the committed follow-up ledger duplicate check."""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIRECTORY = Path(__file__).resolve().parent
if str(_TESTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIRECTORY))

from repository_checks.config.constants import (
    CHECK_ID_FOLLOWUP_LEDGER_DUPLICATES,
    FINDINGS_EXIT_CODE,
    SUCCESS_EXIT_CODE,
)
from repository_policy_test_support import (
    commit_tracked_files,
    initialize_repository,
    run_policy,
    write_text,
)

_LEDGER_RELATIVE_PATH = ".claude/followups/smells.jsonl"


def test_should_flag_a_committed_ledger_with_a_repeated_line(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    initialize_repository(repository_root)
    write_text(
        repository_root / _LEDGER_RELATIVE_PATH,
        '{"rule_id": "a"}\n{"rule_id": "b"}\n{"rule_id": "a"}\n',
    )
    commit_tracked_files(repository_root)

    exit_code, stdout_text, _stderr_text = run_policy(repository_root)

    assert exit_code == FINDINGS_EXIT_CODE
    assert (
        f"{CHECK_ID_FOLLOWUP_LEDGER_DUPLICATES}: {_LEDGER_RELATIVE_PATH}:"
        in stdout_text
    )
    assert "cde followup dedupe" in stdout_text


def test_should_pass_a_committed_ledger_without_repeats(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    initialize_repository(repository_root)
    write_text(
        repository_root / _LEDGER_RELATIVE_PATH,
        '{"rule_id": "a"}\n{"rule_id": "b"}\n',
    )
    commit_tracked_files(repository_root)

    exit_code, stdout_text, _stderr_text = run_policy(repository_root)

    assert exit_code == SUCCESS_EXIT_CODE
    assert stdout_text == ""
