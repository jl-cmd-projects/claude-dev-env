"""Each context-adding hook in hooks.json stays within the policy's character budget."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from context_budget.hook_measure import hook_findings, injected_character_count, run_hook_command
from context_budget.policy_file import read_policy_file

REPOSITORY_ROOT = HOOKS_DIRECTORY.parents[2]
POLICY = read_policy_file(REPOSITORY_ROOT)
ALL_CONTEXT_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "SubagentStart")
SCRIPT_PATTERN = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/hooks/([^\s\"]+\.py)")
CONTEXT_OUTPUT_PATTERN = re.compile(r"additionalContext|ADDITIONAL_CONTEXT|additional_context")
UNMEASURED_REASON_BY_SCRIPT = {
    "blocking/pre_tool_use_dispatcher.py": "relays its hosted hooks' output",
    "blocking/bash_pre_tool_use_dispatcher.py": "relays its hosted hooks' output",
    "lifecycle/nested_project_hooks.py": "relays a nested project's own hooks",
    "routing/thread_spawn_pace_hook.py": "quotes a usage reading capped by its own constant",
    "session/issue_tracker_session_starter.py": "emits only for a repository the user's "
    "project registry names by absolute path",
}


def _context_adding_scripts() -> set[str]:
    registrations = json.loads((HOOKS_DIRECTORY / "hooks.json").read_text(encoding="utf-8"))
    all_scripts = {
        each_script
        for each_event in ALL_CONTEXT_EVENTS
        for each_group in registrations["hooks"].get(each_event, [])
        for each_hook in each_group["hooks"]
        for each_script in SCRIPT_PATTERN.findall(each_hook["command"])
    }
    return {
        each_script
        for each_script in all_scripts
        if CONTEXT_OUTPUT_PATTERN.search(
            (HOOKS_DIRECTORY / each_script).read_text(encoding="utf-8")
        )
    }


def test_the_repository_carries_a_policy_with_hooks() -> None:
    assert POLICY is not None
    assert POLICY.all_hooks


def test_every_context_adding_hook_is_measured_or_named_unmeasured() -> None:
    assert POLICY is not None
    all_measured_commands = " ".join(
        " ".join(each_hook.all_command_parts) for each_hook in POLICY.all_hooks
    )
    all_unlisted = sorted(
        each_script
        for each_script in _context_adding_scripts() - set(UNMEASURED_REASON_BY_SCRIPT)
        if f"hooks/{each_script}" not in all_measured_commands
    )

    assert all_unlisted == []


@pytest.mark.parametrize(
    "hook", POLICY.all_hooks if POLICY is not None else (), ids=lambda each_hook: each_hook.name
)
def test_hook_injects_text_within_its_budget(hook) -> None:
    assert POLICY is not None
    character_count = injected_character_count(run_hook_command(hook, REPOSITORY_ROOT))

    assert character_count > 0, f"{hook.name} injected nothing on its sample payload"
    assert hook_findings(POLICY, hook, character_count) == ()
