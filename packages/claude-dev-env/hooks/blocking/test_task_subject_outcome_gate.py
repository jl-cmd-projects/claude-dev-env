import io
import json
from pathlib import Path

import pytest

import task_subject_outcome_gate


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool_name: str,
    tool_input: object,
) -> tuple[int, str]:
    hook_input = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = task_subject_outcome_gate.main()
    return exit_code, capsys.readouterr().err


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


@pytest.mark.parametrize("tool_name", ["TaskCreate", "TaskUpdate"])
@pytest.mark.parametrize(
    "subject",
    [
        "Task names in the list read as outcomes",
        "PR 2347 merged with checks green",
        "PR 12: checks green",
        "Issue 7: closed with the fix linked",
        "Merge PR #2347 once review is clean",
        "Feature flag removed from the settings page",
        "Step notes turn off when the user asks",
        "Phase 2.0 released to all users",
    ],
)
def test_should_allow_a_plain_outcome_subject(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool_name: str,
    subject: str,
) -> None:
    assert run_gate(monkeypatch, capsys, tool_name, {"subject": subject}) == (0, "")


@pytest.mark.parametrize(
    "subject",
    [
        "Feature 1: Investigate the affected subsystem",
        "Feature 3: Write the throughput checkpoint",
        "Feature 6-8: Rebase into small ordered commits, run Opening a PR",
        "Step 3: run the tests",
        "phase 2) migrate callers",
        "Bug fix 4. Reproduce first",
        "Bug  fix 5: Reproduce first",
    ],
)
def test_should_deny_a_subject_that_starts_with_a_procedure_step_label(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], subject: str
) -> None:
    exit_code, stderr_text = run_gate(monkeypatch, capsys, "TaskCreate", {"subject": subject})
    assert exit_code == 2
    assert "procedure step label" in stderr_text
    assert "by its outcome in the user's words" in stderr_text
    assert "private checklist" in stderr_text


def test_should_deny_a_subject_with_a_code_formatted_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, "TaskUpdate", {"taskId": "3", "subject": "Run `how` over the hooks"}
    )
    assert exit_code == 2
    assert "code-formatted name" in stderr_text


def test_should_deny_a_todo_write_item_that_carries_a_marker(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_todos = [
        {"content": "Hook refuses procedure step names", "status": "completed"},
        {"content": "Step 2: push the branch", "status": "pending"},
    ]
    exit_code, stderr_text = run_gate(monkeypatch, capsys, "TodoWrite", {"todos": all_todos})
    assert exit_code == 2
    assert "Step 2: push the branch" in stderr_text


def test_should_allow_todo_write_items_that_read_as_outcomes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    all_todos = [{"content": "Hook refuses procedure step names", "status": "in_progress"}]
    assert run_gate(monkeypatch, capsys, "TodoWrite", {"todos": all_todos}) == (0, "")


@pytest.mark.parametrize(
    ("tool_name", "tool_input"),
    [
        ("TaskUpdate", {"taskId": "3", "status": "completed"}),
        ("TaskCreate", "Step 1: not a dictionary"),
        ("Bash", {"subject": "Step 1: run"}),
        ("TodoWrite", {"todos": "Step 1: run"}),
    ],
)
def test_should_leave_other_tools_and_schemas_alone(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool_name: str,
    tool_input: object,
) -> None:
    assert run_gate(monkeypatch, capsys, tool_name, tool_input) == (0, "")


def test_task_subject_violation_should_return_none_for_an_outcome() -> None:
    assert task_subject_outcome_gate.task_subject_violation("Hook refuses step names") is None


def test_task_subject_violation_should_name_the_backtick_marker() -> None:
    violation = task_subject_outcome_gate.task_subject_violation("Fix `gate.py`")
    assert violation is not None
    assert "code-formatted name" in violation
