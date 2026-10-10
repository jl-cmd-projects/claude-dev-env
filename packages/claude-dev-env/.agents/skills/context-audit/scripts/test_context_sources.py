"""Behavior tests for reading checkout files and measuring context rows."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

scripts_directory = str(Path(__file__).resolve().parent)
if scripts_directory not in sys.path:
    sys.path.insert(0, scripts_directory)

from context_audit_constants.config.constants import DepthMode, RowKind, Trigger
from context_sources import (
    RowSource,
    classify_depth,
    count_lines,
    find_import_targets,
    find_relative_links,
    list_tracked_files,
    measure_row,
    parse_frontmatter,
    read_text,
)


def _write(root: Path, relative_path: str, text: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_should_list_tracked_files_without_cache_folders_or_untracked_files(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    _write(tmp_path, "AGENTS.md", "# Root\n")
    _write(tmp_path, "node_modules/pkg/README.md", "vendored\n")
    _write(tmp_path, "notes.md", "untracked\n")
    subprocess.run(
        ["git", "add", "-f", "AGENTS.md", "node_modules/pkg/README.md"],
        cwd=tmp_path,
        check=True,
    )

    assert list_tracked_files(tmp_path) == [tmp_path / "AGENTS.md"]


def test_should_read_text_and_return_empty_for_a_missing_file(tmp_path: Path) -> None:
    present_path = _write(tmp_path, "rule.md", "line one\n")

    assert read_text(present_path) == "line one\n"
    assert read_text(tmp_path / "absent.md") == ""


def test_should_parse_frontmatter_and_join_continuation_lines() -> None:
    text = "---\nname: demo\npaths:\n  - src/**\n---\n# Body\n"

    assert parse_frontmatter(text) == {"name": "demo", "paths": "- src/**"}


def test_should_return_no_frontmatter_when_the_fence_never_closes() -> None:
    assert parse_frontmatter("---\nname: demo\n# Body\n") == {}


def test_should_find_links_inside_the_checkout_only(tmp_path: Path) -> None:
    source = _write(tmp_path, "docs/index.md", "")
    guide = _write(tmp_path, "docs/guide.md", "guide\n")
    text = (
        "[guide](guide.md#setup) [web](https://example.com/page.md)"
        " [missing](absent.md)"
    )

    assert find_relative_links(source, text, tmp_path.resolve()) == [guide.resolve()]


def test_should_find_import_targets_that_exist(tmp_path: Path) -> None:
    source = _write(tmp_path, "CLAUDE.md", "")
    agents = _write(tmp_path, "AGENTS.md", "rules\n")

    all_targets = find_import_targets(
        source, "@AGENTS.md\n@missing.md\n", tmp_path.resolve()
    )

    assert all_targets == [agents.resolve()]


def test_should_classify_each_depth_mode() -> None:
    assert classify_depth(20, 0, 0, 0) == DepthMode.EMPTY
    assert classify_depth(None, 900, 30, 0) == DepthMode.REFERENCE
    assert classify_depth(20, 4000, 64, 2) == DepthMode.CARRIES
    assert classify_depth(20, 2500, 10, 0) == DepthMode.CARRIES
    assert classify_depth(20, 600, 12, 3) == DepthMode.POINTS
    assert classify_depth(20, 600, 12, 0) == DepthMode.LEAN


def test_should_count_an_unterminated_final_line() -> None:
    assert count_lines("") == 0
    assert count_lines("one\ntwo\n") == 2
    assert count_lines("one\ntwo") == 2


def test_should_measure_a_row_from_its_text() -> None:
    source = RowSource(
        "rules/plain.md", RowKind.RULE, "harness", Trigger.SESSION_START, "note"
    )

    row = measure_row(source, "a" * 39 + "\n", 20, 1)

    assert (row.path, row.kind, row.trigger, row.note) == (
        "rules/plain.md",
        RowKind.RULE,
        Trigger.SESSION_START,
        "note",
    )
    assert (row.bytes, row.lines, row.est_tokens, row.links_out) == (40, 1, 10, 1)
    assert (row.depth_mode, row.cap) == (DepthMode.POINTS, 20)
