"""Behavioral tests for the host-neutral Grok run ledger."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from dev_env_scripts_constants.grok_run_ledger_constants import (  # noqa: E402
    TASK_STATUS_ADVISOR_BLOCKED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_PENDING,
    TASK_STATUS_PENDING_REVIEW,
)
from grok_run_ledger import GrokRunLedger, is_legal_status  # noqa: E402


def test_register_task_persists_atomically(tmp_path: Path) -> None:
    ledger = GrokRunLedger(tmp_path)
    ledger.register_task(task_id="O-04", all_dependencies=())
    reloaded = GrokRunLedger(tmp_path)
    record = reloaded.get_task("O-04")
    assert record.status == TASK_STATUS_PENDING
    assert is_legal_status(record.status)
    payload = json.loads((tmp_path / "grok-run-ledger.json").read_text(encoding="utf-8"))
    assert payload["tasks"][0]["task_id"] == "O-04"


def test_dependencies_block_dispatch(tmp_path: Path) -> None:
    ledger = GrokRunLedger(tmp_path)
    ledger.register_task(task_id="dep", all_dependencies=())
    ledger.register_task(task_id="child", all_dependencies=("dep",))
    assert ledger.can_dispatch("child") is False
    with pytest.raises(ValueError, match="dependencies"):
        ledger.mark_in_progress(
            task_id="child",
            owner_id="w1",
            advisor_session_id="s1",
            base_sha="aaa",
        )
    ledger.mark_in_progress(
        task_id="dep", owner_id="w0", advisor_session_id="s0", base_sha="aaa"
    )
    ledger.mark_completed(
        task_id="dep",
        reviewed_head="bbb",
        all_changed_paths=(),
        advisor_verdict="ENDORSE",
        all_acceptance_mapping={},
        all_test_evidence=["ok"],
    )
    assert ledger.can_dispatch("child") is True


def test_one_live_owner_and_unique_advisor_session(tmp_path: Path) -> None:
    ledger = GrokRunLedger(tmp_path)
    ledger.register_task(task_id="a", all_dependencies=())
    ledger.register_task(task_id="b", all_dependencies=())
    ledger.mark_in_progress(
        task_id="a", owner_id="owner", advisor_session_id="sess-a", base_sha="1"
    )
    with pytest.raises(ValueError, match="owner already live"):
        ledger.mark_in_progress(
            task_id="b", owner_id="owner", advisor_session_id="sess-b", base_sha="1"
        )
    with pytest.raises(ValueError, match="advisor session already bound"):
        ledger.mark_in_progress(
            task_id="b", owner_id="other", advisor_session_id="sess-a", base_sha="1"
        )


def test_snapshot_drift_moves_to_pending_review(tmp_path: Path) -> None:
    ledger = GrokRunLedger(tmp_path)
    ledger.register_task(task_id="t", all_dependencies=())
    ledger.mark_in_progress(
        task_id="t", owner_id="w", advisor_session_id="s", base_sha="base"
    )
    record = ledger.invalidate_on_snapshot_drift(task_id="t", current_sha="drifted")
    assert record.status == TASK_STATUS_PENDING_REVIEW
    assert record.owner_id is None


def test_advisor_blocked_terminal(tmp_path: Path) -> None:
    ledger = GrokRunLedger(tmp_path)
    ledger.register_task(task_id="t", all_dependencies=())
    ledger.mark_in_progress(
        task_id="t", owner_id="w", advisor_session_id="s", base_sha="base"
    )
    record = ledger.mark_advisor_blocked(task_id="t", reason="bind failed")
    assert record.status == TASK_STATUS_ADVISOR_BLOCKED
    assert "bind failed" in record.test_evidence[0]


def test_completed_records_acceptance_and_head(tmp_path: Path) -> None:
    ledger = GrokRunLedger(tmp_path)
    ledger.register_task(task_id="t", all_dependencies=())
    ledger.mark_in_progress(
        task_id="t", owner_id="w", advisor_session_id="s", base_sha="base"
    )
    record = ledger.mark_completed(
        task_id="t",
        reviewed_head="head",
        all_changed_paths=("a.py",),
        advisor_verdict="ENDORSE",
        all_acceptance_mapping={"criterion": "evidence"},
        all_test_evidence=["pytest -q"],
    )
    assert record.status == TASK_STATUS_COMPLETED
    assert record.reviewed_head == "head"
    assert record.changed_paths == ("a.py",)


def test_release_terminated_owner_allows_same_base_reassignment_after_reload(
    tmp_path: Path,
) -> None:
    ledger = GrokRunLedger(tmp_path)
    ledger.register_task(task_id="task", all_dependencies=())
    ledger.mark_in_progress(
        task_id="task",
        owner_id="old-owner",
        advisor_session_id="old-session",
        base_sha="base",
    )

    released_record = ledger.release_terminated_owner(
        task_id="task",
        expected_owner_id="old-owner",
        expected_advisor_session_id="old-session",
    )

    assert released_record.status == TASK_STATUS_PENDING_REVIEW
    assert released_record.owner_id is None
    assert released_record.advisor_session_id == "old-session"
    assert released_record.base_sha == "base"

    reloaded_ledger = GrokRunLedger(tmp_path)
    replacement_record = reloaded_ledger.mark_in_progress(
        task_id="task",
        owner_id="new-owner",
        advisor_session_id="new-session",
        base_sha="base",
    )
    persisted_record = GrokRunLedger(tmp_path).get_task("task")

    assert replacement_record.base_sha == "base"
    assert persisted_record.status == "in_progress"
    assert persisted_record.owner_id == "new-owner"
    assert persisted_record.advisor_session_id == "new-session"
    assert persisted_record.base_sha == "base"


@pytest.mark.parametrize(
    (
        "expected_owner_id",
        "expected_advisor_session_id",
        "persisted_owner_id",
        "persisted_advisor_session_id",
        "should_complete",
    ),
    [
        ("different-owner", "session", "owner", "session", False),
        ("owner", "different-session", "owner", "session", False),
        ("", "session", "", "session", False),
        ("owner", "", "owner", "", False),
        ("owner", "session", "owner", "session", True),
    ],
)
def test_release_terminated_owner_rejects_stale_identity_and_illegal_status(
    tmp_path: Path,
    expected_owner_id: str,
    expected_advisor_session_id: str,
    persisted_owner_id: str,
    persisted_advisor_session_id: str,
    should_complete: bool,
) -> None:
    ledger = GrokRunLedger(tmp_path)
    ledger.register_task(task_id="task", all_dependencies=())
    ledger.mark_in_progress(
        task_id="task",
        owner_id=persisted_owner_id,
        advisor_session_id=persisted_advisor_session_id,
        base_sha="base",
    )
    ledger_path = tmp_path / "grok-run-ledger.json"
    if should_complete:
        ledger.mark_completed(
            task_id="task",
            reviewed_head="head",
            all_changed_paths=(),
            advisor_verdict="ENDORSE",
            all_acceptance_mapping={},
            all_test_evidence=["pytest -q"],
        )

    task_before = ledger.get_task("task")
    task_state_before = (
        task_before.status,
        task_before.owner_id,
        task_before.advisor_session_id,
        task_before.base_sha,
    )
    persisted_bytes_before = ledger_path.read_bytes()

    with pytest.raises(ValueError):
        ledger.release_terminated_owner(
            task_id="task",
            expected_owner_id=expected_owner_id,
            expected_advisor_session_id=expected_advisor_session_id,
        )

    task_after = ledger.get_task("task")
    assert ledger_path.read_bytes() == persisted_bytes_before
    assert (
        task_after.status,
        task_after.owner_id,
        task_after.advisor_session_id,
        task_after.base_sha,
    ) == task_state_before


def test_release_terminated_owner_preserves_dependencies_and_evidence(
    tmp_path: Path,
) -> None:
    ledger = GrokRunLedger(tmp_path)
    ledger.register_task(task_id="dependency", all_dependencies=())
    ledger.mark_in_progress(
        task_id="dependency",
        owner_id="dependency-owner",
        advisor_session_id="dependency-session",
        base_sha="base",
    )
    ledger.mark_completed(
        task_id="dependency",
        reviewed_head="dependency-head",
        all_changed_paths=(),
        advisor_verdict="ENDORSE",
        all_acceptance_mapping={},
        all_test_evidence=["dependency passed"],
    )
    ledger.register_task(task_id="task", all_dependencies=("dependency",))
    ledger.mark_in_progress(
        task_id="task",
        owner_id="owner",
        advisor_session_id="session",
        base_sha="base",
    )
    ledger_path = tmp_path / "grok-run-ledger.json"
    ledger_document = json.loads(ledger_path.read_text(encoding="utf-8"))
    target_task = next(
        each_task
        for each_task in ledger_document["tasks"]
        if each_task["task_id"] == "task"
    )
    target_task["advisor_verdict"] = "ENDORSE"
    target_task["reviewed_head"] = "reviewed-head"
    target_task["changed_paths"] = ["source.py"]
    target_task["acceptance_mapping"] = {"criterion": "evidence"}
    target_task["test_evidence"] = ["pytest -q"]
    ledger_path.write_text(
        json.dumps(ledger_document, indent=2) + "\n",
        encoding="utf-8",
    )

    reloaded_ledger = GrokRunLedger(tmp_path)
    reloaded_ledger.release_terminated_owner(
        task_id="task",
        expected_owner_id="owner",
        expected_advisor_session_id="session",
    )
    persisted_record = GrokRunLedger(tmp_path).get_task("task")

    assert persisted_record.dependencies == ("dependency",)
    assert persisted_record.advisor_session_id == "session"
    assert persisted_record.base_sha == "base"
    assert persisted_record.advisor_verdict == "ENDORSE"
    assert persisted_record.reviewed_head == "reviewed-head"
    assert persisted_record.changed_paths == ("source.py",)
    assert persisted_record.acceptance_mapping == {"criterion": "evidence"}
    assert persisted_record.test_evidence == ["pytest -q"]
    assert reloaded_ledger.can_dispatch("task") is True
