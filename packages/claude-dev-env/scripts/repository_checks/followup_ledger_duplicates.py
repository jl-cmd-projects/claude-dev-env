"""Committed follow-up ledger check for exact repeated lines.

GitHub's server-side merge ignores ``merge=union``, so repeated lines arrive
only through a local union merge. This check stops them at the merge queue.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from policy_lint.config import constants as policy_constants

from repository_checks.config import constants as repository_constants
from repository_checks.hook_modules import load_hooks_module
from repository_checks.models import RepositoryFinding


def collect_followup_ledger_duplicate_findings(
    repository_root: Path, all_tracked_paths: Sequence[str]
) -> list[RepositoryFinding]:
    """Return a finding when the tracked ledger repeats a line.

    Args:
        repository_root: Git repository root.
        all_tracked_paths: Repository-relative tracked paths.

    Returns:
        One finding naming the repeated-line count, or no findings.
    """
    ledger = load_hooks_module(repository_constants.FOLLOWUP_LEDGER_MODULE_NAME)
    ledger_path = ledger.followup_ledger_path(repository_root)
    relative_path = ledger_path.relative_to(repository_root).as_posix()
    if relative_path not in all_tracked_paths:
        return []
    repeated_line_count = _repeated_line_count(ledger, ledger_path)
    if not repeated_line_count:
        return []
    return [
        RepositoryFinding(
            repository_constants.CHECK_ID_FOLLOWUP_LEDGER_DUPLICATES,
            relative_path,
            repository_constants.FOLLOWUP_LEDGER_DUPLICATE_MESSAGE_TEMPLATE.format(
                repeated_line_count=repeated_line_count
            ),
        )
    ]


def _repeated_line_count(ledger: ModuleType, ledger_path: Path) -> int:
    all_ledger_lines = ledger_path.read_text(
        encoding=policy_constants.UTF8_ENCODING
    ).splitlines()
    return len(all_ledger_lines) - len(ledger.deduplicated_lines(all_ledger_lines))
