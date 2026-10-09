"""Read checkout files and measure them as context rows.

A row records one loaded file: its size, its links out, and its depth mode.
The helpers here read text, parse frontmatter, and follow links and imports.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from context_audit_constants.config import constants
from context_audit_constants.config.constants import DepthMode, RowKind, Trigger


@dataclass(frozen=True)
class ContextRow:
    """One file an agent loads, with its size and how it loads."""

    path: str
    kind: RowKind
    loader: str
    trigger: Trigger
    bytes: int
    lines: int
    est_tokens: int
    links_out: int
    depth_mode: DepthMode
    cap: int | None
    note: str


@dataclass(frozen=True)
class RowSource:
    """Where a row's file sits and how the agent reaches it."""

    path: str
    kind: RowKind
    loader: str
    trigger: Trigger
    note: str


def list_tracked_files(root: Path) -> list[Path]:
    """Return the tracked files under *root*, minus caches and vendored folders.

    Args:
        root: A git checkout.

    Returns:
        Absolute paths of tracked files that exist on disk.
    """
    listing = subprocess.run(
        constants.ALL_GIT_LIST_FILES_ARGUMENTS,
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout
    all_paths = [
        root / os.fsdecode(each_entry)
        for each_entry in listing.split(constants.GIT_LIST_FILES_SEPARATOR)
        if each_entry
    ]
    return [
        each_path
        for each_path in all_paths
        if not constants.ALL_SKIPPED_PATH_PARTS.intersection(each_path.parts)
        and each_path.is_file()
    ]


def read_text(path: Path) -> str:
    """Return the file text, or an empty string when it cannot be read.

    Args:
        path: The file to read.

    Returns:
        The decoded text.
    """
    try:
        return path.read_text(
            encoding=constants.TEXT_ENCODING, errors=constants.TEXT_DECODE_ERRORS
        )
    except OSError:
        return ""


def parse_frontmatter(text: str) -> dict[str, str]:
    """Return the frontmatter fields of a markdown file as flat strings.

    ::

        ---
        name: demo
        paths:
          - src/**
        ---
        -> {"name": "demo", "paths": "- src/**"}

    Args:
        text: The file text.

    Returns:
        Field text by field name; empty when the file has no frontmatter.
    """
    fence_length = len(constants.FRONTMATTER_FENCE)
    closing_index = text.find(constants.FRONTMATTER_CLOSING_FENCE, fence_length)
    if not text.startswith(constants.FRONTMATTER_FENCE) or closing_index == -1:
        return {}
    field_by_name: dict[str, str] = {}
    current_name = ""
    for each_line in text[fence_length:closing_index].splitlines():
        current_name = _merge_frontmatter_line(field_by_name, current_name, each_line)
    return field_by_name


def _merge_frontmatter_line(
    field_by_name: dict[str, str], current_name: str, line: str
) -> str:
    field_match = re.match(constants.FRONTMATTER_FIELD_PATTERN, line)
    if field_match:
        field_by_name[field_match.group(1)] = field_match.group(2).strip()
        return field_match.group(1)
    if current_name and line.startswith(
        constants.ALL_FRONTMATTER_CONTINUATION_PREFIXES
    ):
        field_by_name[current_name] = (
            f"{field_by_name[current_name]} {line.strip()}".strip()
        )
    return current_name


def find_relative_links(source: Path, text: str, root: Path) -> list[Path]:
    """Return the files inside *root* that markdown links in *text* point to.

    Args:
        source: The file the text came from.
        text: Markdown text.
        root: The checkout root.

    Returns:
        Resolved link targets that exist inside the checkout.
    """
    all_targets = [
        each_target
        for each_target in re.findall(constants.LINK_PATTERN, text)
        if not re.match(constants.URL_SCHEME_PATTERN, each_target)
    ]
    return _existing_inside(source, all_targets, root)


def find_import_targets(source: Path, text: str, root: Path) -> list[Path]:
    """Return the files inside *root* that ``@path`` import lines name.

    Args:
        source: The instruction file the text came from.
        text: The instruction text.
        root: The checkout root.

    Returns:
        Resolved import targets that exist inside the checkout.
    """
    return _existing_inside(source, re.findall(constants.IMPORT_PATTERN, text), root)


def _existing_inside(source: Path, all_targets: list[str], root: Path) -> list[Path]:
    all_candidates = [
        (source.parent / each_target).resolve() for each_target in all_targets
    ]
    return [
        each_candidate
        for each_candidate in all_candidates
        if each_candidate.is_file() and root in each_candidate.parents
    ]


def classify_depth(
    cap: int | None, byte_count: int, line_count: int, link_count: int
) -> DepthMode:
    """Return how much depth a file carries against its cap.

    ::

        classify_depth(20, 0, 0, 0)       -> empty
        classify_depth(None, 900, 30, 0)  -> reference
        classify_depth(20, 4000, 64, 2)   -> carries
        classify_depth(20, 600, 12, 3)    -> points

    Args:
        cap: The line cap, or None for on-link depth.
        byte_count: File size in bytes.
        line_count: File length in lines.
        link_count: Relative links out of the file.

    Returns:
        The depth mode; a file over cap lines, or over cap times 120 bytes, carries.
    """
    if byte_count <= constants.EMPTY_FILE_BYTE_LIMIT:
        return DepthMode.EMPTY
    if cap is None:
        return DepthMode.REFERENCE
    if line_count > cap or byte_count > cap * constants.CHARACTERS_PER_CAPPED_LINE:
        return DepthMode.CARRIES
    return DepthMode.POINTS if link_count else DepthMode.LEAN


def count_lines(text: str) -> int:
    """Return the line count of *text*, counting a final unterminated line.

    Args:
        text: Any text.

    Returns:
        The number of lines.
    """
    has_unterminated_tail = bool(text) and not text.endswith(constants.LINE_BREAK)
    return text.count(constants.LINE_BREAK) + int(has_unterminated_tail)


def measure_row(
    source: RowSource, text: str, cap: int | None, link_count: int
) -> ContextRow:
    """Return the row for *text* loaded from *source*.

    Args:
        source: Where the file sits and how it loads.
        text: The text the agent receives.
        cap: The line cap, or None for on-link depth.
        link_count: Relative links out of the text.

    Returns:
        The measured row.
    """
    byte_count = len(text.encode(constants.TEXT_ENCODING))
    line_count = count_lines(text)
    return ContextRow(
        path=source.path,
        kind=source.kind,
        loader=source.loader,
        trigger=source.trigger,
        bytes=byte_count,
        lines=line_count,
        est_tokens=round(byte_count / constants.BYTES_PER_ESTIMATED_TOKEN),
        links_out=link_count,
        depth_mode=classify_depth(cap, byte_count, line_count, link_count),
        cap=cap,
        note=source.note,
    )
