"""Tests for the PreToolUse dispatcher hosted-hook roster."""

import importlib
import pathlib
import sys

_HOOKS_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOOKS_ROOT))

_BLOCKING_DIR = _HOOKS_ROOT / "blocking"
if str(_BLOCKING_DIR) not in sys.path:
    sys.path.insert(0, str(_BLOCKING_DIR))

from hooks_constants.pre_tool_use_dispatcher_constants import (
    ALL_HOSTED_HOOK_ENTRIES,
    ALL_WRITE_EDIT_MULTI_EDIT_APPLY_PATCH_TOOL_NAMES,
    ALL_WRITE_EDIT_MULTI_EDIT_TOOL_NAMES,
    APPLY_PATCH_TOOL_NAME,
    BLOCKING_CRASH_DENY_REASON,
)
from pre_tool_use_dispatcher import HostedHookResult, aggregate_hosted_hook_results


def test_roster_hosts_no_script() -> None:
    assert ALL_HOSTED_HOOK_ENTRIES == ()


def test_every_hosted_script_path_exists_under_the_hooks_root() -> None:
    for each_entry in ALL_HOSTED_HOOK_ENTRIES:
        hosted_script_path = _HOOKS_ROOT / each_entry.script_relative_path
        assert hosted_script_path.is_file()


def test_retired_native_detector_keeps_its_callable_linter_interface() -> None:
    native_module = importlib.import_module("state_description_blocker")
    assert native_module.find_violations("The API uses port 8080.", "guide.md") == []
    assert native_module.find_violations("Previously set via env var.", "guide.md")
    assert all(each_entry.native_module_name is None for each_entry in ALL_HOSTED_HOOK_ENTRIES)


def test_four_way_set_covers_every_mutation_tool_name() -> None:
    assert ALL_WRITE_EDIT_MULTI_EDIT_APPLY_PATCH_TOOL_NAMES == (
        ALL_WRITE_EDIT_MULTI_EDIT_TOOL_NAMES | {APPLY_PATCH_TOOL_NAME}
    )


def test_blocking_hook_crash_deny_reason_surfaces_the_constant() -> None:
    crash_result = HostedHookResult(
        exit_code=0,
        captured_stdout="",
        did_crash=True,
        is_blocking=True,
    )
    decision = aggregate_hosted_hook_results([crash_result])
    assert decision.should_deny
    assert BLOCKING_CRASH_DENY_REASON in decision.all_deny_reasons
