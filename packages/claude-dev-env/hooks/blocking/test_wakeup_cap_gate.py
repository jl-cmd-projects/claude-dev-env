import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import wakeup_cap_gate

SEND_LATER_TOOL = "mcp__claude-code-remote__send_later"
CREATE_TRIGGER_TOOL = "mcp__claude-code-remote__create_trigger"
UPDATE_TRIGGER_TOOL = "mcp__claude-code-remote__update_trigger"


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool_name: str,
    tool_input: dict[str, object],
) -> tuple[int, str, str]:
    hook_input = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = wakeup_cap_gate.main()
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def updated_input_of(stdout_text: str) -> dict[str, object]:
    payload = json.loads(stdout_text)
    hook_output = payload["hookSpecificOutput"]
    assert hook_output["permissionDecision"] == "allow"
    return hook_output["updatedInput"]


def utc_text(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def minutes_from_now(minutes: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


@pytest.mark.parametrize("requested_minutes", [58, 59, 60])
def test_send_later_at_the_cache_edge_is_rewritten_to_the_step_down(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], requested_minutes: int
) -> None:
    tool_input = {"delay_minutes": requested_minutes, "message": "check in", "name": "probe"}
    exit_code, stdout_text, _ = run_gate(monkeypatch, capsys, SEND_LATER_TOOL, tool_input)
    assert exit_code == 0
    assert updated_input_of(stdout_text) == {
        "delay_minutes": 57,
        "message": "check in",
        "name": "probe",
    }


@pytest.mark.parametrize("requested_minutes", [1, 45, 57])
def test_send_later_under_the_step_down_passes_untouched(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], requested_minutes: int
) -> None:
    exit_code, stdout_text, stderr_text = run_gate(
        monkeypatch, capsys, SEND_LATER_TOOL, {"delay_minutes": requested_minutes, "message": "x"}
    )
    assert (exit_code, stdout_text, stderr_text) == (0, "", "")


def test_send_later_over_an_hour_is_refused_with_the_stacking_instruction(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stdout_text, stderr_text = run_gate(
        monkeypatch, capsys, SEND_LATER_TOOL, {"delay_minutes": 90, "message": "x"}
    )
    assert exit_code == 2
    assert stdout_text == ""
    assert "delay_minutes=57" in stderr_text
    assert "delaySeconds=3480" in stderr_text
    assert "stack" in stderr_text


def test_send_later_at_inside_the_cache_edge_is_rewritten(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stdout_text, _ = run_gate(
        monkeypatch,
        capsys,
        SEND_LATER_TOOL,
        {"at": utc_text(minutes_from_now(59.5)), "message": "x"},
    )
    assert exit_code == 0
    rewritten_at = datetime.fromisoformat(
        str(updated_input_of(stdout_text)["at"]).replace("Z", "+00:00")
    )
    assert rewritten_at <= minutes_from_now(57)
    assert rewritten_at >= minutes_from_now(56)


def test_send_later_at_two_hours_out_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _, stderr_text = run_gate(
        monkeypatch,
        capsys,
        SEND_LATER_TOOL,
        {"at": utc_text(minutes_from_now(120)), "message": "x"},
    )
    assert exit_code == 2
    assert "stack" in stderr_text


@pytest.mark.parametrize(("requested_seconds", "allowed_seconds"), [(3500, 3480), (3600, 3480)])
def test_schedule_wakeup_at_the_cache_edge_is_rewritten(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    requested_seconds: int,
    allowed_seconds: int,
) -> None:
    tool_input = {"delaySeconds": requested_seconds, "prompt": "/loop tick", "reason": "r"}
    exit_code, stdout_text, _ = run_gate(monkeypatch, capsys, "ScheduleWakeup", tool_input)
    assert exit_code == 0
    assert updated_input_of(stdout_text)["delaySeconds"] == allowed_seconds
    assert updated_input_of(stdout_text)["prompt"] == "/loop tick"


@pytest.mark.parametrize("requested_seconds", [60, 1800, 3480])
def test_schedule_wakeup_under_the_step_down_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], requested_seconds: int
) -> None:
    exit_code, stdout_text, _ = run_gate(
        monkeypatch, capsys, "ScheduleWakeup", {"delaySeconds": requested_seconds, "prompt": "p"}
    )
    assert (exit_code, stdout_text) == (0, "")


def test_schedule_wakeup_over_an_hour_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _, stderr_text = run_gate(
        monkeypatch, capsys, "ScheduleWakeup", {"delaySeconds": 5400, "prompt": "p"}
    )
    assert exit_code == 2
    assert "delaySeconds=3480" in stderr_text


def test_create_trigger_run_once_at_the_hour_is_rewritten(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tool_input = {
        "name": "n",
        "prompt": "p",
        "initiation": "own_followup",
        "run_once_at": utc_text(minutes_from_now(60)),
    }
    exit_code, stdout_text, _ = run_gate(monkeypatch, capsys, CREATE_TRIGGER_TOOL, tool_input)
    assert exit_code == 0
    rewritten_at = datetime.fromisoformat(
        str(updated_input_of(stdout_text)["run_once_at"]).replace("Z", "+00:00")
    )
    assert rewritten_at <= minutes_from_now(57)


@pytest.mark.parametrize(
    "cron_expression", ["0 * * * *", "0 */4 * * *", "CRON_TZ=America/Los_Angeles 37 8 * * 1-5"]
)
def test_create_trigger_cron_into_a_session_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], cron_expression: str
) -> None:
    tool_input = {
        "name": "n",
        "prompt": "p",
        "initiation": "own_followup",
        "cron_expression": cron_expression,
    }
    exit_code, _, stderr_text = run_gate(monkeypatch, capsys, CREATE_TRIGGER_TOOL, tool_input)
    assert exit_code == 2
    assert cron_expression in stderr_text


def test_create_trigger_with_a_fresh_session_per_firing_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tool_input = {
        "name": "n",
        "prompt": "p",
        "initiation": "human_request",
        "cron_expression": "0 9 * * *",
        "create_new_session_on_fire": True,
    }
    exit_code, stdout_text, _ = run_gate(monkeypatch, capsys, CREATE_TRIGGER_TOOL, tool_input)
    assert (exit_code, stdout_text) == (0, "")


def test_update_trigger_run_once_at_over_an_hour_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tool_input = {"trigger_id": "trig_x", "run_once_at": utc_text(minutes_from_now(90))}
    exit_code, _, _ = run_gate(monkeypatch, capsys, UPDATE_TRIGGER_TOOL, tool_input)
    assert exit_code == 2


def test_update_trigger_cron_change_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tool_input = {"trigger_id": "trig_x", "cron_expression": "0 9 * * *"}
    exit_code, stdout_text, _ = run_gate(monkeypatch, capsys, UPDATE_TRIGGER_TOOL, tool_input)
    assert (exit_code, stdout_text) == (0, "")


@pytest.mark.parametrize("cron_expression", ["*/5 * * * *", "*/30 * * * *", "7,37 * * * *"])
def test_cron_create_firing_more_often_than_the_step_down_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], cron_expression: str
) -> None:
    exit_code, stdout_text, _ = run_gate(
        monkeypatch, capsys, "CronCreate", {"cron": cron_expression, "prompt": "p"}
    )
    assert (exit_code, stdout_text) == (0, "")


@pytest.mark.parametrize("cron_expression", ["7 * * * *", "57 8 * * *", "0,58 * * * *"])
def test_cron_create_with_an_hour_or_more_between_wakes_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], cron_expression: str
) -> None:
    exit_code, _, stderr_text = run_gate(
        monkeypatch, capsys, "CronCreate", {"cron": cron_expression, "prompt": "p"}
    )
    assert exit_code == 2
    assert "stack" in stderr_text


def pinned_local_cron(minutes_ahead: float) -> str:
    fire_time = datetime.now().astimezone() + timedelta(minutes=minutes_ahead)
    return f"{fire_time.minute} {fire_time.hour} {fire_time.day} {fire_time.month} *"


def test_cron_create_one_shot_within_the_step_down_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tool_input = {"cron": pinned_local_cron(30), "prompt": "p", "recurring": False}
    exit_code, stdout_text, _ = run_gate(monkeypatch, capsys, "CronCreate", tool_input)
    assert (exit_code, stdout_text) == (0, "")


def test_cron_create_one_shot_two_hours_out_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tool_input = {"cron": pinned_local_cron(120), "prompt": "p", "recurring": False}
    exit_code, _, _ = run_gate(monkeypatch, capsys, "CronCreate", tool_input)
    assert exit_code == 2


def test_other_tools_pass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stdout_text, _ = run_gate(monkeypatch, capsys, "Bash", {"command": "sleep 4000"})
    assert (exit_code, stdout_text) == (0, "")
