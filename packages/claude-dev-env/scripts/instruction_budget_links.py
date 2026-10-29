"""Count the link hops an agent follows from an entry file to each instruction file.

A file linked from an entry file is one hop out. A file linked from that file is
two hops out, and so on. A file an entry file imports with ``@`` loads at launch
with its importer, so it sits zero hops further out. The nesting check flags a
scoped file past the cap.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from pathlib import Path

from dev_env_scripts_constants.followup_constants import INSTRUCTION_NESTING_RULE_ID
from dev_env_scripts_constants.instruction_budget_constants import (
    ANCHOR_SEPARATOR,
    EXTERNAL_TARGET_PATTERN,
    IMPORT_HOP_COST,
    LINK_HOP_COST,
    MARKDOWN_LINK_PATTERN,
    MARKDOWN_SUFFIX,
    NESTING_FINDING_MESSAGE_TEMPLATE,
)
from instruction_budget_files import (
    InstructionBudgetConfig,
    InstructionFinding,
    import_targets,
    read_text_outside_fences,
    root_files,
)


def _existing_markdown_files(
    source_path: Path, repository_root: Path, all_raw_targets: Iterable[str]
) -> list[Path]:
    all_resolved = [
        (source_path.parent / each_target).resolve() for each_target in all_raw_targets
    ]
    return [
        each_path
        for each_path in all_resolved
        if each_path.suffix == MARKDOWN_SUFFIX
        and each_path.is_file()
        and repository_root in each_path.parents
    ]


def _targets_with_costs(
    source_path: Path, repository_root: Path
) -> list[tuple[Path, int]]:
    text_outside_fences = read_text_outside_fences(source_path)
    all_link_targets = [
        each_target.split(ANCHOR_SEPARATOR, 1)[0]
        for each_target in MARKDOWN_LINK_PATTERN.findall(text_outside_fences)
        if not EXTERNAL_TARGET_PATTERN.match(each_target)
    ]
    all_linked = _existing_markdown_files(
        source_path, repository_root, all_link_targets
    )
    all_imported = _existing_markdown_files(
        source_path, repository_root, import_targets(text_outside_fences)
    )
    return [(each_path, LINK_HOP_COST) for each_path in all_linked] + [
        (each_path, IMPORT_HOP_COST) for each_path in all_imported
    ]


def _visit_links(
    source_path: Path,
    repository_root: Path,
    all_distances: dict[Path, int],
    all_pending: deque[Path],
) -> None:
    for each_target, each_cost in _targets_with_costs(source_path, repository_root):
        each_distance = all_distances[source_path] + each_cost
        known_distance = all_distances.get(each_target)
        if known_distance is not None and known_distance <= each_distance:
            continue
        all_distances[each_target] = each_distance
        if each_cost == IMPORT_HOP_COST:
            all_pending.appendleft(each_target)
        else:
            all_pending.append(each_target)


def hop_distances(
    repository_root: Path, all_root_files: Iterable[Path]
) -> dict[Path, int]:
    """Count the fewest link hops from any root file to each reachable file.

    A markdown link adds one hop. An ``@`` import adds none.

    Args:
        repository_root: Resolved repository root. Links that leave it are ignored.
        all_root_files: Files an agent reads without following a link.

    Returns:
        Each reachable file mapped to its fewest hops. A root maps to zero.
    """
    all_distances = {each_root: 0 for each_root in all_root_files}
    all_pending = deque(all_distances)
    while all_pending:
        _visit_links(all_pending.popleft(), repository_root, all_distances, all_pending)
    return all_distances


def _nesting_finding(
    repository_root: Path, file_path: Path, hops: int, max_link_hops: int
) -> InstructionFinding:
    return InstructionFinding(
        rule_id=INSTRUCTION_NESTING_RULE_ID,
        file_path=file_path.relative_to(repository_root).as_posix(),
        message=NESTING_FINDING_MESSAGE_TEMPLATE.format(hops=hops, cap=max_link_hops),
    )


def nesting_findings(
    repository_root: Path,
    config: InstructionBudgetConfig,
    all_scoped_files: Iterable[Path],
) -> list[InstructionFinding]:
    """Report a scoped instruction file more link hops out than the cap allows.

    Args:
        repository_root: Resolved repository root.
        config: The repository's budget limits.
        all_scoped_files: Instruction files to check.

    Returns:
        One finding per scoped file that sits beyond max_link_hops.
    """
    all_scoped = list(all_scoped_files)
    if not all_scoped:
        return []
    all_distances = hop_distances(repository_root, root_files(repository_root, config))
    all_findings: list[InstructionFinding] = []
    for each_path in all_scoped:
        hops = all_distances.get(each_path)
        if hops is not None and hops > config.max_link_hops:
            all_findings.append(
                _nesting_finding(repository_root, each_path, hops, config.max_link_hops)
            )
    return all_findings
