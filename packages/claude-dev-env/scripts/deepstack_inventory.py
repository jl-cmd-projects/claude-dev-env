#!/usr/bin/env python3
"""Diff the DeepStack retirement manifest against the active tree.

Each row names a retired path, the behavior it required, the trigger that
replaces it, and the requirement that stays. The eval row keeps a
reproducible check. An instruction or a manifest cell that marks evals
optional, or that drops that check, is a finding.

This script reads the manifest and the active files. It does not rewrite them.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from active_capability_references import unresolved_active_capabilities
from dev_env_scripts_constants.deepstack_inventory_constants import (
    ALL_EVAL_OPTIONAL_MARKERS,
    ALL_TRUST_CARD_LINES,
    DEEPSTACK_SECTION_HEADING,
    DEEPSTACK_SKILL_RELATIVE_PATH,
    EVAL_GUIDE_PATH_SUFFIX,
    FINDING_BEHAVIOR_STILL_ACTIVE,
    FINDING_DROPS_FIRST_ACTION_NOTE,
    FINDING_DROPS_REPRODUCIBLE_CHECK,
    FINDING_DROPS_TRUST_LINE,
    FINDING_MARKS_EVALS_OPTIONAL,
    FINDING_TRIGGER_MISSING,
    FIRST_ACTION_BEHAVIOR_PREFIX,
    FIRST_ACTION_RETIRED_SENTENCE,
    MANIFEST_RELATIVE_PATH,
    PATH_NONE,
    REPRODUCIBLE_CHECK_SENTENCE,
    RETIRED_PATH_HEADER,
    UTF8_ENCODING,
)


@dataclass(frozen=True)
class ReplacementRow:
    """One retired behavior and the trigger that replaces it."""

    retired_path: str
    behavior: str
    trigger: str
    requirement_that_stays: str


@dataclass(frozen=True)
class InventoryFinding:
    """One place the active tree still carries a retired behavior."""

    retired_path: str
    code: str
    detail: str


def _unquote(cell: str) -> str:
    text = cell.strip()
    if len(text) >= 2 and text.startswith("`") and text.endswith("`"):
        return text[1:-1]
    return text


def _table_cells(line: str) -> tuple[str, ...] | None:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    cells = [_unquote(each_cell) for each_cell in stripped.strip("|").split("|")]
    if len(cells) != 4:
        return None
    if cells[0].startswith("-") or cells[0].lower() == RETIRED_PATH_HEADER:
        return None
    return tuple(cells)


def replacement_rows(manifest_text: str) -> tuple[ReplacementRow, ...]:
    """Return the rows under the DeepStack heading, or none when it is absent."""
    all_lines = manifest_text.splitlines()
    in_section = False
    all_rows: list[ReplacementRow] = []
    for each_line in all_lines:
        if each_line.startswith(DEEPSTACK_SECTION_HEADING):
            in_section = True
            continue
        if in_section and each_line.startswith("## "):
            break
        if not in_section:
            continue
        cells = _table_cells(each_line)
        if cells is None:
            continue
        all_rows.append(
            ReplacementRow(
                retired_path=cells[0],
                behavior=cells[1],
                trigger=cells[2],
                requirement_that_stays=cells[3],
            )
        )
    return tuple(all_rows)


def _is_eval_retirement(row: ReplacementRow) -> bool:
    return row.retired_path.endswith(EVAL_GUIDE_PATH_SUFFIX) or row.behavior.startswith(
        FIRST_ACTION_BEHAVIOR_PREFIX
    )


def reproducible_check_findings(
    instruction_text: str, requirement_text: str, retired_path: str
) -> tuple[InventoryFinding, ...]:
    """Reject an eval retirement that makes the reproducible check optional.

    Args:
        instruction_text: The active instruction the row points at.
        requirement_text: The manifest cell for the requirement that stays.
        retired_path: Path named by the row, used on each finding.

    Returns:
        Findings for an optional eval or a dropped reproducible check.
    """
    all_findings: list[InventoryFinding] = []
    for each_text, each_surface in (
        (instruction_text, "instruction"),
        (requirement_text, "manifest"),
    ):
        lowered = each_text.lower()
        if any(each_marker in lowered for each_marker in ALL_EVAL_OPTIONAL_MARKERS):
            all_findings.append(
                InventoryFinding(
                    retired_path=retired_path,
                    code=FINDING_MARKS_EVALS_OPTIONAL,
                    detail=each_surface,
                )
            )
        if REPRODUCIBLE_CHECK_SENTENCE not in each_text:
            all_findings.append(
                InventoryFinding(
                    retired_path=retired_path,
                    code=FINDING_DROPS_REPRODUCIBLE_CHECK,
                    detail=each_surface,
                )
            )
        for each_trust_line in ALL_TRUST_CARD_LINES:
            if each_trust_line not in each_text:
                all_findings.append(
                    InventoryFinding(
                        retired_path=retired_path,
                        code=FINDING_DROPS_TRUST_LINE,
                        detail=f"{each_surface}:{each_trust_line}",
                    )
                )
    if FIRST_ACTION_RETIRED_SENTENCE not in requirement_text:
        all_findings.append(
            InventoryFinding(
                retired_path=retired_path,
                code=FINDING_DROPS_FIRST_ACTION_NOTE,
                detail="manifest",
            )
        )
    return tuple(all_findings)


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding=UTF8_ENCODING)


def findings_for_rows(
    package_root: Path,
    all_rows: tuple[ReplacementRow, ...],
    skill_text: str,
) -> tuple[InventoryFinding, ...]:
    """Return findings for retired behaviors that the active tree still requires."""
    all_findings: list[InventoryFinding] = []
    for each_row in all_rows:
        if each_row.trigger not in skill_text:
            all_findings.append(
                InventoryFinding(
                    retired_path=each_row.retired_path,
                    code=FINDING_TRIGGER_MISSING,
                    detail=each_row.trigger,
                )
            )
        if each_row.retired_path != PATH_NONE:
            instruction_text = _read_text(package_root / each_row.retired_path)
            if each_row.behavior and each_row.behavior in instruction_text:
                all_findings.append(
                    InventoryFinding(
                        retired_path=each_row.retired_path,
                        code=FINDING_BEHAVIOR_STILL_ACTIVE,
                        detail=each_row.behavior,
                    )
                )
        else:
            instruction_text = ""
        if _is_eval_retirement(each_row):
            all_findings.extend(
                reproducible_check_findings(
                    instruction_text,
                    each_row.requirement_that_stays,
                    each_row.retired_path,
                )
            )
    return tuple(all_findings)


def inventory_findings(package_root: Path) -> tuple[InventoryFinding, ...]:
    """Return DeepStack findings plus leftover retired capability names."""
    manifest_text = _read_text(package_root / MANIFEST_RELATIVE_PATH)
    all_rows = replacement_rows(manifest_text)
    skill_text = _read_text(package_root / DEEPSTACK_SKILL_RELATIVE_PATH)
    all_findings = list(findings_for_rows(package_root, all_rows, skill_text))
    for each_reference in unresolved_active_capabilities(package_root):
        all_findings.append(
            InventoryFinding(
                retired_path=each_reference.file_path,
                code="retired-capability",
                detail=each_reference.capability_name,
            )
        )
    return tuple(all_findings)


def _format_finding(finding: InventoryFinding) -> str:
    return f"{finding.retired_path}: {finding.code}: {finding.detail}"


def main(all_arguments: list[str]) -> int:
    """Print each finding and return 1 when the active tree fails the manifest."""
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--package-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
    )
    arguments = parser.parse_args(all_arguments)
    all_findings = inventory_findings(arguments.package_root)
    for each_finding in all_findings:
        sys.stdout.write(_format_finding(each_finding) + "\n")
    return 1 if all_findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
