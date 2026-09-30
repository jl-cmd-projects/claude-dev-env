"""Tests for orchestrator status_gate (status file + single-pending re-arm)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from status_gate_constants.config.constants import (  # noqa: E402
    ALL_DEFAULT_STATUS_DIRECTORY_PARTS,
    EXIT_CODE_STOP,
    EXIT_CODE_SUCCESS,
    REARM_PENDING_FIELD_NAME,
    REASON_ACTIVE,
    REASON_MISSING_STATUS_FILE,
    REASON_REARM_ALREADY_PENDING,
    REASON_STATUS_NOT_ACTIVE,
    RUN_STATUS_ACTIVE,
    RUN_STATUS_DONE,
    STATUS_FIELD_NAME,
    STATUS_FILE_ENV_VAR,
    STATUS_FILE_NAME,
)


def load_status_gate_module() -> ModuleType:
    module_path = SCRIPTS_DIRECTORY / "status_gate.py"
    spec = importlib.util.spec_from_file_location("status_gate", module_path)
    assert spec is not None
    assert spec.loader is not None
    status_gate_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = status_gate_module
    spec.loader.exec_module(status_gate_module)
    return status_gate_module


class TestWriteAndDecide:
    def should_allow_reschedule_when_status_is_active(
        self, temporary_directory: Path
    ) -> None:
        status_gate = load_status_gate_module()
        status_file_path = temporary_directory / "run-status.json"
        status_gate.write_status_file(
            status_file_path, RUN_STATUS_ACTIVE, "", is_rearm_pending=False
        )
        is_allowed, reason_code = status_gate.decide_should_reschedule(status_file_path)
        assert is_allowed is True
        assert reason_code == REASON_ACTIVE

    def should_stop_when_status_is_done(self, temporary_directory: Path) -> None:
        status_gate = load_status_gate_module()
        status_file_path = temporary_directory / "run-status.json"
        status_gate.write_status_file(
            status_file_path, RUN_STATUS_DONE, "", is_rearm_pending=False
        )
        is_allowed, reason_code = status_gate.decide_should_reschedule(status_file_path)
        assert is_allowed is False
        assert reason_code == REASON_STATUS_NOT_ACTIVE

    def should_fail_closed_when_status_file_missing(
        self, temporary_directory: Path
    ) -> None:
        status_gate = load_status_gate_module()
        status_file_path = temporary_directory / "missing.json"
        is_allowed, reason_code = status_gate.decide_should_reschedule(status_file_path)
        assert is_allowed is False
        assert reason_code == REASON_MISSING_STATUS_FILE

    def should_fail_closed_when_status_file_is_invalid_json(
        self, temporary_directory: Path
    ) -> None:
        status_gate = load_status_gate_module()
        status_file_path = temporary_directory / "bad.json"
        status_file_path.write_text("{not-json", encoding="utf-8")
        is_allowed, reason_code = status_gate.decide_should_reschedule(status_file_path)
        assert is_allowed is False

    def should_deny_reschedule_when_rearm_already_pending(
        self, temporary_directory: Path
    ) -> None:
        status_gate = load_status_gate_module()
        status_file_path = temporary_directory / "run-status.json"
        status_gate.write_status_file(
            status_file_path, RUN_STATUS_ACTIVE, "", is_rearm_pending=True
        )
        is_allowed, reason_code = status_gate.decide_should_reschedule(status_file_path)
        assert is_allowed is False
        assert reason_code == REASON_REARM_ALREADY_PENDING


class TestSetPreservesPending:
    def should_preserve_rearm_pending_when_reasserting_active(
        self, temporary_directory: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        status_gate = load_status_gate_module()
        status_file_path = temporary_directory / "status.json"
        status_gate.write_status_file(
            status_file_path, RUN_STATUS_ACTIVE, "demo", is_rearm_pending=False
        )
        assert status_gate.claim_rearm_slot(status_file_path, "demo")[0] is True
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "status_gate.py",
                "set",
                "--status-file",
                str(status_file_path),
                "--status",
                RUN_STATUS_ACTIVE,
                "--run-slug",
                "demo",
            ],
        )
        assert status_gate.main() == EXIT_CODE_SUCCESS
        payload = json.loads(status_file_path.read_text(encoding="utf-8"))
        assert payload[REARM_PENDING_FIELD_NAME] is True
        is_allowed, reason_code = status_gate.decide_should_reschedule(
            status_file_path
        )
        assert is_allowed is False
        assert reason_code == REASON_REARM_ALREADY_PENDING

    def should_clear_rearm_pending_when_setting_done(
        self, temporary_directory: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        status_gate = load_status_gate_module()
        status_file_path = temporary_directory / "status.json"
        status_gate.write_status_file(
            status_file_path, RUN_STATUS_ACTIVE, "", is_rearm_pending=True
        )
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "status_gate.py",
                "set",
                "--status-file",
                str(status_file_path),
                "--status",
                RUN_STATUS_DONE,
            ],
        )
        assert status_gate.main() == EXIT_CODE_SUCCESS
        payload = json.loads(status_file_path.read_text(encoding="utf-8"))
        assert payload[STATUS_FIELD_NAME] == RUN_STATUS_DONE
        assert payload[REARM_PENDING_FIELD_NAME] is False


class TestBeginClaimRelease:
    def should_claim_rearm_only_once_until_begin_firing(
        self, temporary_directory: Path
    ) -> None:
        status_gate = load_status_gate_module()
        status_file_path = temporary_directory / "run-status.json"
        status_gate.write_status_file(
            status_file_path, RUN_STATUS_ACTIVE, "demo", is_rearm_pending=False
        )
        is_claimed, reason_code, payload = status_gate.claim_rearm_slot(
            status_file_path, "demo"
        )
        assert is_claimed is True
        assert payload is not None
        assert payload[REARM_PENDING_FIELD_NAME] is True

        is_claimed_again, second_reason, _second_payload = status_gate.claim_rearm_slot(
            status_file_path, "demo"
        )
        assert is_claimed_again is False
        assert second_reason == REASON_REARM_ALREADY_PENDING

        is_firing, firing_reason, firing_payload = status_gate.begin_firing(
            status_file_path, "demo"
        )
        assert is_firing is True
        assert firing_payload is not None
        assert firing_payload[REARM_PENDING_FIELD_NAME] is False
        assert firing_reason

        is_claimed_after_firing, _claim_reason, after_payload = (
            status_gate.claim_rearm_slot(status_file_path, "demo")
        )
        assert is_claimed_after_firing is True
        assert after_payload is not None
        assert after_payload[REARM_PENDING_FIELD_NAME] is True

    def should_release_rearm_after_failed_schedule(
        self, temporary_directory: Path
    ) -> None:
        status_gate = load_status_gate_module()
        status_file_path = temporary_directory / "run-status.json"
        status_gate.write_status_file(
            status_file_path, RUN_STATUS_ACTIVE, "", is_rearm_pending=False
        )
        assert status_gate.claim_rearm_slot(status_file_path, "")[0] is True
        is_released, reason_code, payload = status_gate.release_rearm_slot(
            status_file_path, ""
        )
        assert is_released is True
        assert payload is not None
        assert payload[REARM_PENDING_FIELD_NAME] is False
        assert reason_code
        is_allowed, allow_reason = status_gate.decide_should_reschedule(
            status_file_path
        )
        assert is_allowed is True
        assert allow_reason == REASON_ACTIVE


class TestResolveAndCli:
    def should_resolve_explicit_status_file_path(
        self, temporary_directory: Path
    ) -> None:
        status_gate = load_status_gate_module()
        target_path = temporary_directory / "explicit.json"
        resolved_path = status_gate.resolve_status_file_path(
            str(target_path), None, ""
        )
        assert resolved_path == target_path.resolve()

    def should_resolve_default_path_under_base_directory(
        self, temporary_directory: Path
    ) -> None:
        status_gate = load_status_gate_module()
        resolved_path = status_gate.resolve_status_file_path(
            None, temporary_directory, ""
        )
        expected_path = temporary_directory.joinpath(
            *ALL_DEFAULT_STATUS_DIRECTORY_PARTS, STATUS_FILE_NAME
        ).resolve()
        assert resolved_path == expected_path

    def should_scope_default_path_by_run_slug(
        self, temporary_directory: Path
    ) -> None:
        status_gate = load_status_gate_module()
        run_slug = "demo-run"
        resolved_path = status_gate.resolve_status_file_path(
            None, temporary_directory, run_slug
        )
        expected_path = temporary_directory.joinpath(
            *ALL_DEFAULT_STATUS_DIRECTORY_PARTS, run_slug, STATUS_FILE_NAME
        ).resolve()
        assert resolved_path == expected_path

    def should_set_and_gate_via_main(
        self,
        temporary_directory: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        status_gate = load_status_gate_module()
        status_file_path = temporary_directory / "status.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "status_gate.py",
                "set",
                "--status-file",
                str(status_file_path),
                "--status",
                RUN_STATUS_ACTIVE,
                "--run-slug",
                "demo-run",
            ],
        )
        assert status_gate.main() == EXIT_CODE_SUCCESS
        payload = json.loads(status_file_path.read_text(encoding="utf-8"))
        assert payload[STATUS_FIELD_NAME] == RUN_STATUS_ACTIVE
        assert payload[REARM_PENDING_FIELD_NAME] is False

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "status_gate.py",
                "should-reschedule",
                "--status-file",
                str(status_file_path),
            ],
        )
        assert status_gate.main() == EXIT_CODE_SUCCESS

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "status_gate.py",
                "claim-rearm",
                "--status-file",
                str(status_file_path),
            ],
        )
        assert status_gate.main() == EXIT_CODE_SUCCESS
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "status_gate.py",
                "claim-rearm",
                "--status-file",
                str(status_file_path),
            ],
        )
        assert status_gate.main() == EXIT_CODE_STOP
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "status_gate.py",
                "should-reschedule",
                "--status-file",
                str(status_file_path),
            ],
        )
        assert status_gate.main() == EXIT_CODE_STOP

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "status_gate.py",
                "begin-firing",
                "--status-file",
                str(status_file_path),
            ],
        )
        assert status_gate.main() == EXIT_CODE_SUCCESS
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "status_gate.py",
                "should-reschedule",
                "--status-file",
                str(status_file_path),
            ],
        )
        assert status_gate.main() == EXIT_CODE_SUCCESS

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "status_gate.py",
                "set",
                "--status-file",
                str(status_file_path),
                "--status",
                RUN_STATUS_DONE,
            ],
        )
        assert status_gate.main() == EXIT_CODE_SUCCESS
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "status_gate.py",
                "should-reschedule",
                "--status-file",
                str(status_file_path),
            ],
        )
        assert status_gate.main() == EXIT_CODE_STOP

    def should_resolve_status_file_from_environment(
        self, temporary_directory: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        status_gate = load_status_gate_module()
        status_file_path = temporary_directory / "env-status.json"
        monkeypatch.setenv(STATUS_FILE_ENV_VAR, str(status_file_path))
        monkeypatch.setattr(
            sys,
            "argv",
            ["status_gate.py", "set", "--status", RUN_STATUS_ACTIVE],
        )
        assert status_gate.main() == EXIT_CODE_SUCCESS
        assert status_file_path.is_file()
        is_allowed, _reason = status_gate.decide_should_reschedule(status_file_path)
        assert is_allowed is True

    def should_scope_set_and_should_reschedule_with_matching_run_slug(
        self, temporary_directory: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        status_gate = load_status_gate_module()
        monkeypatch.chdir(temporary_directory)
        monkeypatch.delenv(STATUS_FILE_ENV_VAR, raising=False)
        run_slug = "demo-run"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "status_gate.py",
                "set",
                "--status",
                RUN_STATUS_ACTIVE,
                "--run-slug",
                run_slug,
            ],
        )
        assert status_gate.main() == EXIT_CODE_SUCCESS
        slug_path = status_gate.resolve_status_file_path(
            None, temporary_directory, run_slug
        )
        default_path = status_gate.resolve_status_file_path(
            None, temporary_directory, ""
        )
        assert slug_path.is_file()
        assert not default_path.is_file()
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "status_gate.py",
                "should-reschedule",
                "--run-slug",
                run_slug,
            ],
        )
        assert status_gate.main() == EXIT_CODE_SUCCESS
        monkeypatch.setattr(
            sys,
            "argv",
            ["status_gate.py", "should-reschedule"],
        )
        assert status_gate.main() == EXIT_CODE_STOP


@pytest.fixture
def temporary_directory(tmp_path: Path) -> Path:
    return tmp_path


@pytest.mark.parametrize("stored_slug", ["owner-a", ""])
@pytest.mark.parametrize(
    "run_status,is_rearm_pending",
    [("active", False), ("active", True), ("done", False)],
)
@pytest.mark.parametrize(
    "operation",
    [
        "decide_should_reschedule",
        "begin_firing",
        "claim_rearm_slot",
        "release_rearm_slot",
    ],
)
def test_scoped_api_rejects_foreign_or_missing_owner(
    tmp_path: Path,
    stored_slug: str,
    operation: str,
    run_status: str,
    is_rearm_pending: bool,
) -> None:
    status_gate = load_status_gate_module()
    status_path = tmp_path / "status.json"
    status_gate.write_status_file(
        status_path, run_status, stored_slug, is_rearm_pending=is_rearm_pending
    )
    previous_bytes = status_path.read_bytes()
    decision = getattr(status_gate, operation)(status_path, run_slug="caller-b")
    assert decision[:2] == (False, "run_slug_mismatch")
    assert status_path.read_bytes() == previous_bytes


@pytest.mark.parametrize(
    "stored_text",
    ['{"status":"active","run_slug":"owner-a"}', '{"status":"active"}', "{broken"],
)
def test_scoped_write_rejects_unowned_existing_file(
    tmp_path: Path, stored_text: str
) -> None:
    status_gate = load_status_gate_module()
    status_path = tmp_path / "status.json"
    status_path.write_text(stored_text, encoding="utf-8")
    previous_bytes = status_path.read_bytes()
    with pytest.raises(ValueError):
        status_gate.write_status_file(
            status_path, "done", "caller-b", is_rearm_pending=False
        )
    assert status_path.read_bytes() == previous_bytes
    assert sorted(each_path.name for each_path in tmp_path.iterdir()) == ["status.json"]


@pytest.mark.parametrize(
    "command",
    ["set", "should-reschedule", "begin-firing", "claim-rearm", "release-rearm"],
)
@pytest.mark.parametrize("scope_source", ["argument", "environment", "empty_argument"])
def test_scoped_cli_rejects_other_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    scope_source: str,
) -> None:
    status_gate = load_status_gate_module()
    status_path = tmp_path / "status.json"
    status_gate.write_status_file(
        status_path, "active", "owner-a", is_rearm_pending=False
    )
    previous_bytes = status_path.read_bytes()
    all_arguments = ["status_gate.py", command, "--status-file", str(status_path)]
    if command == "set":
        all_arguments.extend(["--status", "done"])
    if scope_source == "argument":
        all_arguments.extend(["--run-slug", "caller-b"])
    if scope_source in ("environment", "empty_argument"):
        monkeypatch.setenv("ORCHESTRATOR_RUN_SLUG", "caller-b")
    if scope_source == "empty_argument":
        all_arguments.extend(["--run-slug", ""])
    monkeypatch.setattr(sys, "argv", all_arguments)
    assert status_gate.main() == EXIT_CODE_STOP
    assert json.loads(capsys.readouterr().out)["reason"] == "run_slug_mismatch"
    assert status_path.read_bytes() == previous_bytes


@pytest.mark.parametrize("run_status", ["active", "done"])
def test_scoped_cli_set_rejects_malformed_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run_status: str,
) -> None:
    status_gate = load_status_gate_module()
    status_path = tmp_path / "status.json"
    status_path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "status_gate.py",
            "set",
            "--status",
            run_status,
            "--status-file",
            str(status_path),
            "--run-slug",
            "scope",
        ],
    )
    assert status_gate.main() == EXIT_CODE_STOP
    assert json.loads(capsys.readouterr().out)["reason"] == "invalid_status_file"
    assert status_path.read_text(encoding="utf-8") == "{broken"


def test_environment_scope_initializes_and_runs_matching_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status_gate = load_status_gate_module()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(STATUS_FILE_ENV_VAR, raising=False)
    monkeypatch.setenv("ORCHESTRATOR_RUN_SLUG", "scope")
    monkeypatch.setattr(sys, "argv", ["status_gate.py", "set", "--status", "active"])
    assert status_gate.main() == EXIT_CODE_SUCCESS
    status_path = status_gate.resolve_status_file_path(None, tmp_path, "scope")
    assert json.loads(status_path.read_text(encoding="utf-8"))["run_slug"] == "scope"
    for each_command in [
        "should-reschedule",
        "claim-rearm",
        "begin-firing",
        "claim-rearm",
        "release-rearm",
    ]:
        monkeypatch.setattr(sys, "argv", ["status_gate.py", each_command])
        assert status_gate.main() == EXIT_CODE_SUCCESS
    assert status_gate.decide_should_reschedule(status_path, run_slug="scope") == (
        True,
        "active",
    )


def test_cli_argument_scope_overrides_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status_gate = load_status_gate_module()
    status_path = tmp_path / "status.json"
    monkeypatch.setenv("ORCHESTRATOR_RUN_SLUG", "environment")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "status_gate.py",
            "set",
            "--status",
            "active",
            "--status-file",
            str(status_path),
            "--run-slug",
            "argument",
        ],
    )
    assert status_gate.main() == EXIT_CODE_SUCCESS
    assert json.loads(status_path.read_text(encoding="utf-8"))["run_slug"] == "argument"
