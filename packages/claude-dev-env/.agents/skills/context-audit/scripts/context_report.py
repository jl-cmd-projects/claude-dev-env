"""Format inventory rows as a markdown report with a cleanup list.

::

    # Context audit: my-repo
    412 loaded files. Startup loads 96 lines, about 1830 tokens, from 9 files.
    ## Load by trigger
    ## Carries depth over cap
    ## Empty instruction stubs
    ## Long skills to split
"""

from __future__ import annotations

from context_audit_constants.config import constants
from context_audit_constants.config.constants import DepthMode, RowKind, Trigger
from context_sources import ContextRow


def format_trigger_table(all_rows: list[ContextRow]) -> list[str]:
    """Return the load-by-trigger table lines.

    Args:
        all_rows: Inventory rows.

    Returns:
        Markdown table lines, one row per trigger present.
    """
    all_lines = [
        constants.REPORT_TRIGGER_HEADING,
        "",
        constants.REPORT_TRIGGER_HEADER,
        constants.REPORT_FOUR_COLUMN_RULE,
    ]
    for each_trigger in Trigger:
        all_matching = [
            each_row for each_row in all_rows if each_row.trigger == each_trigger
        ]
        if all_matching:
            all_lines.append(
                constants.REPORT_TRIGGER_ROW_TEMPLATE.format(
                    trigger=each_trigger.value,
                    files=len(all_matching),
                    lines=sum(each_row.lines for each_row in all_matching),
                    tokens=sum(each_row.est_tokens for each_row in all_matching),
                )
            )
    return all_lines


def format_carries_section(all_carries: list[ContextRow]) -> list[str]:
    """Return the section that lists files over their cap.

    Args:
        all_carries: Rows in carries depth mode, skill bodies excluded.

    Returns:
        Markdown lines for the section.
    """
    all_lines = ["", constants.REPORT_CARRIES_HEADING, ""]
    if not all_carries:
        return [*all_lines, constants.REPORT_NONE_LINE]
    all_lines += [constants.REPORT_CARRIES_HEADER, constants.REPORT_SIX_COLUMN_RULE]
    return all_lines + [
        constants.REPORT_CARRIES_ROW_TEMPLATE.format(
            path=each_row.path,
            kind=each_row.kind.value,
            trigger=each_row.trigger.value,
            lines=each_row.lines,
            cap=each_row.cap,
            tokens=each_row.est_tokens,
        )
        for each_row in all_carries
    ]


def format_stub_section(all_stubs: list[ContextRow]) -> list[str]:
    """Return the section that lists empty instruction files.

    Args:
        all_stubs: Empty instruction, import, and rule rows.

    Returns:
        Markdown lines for the section.
    """
    all_lines = ["", constants.REPORT_EMPTY_HEADING, ""]
    all_stub_lines = [
        constants.REPORT_EMPTY_ROW_TEMPLATE.format(
            path=each_row.path, kind=each_row.kind.value
        )
        for each_row in all_stubs
    ]
    return all_lines + (all_stub_lines or [constants.REPORT_NONE_LINE])


def format_split_section(all_long_skills: list[ContextRow]) -> list[str]:
    """Return the section that lists skill bodies over their cap.

    Args:
        all_long_skills: Skill body rows in carries depth mode.

    Returns:
        Markdown lines for the section.
    """
    all_lines = ["", constants.REPORT_SPLIT_HEADING, ""]
    if not all_long_skills:
        return [*all_lines, constants.REPORT_NONE_LINE]
    all_lines += [constants.REPORT_SPLIT_HEADER, constants.REPORT_FOUR_COLUMN_RULE]
    return all_lines + [
        constants.REPORT_SPLIT_ROW_TEMPLATE.format(
            path=each_row.path,
            lines=each_row.lines,
            cap=each_row.cap,
            tokens=each_row.est_tokens,
        )
        for each_row in all_long_skills
    ]


def format_cleanup_list(all_rows: list[ContextRow]) -> list[str]:
    """Return the over-cap, empty-stub, and long-skill sections, largest first.

    Args:
        all_rows: Inventory rows.

    Returns:
        Markdown lines for the three sections.
    """
    all_over_cap = sorted(
        (each_row for each_row in all_rows if each_row.depth_mode == DepthMode.CARRIES),
        key=lambda each_row: each_row.est_tokens,
        reverse=True,
    )
    all_long_skills = [
        each_row for each_row in all_over_cap if each_row.kind == RowKind.SKILL_BODY
    ]
    all_carries = [
        each_row for each_row in all_over_cap if each_row.kind != RowKind.SKILL_BODY
    ]
    all_stubs = [
        each_row
        for each_row in all_rows
        if each_row.depth_mode == DepthMode.EMPTY and each_row.kind in constants.ALL_STUB_KINDS
    ]
    all_carries_lines = format_carries_section(all_carries)
    return all_carries_lines + format_stub_section(all_stubs) + format_split_section(all_long_skills)


def format_report(checkout_name: str, all_rows: list[ContextRow]) -> str:
    """Return the markdown report: summary, load by trigger, and cleanup list.

    Args:
        checkout_name: The name shown in the title.
        all_rows: Inventory rows.

    Returns:
        The report text.
    """
    all_session_start = [
        each_row for each_row in all_rows if each_row.trigger == Trigger.SESSION_START
    ]
    summary = constants.REPORT_SUMMARY_TEMPLATE.format(
        row_count=len(all_rows),
        lines=sum(each_row.lines for each_row in all_session_start),
        tokens=sum(each_row.est_tokens for each_row in all_session_start),
        files=len(all_session_start),
    )
    all_lines = [
        constants.REPORT_TITLE_TEMPLATE.format(name=checkout_name),
        "",
        summary,
        "",
    ]
    all_lines += format_trigger_table(all_rows)
    all_lines += format_cleanup_list(all_rows)
    return constants.LINE_BREAK.join(all_lines) + constants.LINE_BREAK
