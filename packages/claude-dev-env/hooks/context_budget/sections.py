"""Classify a path by the kind table and measure its Markdown sections.

::

    ## Plan                    heading starts a section
    Step one.                  detail line
    | a | b |                  table row, not detail
    - [ref](reference/x.md)    pure link item, not detail; relative link is a pointer
    @AGENTS.md                 import line; a pointer for the prose rule only
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase

from context_budget.model import (
    BaselineEntry,
    BudgetPolicy,
    ContextKind,
    FileMeasure,
    ProseScan,
    SectionScan,
)
from hooks_constants.ask_user_question_shape import count_prose_words
from hooks_constants.context_budget_constants import (
    ALL_NON_RELATIVE_TARGET_PREFIXES,
    ATX_HEADING_PATTERN,
    FENCE_OPEN_PATTERN,
    FRONTMATTER_DELIMITER,
    IMPORT_DIRECTIVE_PATTERN,
    LINK_TARGET_PATTERN,
    LIST_MARKER_PATTERN,
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


def _first_matching_kind(policy: BudgetPolicy, relative_path: str) -> ContextKind | None:
    for each_kind in policy.all_kinds:
        if any(path_matches_pattern(each, relative_path) for each in each_kind.all_patterns):
            return each_kind
    return None


def context_kind_for_path(policy: BudgetPolicy, relative_path: str) -> ContextKind | None:
    """Return the measured kind of a path; the first matching kind wins.

    Args:
        policy: Budget policy holding the ordered kind table.
        relative_path: Repository-relative POSIX path.

    Returns:
        The matching kind, or None when no kind matches or the match is skipped.
    """
    kind = _first_matching_kind(policy, relative_path)
    return kind if kind is not None and kind.line_limit is not None else None


def is_path_skipped(policy: BudgetPolicy, relative_path: str) -> bool:
    """Return whether the first kind that matches a path has no line limit.

    Args:
        policy: Budget policy holding the ordered kind table.
        relative_path: Repository-relative POSIX path.

    Returns:
        True when the matching kind is a skipped kind, else False.
    """
    kind = _first_matching_kind(policy, relative_path)
    return kind is not None and kind.line_limit is None


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
    has_detail_line: bool = False
    has_import_line: bool = False
    all_unlinked_detail_lines: list[str] = field(default_factory=list)

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
            self.read_body_line(line)

    def read_body_line(self, line: str) -> None:
        is_detail = _is_detail_line(line)
        has_link = _line_has_pointer(line)
        is_import = IMPORT_DIRECTIVE_PATTERN.match(line) is not None
        self.detail_line_count += int(is_detail)
        self.has_pointer = self.has_pointer or has_link
        self.has_detail_line = self.has_detail_line or is_detail
        self.has_import_line = self.has_import_line or is_import
        if is_detail and not has_link and not is_import:
            self.all_unlinked_detail_lines.append(line)


def scan_sections(text: str) -> tuple[SectionScan, ...]:
    """Split Markdown into sections and measure each one.

    A heading inside a fenced block is not a heading. Fenced lines count as
    detail and never supply a pointer.

    Args:
        text: Full file text; leading frontmatter is removed.

    Returns:
        One scan per section in document order, starting with ``(top)``.
    """
    return tuple(_walk_body(text).all_scans)


def _walk_body(text: str) -> _SectionWalk:
    walk = _SectionWalk([])
    for each_line in _body_lines(text):
        if walk.opening_marker is not None:
            walk.read_fenced(each_line)
        else:
            walk.read_open(each_line)
    walk.close_section()
    return walk


def prose_word_count(line: str) -> int:
    """Count the words of one Markdown line after its list marker.

    Args:
        line: One line of Markdown text.

    Returns:
        The number of words in the line's text.
    """
    return count_prose_words(LIST_MARKER_PATTERN.sub("", line))


def scan_prose(text: str, word_limit: int) -> ProseScan:
    """Measure the prose rule's inputs for one Markdown body.

    Fenced lines, tables, and pure link items are not detail lines. A line
    counts as pointed when it holds a relative link or an @import line.

    Args:
        text: Full file text; leading frontmatter is removed.
        word_limit: Words an unlinked detail line may hold.

    Returns:
        Whether the body has a detail line, whether any line links to a relative
        target or holds an @import line, and the unlinked detail lines over the
        word limit.
    """
    walk = _walk_body(text)
    return ProseScan(
        walk.has_detail_line,
        walk.has_import_line or any(each_scan.has_pointer for each_scan in walk.all_scans),
        tuple(
            each_line
            for each_line in walk.all_unlinked_detail_lines
            if prose_word_count(each_line) > word_limit
        ),
    )


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
