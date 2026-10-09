"""Clear and normalize the follow-up ledger directory.

``cde followup clear`` and ``cde followup dedupe`` run these. The gates that
record findings use only ``followup_ledger``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

_hooks_directory = str(Path(__file__).resolve().parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

from followup_ledger import (
    all_finding_files,
    all_record_paths,
    finding_from_text,
    finding_path,
    followup_directory,
    record_followup_finding,
)
from hooks_constants.followup_ledger_constants import (
    LEDGER_ENCODING,
    LEGACY_LEDGER_FILE_NAME,
)


def clear_recorded_findings(repository_root: Path) -> None:
    """Remove every recorded finding and any legacy ledger file.

    The directory and its ``.gitignore`` stay. A file that cannot be removed
    is left in place.

    Args:
        repository_root: The repository whose ledger to empty.
    """
    directory = followup_directory(repository_root)
    all_paths = [*all_record_paths(directory), directory / LEGACY_LEDGER_FILE_NAME]
    for each_path in all_paths:
        try:
            each_path.unlink(missing_ok=True)
        except OSError:
            continue


class LedgerNormalization(NamedTuple):
    """What one ``normalize_ledger`` run changed.

    Attributes:
        migrated_count: Legacy ledger lines written as finding files.
        removed_count: Finding files removed as duplicates.
    """

    migrated_count: int
    removed_count: int


def normalize_ledger(repository_root: Path) -> LedgerNormalization:
    """Move every record to the file its tracking key names.

    A legacy ``smells.jsonl`` ledger is split into one file per finding and
    removed. A finding file whose name does not match its tracking key moves
    to the matching name, or is removed when that name already holds the
    finding.

    Args:
        repository_root: The repository whose ledger to normalize.

    Returns:
        How many legacy lines moved and how many duplicate files left.
    """
    migrated_count = _migrate_legacy_ledger(repository_root)
    removed_count = sum(
        _settle_finding_file(each_path, finding_path(repository_root, each_finding))
        for each_path, each_finding in all_finding_files(repository_root)
    )
    return LedgerNormalization(migrated_count, removed_count)


def _settle_finding_file(current_path: Path, expected_path: Path) -> int:
    if current_path == expected_path:
        return 0
    try:
        if expected_path.exists():
            current_path.unlink()
            return 1
        current_path.rename(expected_path)
    except OSError:
        return 0
    return 0


def _migrate_legacy_ledger(repository_root: Path) -> int:
    legacy_path = followup_directory(repository_root) / LEGACY_LEDGER_FILE_NAME
    try:
        legacy_text = legacy_path.read_text(encoding=LEDGER_ENCODING)
    except (OSError, UnicodeError):
        return 0
    all_legacy_findings = [
        each_finding
        for each_finding in map(finding_from_text, legacy_text.splitlines())
        if each_finding is not None
    ]
    for each_finding in all_legacy_findings:
        record_followup_finding(repository_root, each_finding)
    if not all(
        finding_path(repository_root, each_finding).is_file()
        for each_finding in all_legacy_findings
    ):
        return 0
    try:
        legacy_path.unlink()
    except OSError:
        return 0
    return len(all_legacy_findings)
