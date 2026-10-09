"""Classify a path by the kind table and measure its Markdown sections.

::

    ## Plan                    heading starts a section
    Step one.                  detail line
    | a | b |                  table row, not detail
    - [ref](reference/x.md)    pure link item, not detail; relative link is a pointer
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase

from context_budget.model import (
    BaselineEntry,
    BudgetPolicy,
    ContextKind,
    FileMeasure,
    SectionScan,
)
from hooks_constants.context_budget_constants import (
    ALL_NON_RELATIVE_TARGET_PREFIXES,
    ATX_HEADING_PATTERN,
    FENCE_OPEN_PATTERN,
    FRONTMATTER_DELIMITER,
    LINK_TARGET_PATTERN,
    PATH_SEPARATOR,
    PURE_LINK_LIST_ITEM_PATTERN,
    RECURSIVE_GLOB_SEGMENT,
    TABLE_ROW_PREFIX,
    TOP_SECTION_HEADING,
)


def _segments_match(all_pattern_parts: Sequence[str], all_path_parts: Sequence[str]) -> bool:
    if not all_pattern_parts:
        return not all_path_parts
    if all_pattern_parts[0] == RECURSIVE_GLOB_SEGMENT:
        return any(
            _segments_match(all_pattern_parts[1:], all_path_parts[each_start:])
            for each_start in range(len(all_path_parts) + 1)
        )
    if not all_path_parts or not fnmatchcase(all_path_parts[0], all_pattern_parts[0]):
        return False
    return _segments_match(all_pattern_parts[1:], all_path_parts[1:])


def path_matches_pattern(pattern: str, relative_path: str) -> bool:
    """Return whether a repository-relative POSIX path matches one glob.

    ::

        "**/SKILL.md"       "SKILL.md"            -> True
        "rules/*.md"        "rules/deep/a.md"     -> False
        "**/archived/**"    "x/archived/a/b.md"   -> True

    Args:
        pattern: Glob where ``**`` spans zero or more directories.
        relative_path: Repository-relative POSIX path.

    Returns:
        True when the whole path matches.
    """
    return _segments_match(pattern.split(PATH_SEPARATOR), relative_path.split(PATH_SEPARATOR))


def context_kind_for_path(policy: BudgetPolicy, relative_path: str) -> ContextKind | None:
    """Return the measured kind of a path; the first matching kind wins.

    Args:
        policy: Budget policy holding the ordered kind table.
        relative_path: Repository-relative POSIX path.

    Returns:
        The matching kind, or None when no kind matches or the match is skipped.
    """
    for each_kind in policy.all_kinds:
        if any(path_matches_pattern(each, relative_path) for each in each_kind.all_patterns):
            return each_kind if each_kind.line_limit is not None else None
    return None


def _body_lines(text: str) -> list[str]:
    all_lines = text.splitlines()
    if not all_lines or all_lines[0].strip() != FRONTMATTER_DELIMITER:
        return all_lines
    for each_index in range(1, len(all_lines)):
        if all_lines[each_index].strip() == FRONTMATTER_DELIMITER:
            return all_lines[each_index + 1 :]
    return all_lines


def _line_has_pointer(line: str) -> bool:
    return any(
        not each_match.group("target").lower().startswith(ALL_NON_RELATIVE_TARGET_PREFIXES)
        for each_match in LINK_TARGET_PATTERN.finditer(line)
    )


def _is_detail_line(line: str) -> bool:
    if not line.strip() or line.lstrip().startswith(TABLE_ROW_PREFIX):
        return False
    return PURE_LINK_LIST_ITEM_PATTERN.match(line) is None


def _closes_fence(line: str, opening_marker: str) -> bool:
    match = FENCE_OPEN_PATTERN.match(line)
    if match is None or line[match.end() :].strip():
        return False
    marker = match.group("marker")
    return marker[0] == opening_marker[0] and len(marker) >= len(opening_marker)


@dataclass
class _SectionWalk:
    """Mutable state of one pass over a Markdown body."""

    all_scans: list[SectionScan]
    heading: str = TOP_SECTION_HEADING
    detail_line_count: int = 0
    has_pointer: bool = False
    opening_marker: str | None = None

    def close_section(self) -> None:
        self.all_scans.append(SectionScan(self.heading, self.detail_line_count, self.has_pointer))

    def read_fenced(self, line: str) -> None:
        if line.strip():
            self.detail_line_count += 1
        if self.opening_marker is not None and _closes_fence(line, self.opening_marker):
            self.opening_marker = None

    def read_open(self, line: str) -> None:
        fence_match = FENCE_OPEN_PATTERN.match(line)
        heading_match = ATX_HEADING_PATTERN.match(line)
        if fence_match is not None:
            self.opening_marker = fence_match.group("marker")
            self.detail_line_count += 1
        elif heading_match is not None:
            self.close_section()
            self.heading = (heading_match.group("text") or "").strip()
            self.detail_line_count = 0
            self.has_pointer = False
        else:
            self.detail_line_count += int(_is_detail_line(line))
            self.has_pointer = self.has_pointer or _line_has_pointer(line)


def scan_sections(text: str) -> tuple[SectionScan, ...]:
    """Split Markdown into sections and measure each one.

    A heading inside a fenced block is not a heading. Fenced lines count as
    detail and never supply a pointer.

    Args:
        text: Full file text; leading frontmatter is removed.

    Returns:
        One scan per section in document order, starting with ``(top)``.
    """
    walk = _SectionWalk([])
    for each_line in _body_lines(text):
        if walk.opening_marker is not None:
            walk.read_fenced(each_line)
        else:
            walk.read_open(each_line)
    walk.close_section()
    return tuple(walk.all_scans)


def measure_file(policy: BudgetPolicy, relative_path: str, text: str) -> FileMeasure | None:
    """Measure one file against the kind its path selects.

    Args:
        policy: Budget policy.
        relative_path: Repository-relative POSIX path.
        text: File text.

    Returns:
        The measurement, or None when the path is not measured context.
    """
    kind = context_kind_for_path(policy, relative_path)
    if kind is None:
        return None
    all_over_limit_sections: tuple[SectionScan, ...] = ()
    if kind.is_section_rule_on:
        all_over_limit_sections = tuple(
            each_scan
            for each_scan in scan_sections(text)
            if each_scan.detail_line_count > policy.section_detail_line_limit
            and not each_scan.has_pointer
        )
    return FileMeasure(kind, len(text.splitlines()), all_over_limit_sections)


def baseline_entry_for(measure: FileMeasure) -> BaselineEntry | None:
    """Return the baseline entry a measurement needs, or None when within budget.

    Args:
        measure: One file measurement.

    Returns:
        The entry recording the over-limit headings, and the line count only
        when it exceeds the kind's line limit.
    """
    all_headings = tuple(each_scan.heading for each_scan in measure.all_over_limit_sections)
    is_over_line_limit = measure.line_count > (measure.kind.line_limit or 0)
    if not is_over_line_limit and not all_headings:
        return None
    return BaselineEntry(measure.line_count if is_over_line_limit else None, all_headings)
