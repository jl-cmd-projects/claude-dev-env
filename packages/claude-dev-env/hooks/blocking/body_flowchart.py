"""Find the flowchart in one body section."""

from __future__ import annotations

from collections.abc import Iterator

from hooks_constants.body_flowchart_constants import (
    EDGE_LABEL_PATTERN,
    FENCE_MAX_INDENT,
    FENCE_OPEN_PATTERN,
    FLOWCHART_EDGE_PATTERN,
    FLOWCHART_FIRST_LINE_PATTERN,
    FENCE_MARKER_GROUP,
    INFO_STRING_GROUP,
    MERMAID_COMMENT_PREFIX,
    MERMAID_INFO_STRING,
    NODE_TEXT_PATTERN,
)


def _closes_fence(line: str, open_fence: str) -> bool:
    stripped_line = line.strip()
    indent = len(line) - len(line.lstrip())
    return (
        indent <= FENCE_MAX_INDENT
        and len(stripped_line) >= len(open_fence)
        and set(stripped_line) == {open_fence[0]}
    )


def _closing_index(all_lines: list[str], start_index: int, open_fence: str) -> int | None:
    return next(
        (each_index for each_index in range(start_index, len(all_lines)) if _closes_fence(all_lines[each_index], open_fence)),
        None,
    )


def _closed_mermaid_blocks(section: str) -> Iterator[list[str]]:
    all_lines = section.splitlines()
    line_index = 0
    while line_index < len(all_lines):
        fence_match = FENCE_OPEN_PATTERN.match(all_lines[line_index])
        if fence_match is None:
            line_index += 1
            continue
        close_index = _closing_index(all_lines, line_index + 1, fence_match.group(FENCE_MARKER_GROUP))
        if close_index is None:
            return
        if fence_match.group(INFO_STRING_GROUP).lower() == MERMAID_INFO_STRING:
            yield [each_line.strip() for each_line in all_lines[line_index + 1 : close_index]]
        line_index = close_index + 1


def _without_labels(line: str) -> str:
    return EDGE_LABEL_PATTERN.sub("", NODE_TEXT_PATTERN.sub("", line))


def _is_flowchart(all_block_lines: list[str]) -> bool:
    all_diagram_lines = [
        each_line
        for each_line in all_block_lines
        if each_line and not each_line.startswith(MERMAID_COMMENT_PREFIX)
    ]
    if not all_diagram_lines:
        return False
    first_line, *all_later_lines = all_diagram_lines
    if FLOWCHART_FIRST_LINE_PATTERN.match(first_line) is None:
        return False
    return any(
        FLOWCHART_EDGE_PATTERN.search(_without_labels(each_line)) is not None
        for each_line in all_later_lines
    )


def section_has_flowchart(section: str) -> bool:
    """Return whether a section holds a closed mermaid block that draws a flowchart.

    ::

        "```mermaid\\nflowchart LR\\n  a --> b\\n```"   -> True
        "```mermaid\\nsequenceDiagram\\n  a->>b: hi\\n```" -> False
        "```mermaid\\nflowchart LR\\n  a\\n```"          -> False
        "```mermaid\\nflowchart LR\\n  a --> b"         -> False

    The block opens with a fence whose info string is mermaid. Its first line
    starts with flowchart, and a later line joins two nodes with an arrow.

    Args:
        section: The text under one pull request description heading.
    """
    return any(_is_flowchart(each_block) for each_block in _closed_mermaid_blocks(section))
