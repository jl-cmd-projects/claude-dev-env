"""Behavior tests for finding the hooks that nested checkouts declare.

Each case builds a session directory with child checkouts on disk and reads
which checkouts and which command hooks the discovery functions return.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from lifecycle.nested_project_hooks_discovery import (
    NestedHook,
    collect_nested_hooks,
    find_nested_projects,
    matcher_selects,
)

DEFAULT_TIMEOUT_SECONDS = 600.0


def _make_checkout(
    session_directory: pathlib.Path,
    checkout_name: str,
    all_hook_groups_by_event: dict[str, list[dict[str, object]]],
) -> pathlib.Path:
    checkout_directory = session_directory / checkout_name
    (checkout_directory / ".git").mkdir(parents=True)
    settings_directory = checkout_directory / ".claude"
    settings_directory.mkdir()
    (settings_directory / "settings.json").write_text(
        json.dumps({"hooks": all_hook_groups_by_event}), encoding="utf-8"
    )
    return checkout_directory


def test_should_find_each_child_checkout_with_settings_in_name_order(
    tmp_path: pathlib.Path,
) -> None:
    beta_directory = _make_checkout(tmp_path, "beta", {})
    alpha_directory = _make_checkout(tmp_path, "alpha", {})
    (tmp_path / "no-git" / ".claude").mkdir(parents=True)
    (tmp_path / "no-git" / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    (tmp_path / "no-settings" / ".git").mkdir(parents=True)
    (tmp_path / "loose-file.txt").write_text("not a checkout", encoding="utf-8")

    assert find_nested_projects(tmp_path) == [alpha_directory, beta_directory]


def test_should_find_no_child_when_the_session_directory_is_a_checkout(
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / ".git").mkdir()
    _make_checkout(tmp_path, "alpha", {})

    assert find_nested_projects(tmp_path) == []


def test_should_find_no_child_when_the_session_directory_has_its_own_settings(
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    _make_checkout(tmp_path, "alpha", {})

    assert find_nested_projects(tmp_path) == []


def test_should_find_no_child_when_the_session_directory_is_missing(
    tmp_path: pathlib.Path,
) -> None:
    assert find_nested_projects(tmp_path / "gone") == []


@pytest.mark.parametrize(
    ("matcher", "match_target", "is_selected"),
    [
        (None, "Bash", True),
        ("", "Bash", True),
        ("*", "Bash", True),
        ("Write|Edit", "Edit", True),
        ("Write|Edit", "Bash", False),
        ("Bas", "Bash", False),
        ("[", "[", True),
        ("[", "Bash", False),
        (7, "Bash", False),
    ],
)
def test_should_select_a_target_only_when_the_matcher_covers_all_of_it(
    matcher: object, match_target: str, is_selected: bool
) -> None:
    assert matcher_selects(matcher, match_target) is is_selected


def test_should_collect_command_hooks_by_checkout_then_declaration_order(
    tmp_path: pathlib.Path,
) -> None:
    alpha_directory = _make_checkout(
        tmp_path,
        "alpha",
        {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "./first.sh"}]},
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "./second.sh", "timeout": 5}],
                },
            ]
        },
    )
    beta_directory = _make_checkout(
        tmp_path,
        "beta",
        {"PreToolUse": [{"hooks": [{"type": "command", "command": "./third.sh"}]}]},
    )

    assert collect_nested_hooks(tmp_path, "PreToolUse", "Bash") == [
        NestedHook(alpha_directory, "./first.sh", DEFAULT_TIMEOUT_SECONDS),
        NestedHook(alpha_directory, "./second.sh", 5.0),
        NestedHook(beta_directory, "./third.sh", DEFAULT_TIMEOUT_SECONDS),
    ]


def test_should_skip_entries_that_are_not_runnable_command_hooks(
    tmp_path: pathlib.Path,
) -> None:
    alpha_directory = _make_checkout(
        tmp_path,
        "alpha",
        {
            "PreToolUse": [
                {"matcher": "Edit", "hooks": [{"type": "command", "command": "./edit-only.sh"}]},
                "not a group",
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "prompt", "prompt": "check the call"},
                        {"type": "command", "command": "   "},
                        {"type": "command", "command": "./zero-timeout.sh", "timeout": 0},
                        "not a hook",
                    ],
                },
            ],
            "SessionStart": [{"hooks": [{"type": "command", "command": "./start.sh"}]}],
        },
    )

    assert collect_nested_hooks(tmp_path, "PreToolUse", "Bash") == [
        NestedHook(alpha_directory, "./zero-timeout.sh", DEFAULT_TIMEOUT_SECONDS),
    ]


@pytest.mark.parametrize("unreadable_settings", ["{not json", "[]", '{"hooks": []}'])
def test_should_collect_nothing_from_settings_that_cannot_be_read(
    tmp_path: pathlib.Path, unreadable_settings: str
) -> None:
    checkout_directory = _make_checkout(tmp_path, "alpha", {})
    (checkout_directory / ".claude" / "settings.json").write_text(
        unreadable_settings, encoding="utf-8"
    )

    assert collect_nested_hooks(tmp_path, "PreToolUse", "Bash") == []
