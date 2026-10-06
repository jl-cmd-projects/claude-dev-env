"""Hook output measurement and the hook budget."""

from __future__ import annotations

import json

from context_budget.hook_measure import (
    hook_findings,
    injected_character_count,
    split_command_environment,
)
from context_budget.model import BudgetPolicy, HookBudget


def test_injected_characters_count_context_and_system_message_or_raw_stdout() -> None:
    json_output = json.dumps(
        {"hookSpecificOutput": {"additionalContext": "abcd"}, "systemMessage": "xy"}
    )

    assert injected_character_count(json_output) == 6
    assert injected_character_count("plain text") == 10
    assert injected_character_count("") == 0


def test_hook_is_held_to_its_limit_or_its_baseline() -> None:
    hook = HookBudget("greeter", ("python3", "g.py"), "{}", 100)
    unlisted_policy = BudgetPolicy(6, ())
    listed_policy = BudgetPolicy(6, (), (hook,), {}, {"greeter": 150})

    assert hook_findings(unlisted_policy, hook, 100) == ()
    assert "injects 101 characters (limit 100)" in hook_findings(unlisted_policy, hook, 101)[0]
    assert hook_findings(listed_policy, hook, 150) == ()
    assert "over its baseline of 150" in hook_findings(listed_policy, hook, 151)[0]


def test_env_prefix_lifts_into_environment_pairs() -> None:
    assert split_command_environment(["env", "A=1", "B=", "python3", "x.py"]) == (
        {"A": "1", "B": ""},
        ("python3", "x.py"),
    )
    assert split_command_environment(["python3", "x.py"]) == ({}, ("python3", "x.py"))
