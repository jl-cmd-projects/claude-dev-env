"""Tests for the shared hook time budget and the budgets that sit under each registered timeout."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import pytest

from hooks_constants import nested_project_hooks_constants
from hooks_constants import turn_review_gate_constants
from hooks_constants.hook_time_budget import call_timeout, remaining_seconds, time_budget

HOOKS_JSON_PATH = Path(__file__).resolve().parent.parent / "hooks.json"
MINIMUM_MARGIN_SECONDS = 5
EXIT_MARGIN_SECONDS = 2


def registered_timeout(event_name: str, script_relative_path: str) -> int:
    all_events = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))["hooks"]
    all_timeouts = [
        each_hook["timeout"]
        for each_group in all_events[event_name]
        for each_hook in each_group["hooks"]
        if each_hook.get("command", "").endswith(f"/hooks/{script_relative_path}")
    ]
    assert len(all_timeouts) == 1, (event_name, script_relative_path, all_timeouts)
    return all_timeouts[0]


def test_should_return_the_cap_outside_a_budget() -> None:
    assert remaining_seconds() == math.inf
    assert call_timeout(10) == 10


def test_should_shrink_the_cap_to_the_time_left_inside_a_budget() -> None:
    with time_budget(0.5):
        assert call_timeout(10) <= 0.5
        assert call_timeout(0.1) == 0.1


def test_should_return_none_once_the_budget_is_spent() -> None:
    with time_budget(0.05):
        time.sleep(0.06)
        assert call_timeout(10) is None


def test_should_keep_an_inner_budget_inside_the_outer_one() -> None:
    with time_budget(0.5), time_budget(100):
        assert remaining_seconds() <= 0.5


def test_should_reset_the_budget_when_the_block_exits() -> None:
    with pytest.raises(RuntimeError), time_budget(0.01):
        raise RuntimeError("leave the block")
    assert remaining_seconds() == math.inf


@pytest.mark.parametrize(
    ("event_name", "script_relative_path", "budget_seconds"),
    [
        (
            "Stop",
            "blocking/turn_review_gate.py",
            turn_review_gate_constants.STOP_RUN_BUDGET_SECONDS,
        ),
        (
            "UserPromptSubmit",
            "blocking/turn_review_gate.py",
            turn_review_gate_constants.PROMPT_RUN_BUDGET_SECONDS,
        ),
    ],
)
def test_should_end_each_budget_before_the_host_timeout(
    event_name: str, script_relative_path: str, budget_seconds: float
) -> None:
    assert budget_seconds + MINIMUM_MARGIN_SECONDS <= registered_timeout(
        event_name, script_relative_path
    )


@pytest.mark.parametrize(
    ("event_name", "budget_seconds"),
    sorted(nested_project_hooks_constants.ALL_RUN_BUDGET_SECONDS_BY_EVENT.items()),
)
def test_should_let_nested_children_run_until_just_before_the_host_timeout(
    event_name: str, budget_seconds: float
) -> None:
    host_timeout = registered_timeout(event_name, "lifecycle/nested_project_hooks.py")
    assert host_timeout - EXIT_MARGIN_SECONDS <= budget_seconds < host_timeout


def test_should_give_the_nested_hooks_a_budget_on_every_event_it_is_registered_on() -> None:
    all_events = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))["hooks"]
    all_registered_events = {
        each_event
        for each_event, all_groups in all_events.items()
        for each_group in all_groups
        for each_hook in each_group["hooks"]
        if each_hook.get("command", "").endswith("/hooks/lifecycle/nested_project_hooks.py")
    }
    assert set(nested_project_hooks_constants.ALL_RUN_BUDGET_SECONDS_BY_EVENT) == all_registered_events
