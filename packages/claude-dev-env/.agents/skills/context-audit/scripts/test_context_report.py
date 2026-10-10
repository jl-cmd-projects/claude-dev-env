"""Behavior tests for formatting inventory rows as a markdown report."""

from __future__ import annotations

from context_audit_constants.config.constants import DepthMode, RowKind, Trigger
from context_report import (
    format_carries_section,
    format_cleanup_list,
    format_report,
    format_split_section,
    format_stub_section,
    format_trigger_table,
)
from context_sources import ContextRow


def _row(
    path: str,
    kind: RowKind,
    trigger: Trigger,
    depth_mode: DepthMode,
    lines: int,
    est_tokens: int,
) -> ContextRow:
    return ContextRow(
        path=path,
        kind=kind,
        loader="harness",
        trigger=trigger,
        bytes=est_tokens * 4,
        lines=lines,
        est_tokens=est_tokens,
        links_out=0,
        depth_mode=depth_mode,
        cap=20,
        note="",
    )


_ROOT_ROW = _row(
    "AGENTS.md", RowKind.INSTRUCTIONS, Trigger.SESSION_START, DepthMode.CARRIES, 30, 300
)
_RULE_ROW = _row(
    "rules/big.md", RowKind.RULE, Trigger.SESSION_START, DepthMode.CARRIES, 40, 500
)
_STUB_ROW = _row(
    "pkg/CLAUDE.md", RowKind.INSTRUCTIONS, Trigger.FOLDER_ENTER, DepthMode.EMPTY, 0, 0
)
_SKILL_ROW = _row(
    "skills/x/SKILL.md",
    RowKind.SKILL_BODY,
    Trigger.SKILL_INVOKE,
    DepthMode.CARRIES,
    250,
    900,
)
_EMPTY_DOCSTRING_ROW = _row(
    "src/mod.py", RowKind.DOCSTRING, Trigger.FILE_OPEN, DepthMode.EMPTY, 0, 0
)


def test_should_total_each_present_trigger_in_enum_order() -> None:
    all_lines = format_trigger_table([_STUB_ROW, _ROOT_ROW, _RULE_ROW])

    assert all_lines[4:] == [
        "| session-start | 2 | 70 | 800 |",
        "| folder-enter | 1 | 0 | 0 |",
    ]


def test_should_list_carries_rows_or_say_none() -> None:
    assert format_carries_section([])[-1] == "None."
    assert format_carries_section([_RULE_ROW])[-1] == (
        "| rules/big.md | rule | session-start | 40 | 20 | 500 |"
    )


def test_should_list_stub_rows_or_say_none() -> None:
    assert format_stub_section([])[-1] == "None."
    assert format_stub_section([_STUB_ROW])[-1] == "- pkg/CLAUDE.md (instructions)"


def test_should_list_long_skills_or_say_none() -> None:
    assert format_split_section([])[-1] == "None."
    assert format_split_section([_SKILL_ROW])[-1] == (
        "| skills/x/SKILL.md | 250 | 20 | 900 |"
    )


def test_should_sort_cleanup_rows_largest_first_and_route_each_kind() -> None:
    all_lines = format_cleanup_list(
        [_ROOT_ROW, _RULE_ROW, _STUB_ROW, _SKILL_ROW, _EMPTY_DOCSTRING_ROW]
    )

    carries_start = all_lines.index("## Carries depth over cap")
    stubs_start = all_lines.index("## Empty instruction stubs")
    all_carries_rows = all_lines[carries_start + 4 : stubs_start - 1]
    assert all_carries_rows == [
        "| rules/big.md | rule | session-start | 40 | 20 | 500 |",
        "| AGENTS.md | instructions | session-start | 30 | 20 | 300 |",
    ]
    assert "- pkg/CLAUDE.md (instructions)" in all_lines
    assert not any("src/mod.py" in each_line for each_line in all_lines)
    assert "| skills/x/SKILL.md | 250 | 20 | 900 |" in all_lines


def test_should_summarize_session_start_load_in_the_report() -> None:
    report = format_report("demo", [_ROOT_ROW, _RULE_ROW, _STUB_ROW])

    assert report.startswith(
        "# Context audit: demo\n\n"
        "3 loaded files. Startup loads 70 lines, about 800 tokens, from 2 files.\n"
    )
    assert report.endswith(
        "- pkg/CLAUDE.md (instructions)\n\n## Long skills to split\n\nNone.\n"
    )
