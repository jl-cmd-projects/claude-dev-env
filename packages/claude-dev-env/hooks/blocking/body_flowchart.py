"""Find the flowchart in one body section."""

from __future__ import annotations

from collections.abc import Iterator

from hooks_constants.body_flowchart_constants import (
    BACKTICK_FENCE_CHARACTER,
    EDGE_LABEL_PATTERN,
    FENCE_MARKER_GROUP,
    FENCE_OPEN_PATTERN,
    FLOWCHART_EDGE_PATTERN,
    FLOWCHART_FIRST_LINE_PATTERN,
    FRONT_MATTER_DELIMITER,
    INFO_STRING_GROUP,
    INFO_TAIL_GROUP,
    MERMAID_COMMENT_PREFIX,
    MERMAID_INFO_STRING,
    MINIMUM_FENCE_LENGTH,
    NODE_TEXT_PATTERN,
    TRAILING_COMMENT_PATTERN,
)


def _opening_fence(line: str) -> tuple[str, str] | None:
    fence_match = FENCE_OPEN_PATTERN.match(line)
    if fence_match is None:
        return None
    marker = fence_match.group(FENCE_MARKER_GROUP)
    info_text = fence_match.group(INFO_STRING_GROUP) + fence_match.group(INFO_TAIL_GROUP)
    if marker[0] == BACKTICK_FENCE_CHARACTER and BACKTICK_FENCE_CHARACTER in info_text:
        return None
    return marker, fence_match.group(INFO_STRING_GROUP)


def _closes_fence(line: str, open_fence: str) -> bool:
    stripped_line = line.strip()
    return len(stripped_line) >= MINIMUM_FENCE_LENGTH and set(stripped_line) == {open_fence[0]}


def _closing_index(all_lines: list[str], start_index: int, open_fence: str) -> int | None:
    return next(
        (each_index for each_index in range(start_index, len(all_lines)) if _closes_fence(all_lines[each_index], open_fence)),
        None,
    )


def _closed_mermaid_blocks(section: str) -> Iterator[list[str]]:
    all_lines = section.splitlines()
    line_index = 0
    while line_index < len(all_lines):
        opening = _opening_fence(all_lines[line_index])
        if opening is None:
            line_index += 1
            continue
        marker, info_string = opening
        close_index = _closing_index(all_lines, line_index + 1, marker)
        if close_index is None:
            return
        if info_string.lower() == MERMAID_INFO_STRING:
            yield [each_line.strip() for each_line in all_lines[line_index + 1 : close_index]]
        line_index = close_index + 1


def _without_labels(line: str) -> str:
    return EDGE_LABEL_PATTERN.sub("", NODE_TEXT_PATTERN.sub("", TRAILING_COMMENT_PATTERN.sub("", line)))


def _without_front_matter(all_block_lines: list[str]) -> list[str]:
    if not all_block_lines or all_block_lines[0] != FRONT_MATTER_DELIMITER:
        return all_block_lines
    closing_offset = next(
        (each_index for each_index, each_line in enumerate(all_block_lines[1:], start=1) if each_line == FRONT_MATTER_DELIMITER),
        None,
    )
    return [] if closing_offset is None else all_block_lines[closing_offset + 1 :]


def _is_flowchart(all_block_lines: list[str]) -> bool:
    all_diagram_lines = [
        each_line
        for each_line in _without_front_matter(all_block_lines)
        if each_line and not each_line.startswith(MERMAID_COMMENT_PREFIX)
    ]
    if not all_diagram_lines:
        return False
    if FLOWCHART_FIRST_LINE_PATTERN.match(all_diagram_lines[0]) is None:
        return False
    return any(
        FLOWCHART_EDGE_PATTERN.search(_without_labels(each_line)) is not None
        for each_line in all_diagram_lines
    )


def section_has_flowchart(section: str) -> bool:
    """Return whether a section holds a closed mermaid block that draws a flowchart.

    ::

        "```mermaid\\nflowchart LR\\n  a --> b\\n```"   -> True
        "```mermaid\\nflowchart LR; a --> b\\n```"     -> True
        "```mermaid\\nsequenceDiagram\\n  a->>b: hi\\n```" -> False
        "```mermaid\\nflowchart LR\\n  a\\n```"          -> False
        "```mermaid\\nflowchart LR\\n  a --> b"         -> False

    The block opens with a fence whose info string is mermaid. Its first line,
    after any front matter, starts with flowchart, and a line joins two nodes
    with an arrow.

    Args:
        section: The text under one pull request description heading.
    """
    return any(_is_flowchart(each_block) for each_block in _closed_mermaid_blocks(section))
