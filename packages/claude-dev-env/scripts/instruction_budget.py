"""Check instruction files for the launch byte budget, named people, and link nesting.

A repository opts in with ``instruction-budget.json`` at its root::

    {"max_launch_bytes": 7504, "max_link_hops": 2, "rules_dirs": ["packages/claude-dev-env/rules"]}

The budget counts the bytes an agent loads at launch: each entry instruction
file, its ``@`` imports, and each rule without ``paths:`` frontmatter. The name
and nesting checks run only on the instruction files the caller names.

The CI workflow ``instruction-budget.yml`` runs this on the changed files of a
pull request. The write-time hook ``instruction_file_write_warning.py`` runs it
on each instruction file an agent writes.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

from dev_env_scripts_constants.followup_constants import (
    GATE_FAILED_EXIT_CODE,
    GATE_PASSED_EXIT_CODE,
)
from dev_env_scripts_constants.instruction_budget_constants import (
    FINDING_LINE_TEMPLATE,
    INSTRUCTION_BUDGET_CONFIG_FILE_NAME,
    MISSING_CONFIG_MESSAGE_TEMPLATE,
    PASSED_MESSAGE,
)
from instruction_budget_files import (
    InstructionBudgetConfig,
    InstructionFinding,
    budget_findings,
    instruction_files,
    is_instruction_file,
    load_config,
)
from instruction_budget_links import nesting_findings
from instruction_budget_names import personal_name_findings


def check_repository(
    repository_root: Path,
    config: InstructionBudgetConfig,
    all_changed_files: Iterable[Path],
) -> list[InstructionFinding]:
    """Run the budget check, and the name and nesting checks on changed instruction files.

    Args:
        repository_root: Resolved repository root.
        config: The repository's budget limits.
        all_changed_files: Resolved paths the change touched. Paths that are not
            instruction files, or that are missing, are skipped.

    Returns:
        Every finding, budget first, then names, then nesting.
    """
    all_scoped_files = [
        each_path
        for each_path in all_changed_files
        if each_path.is_file()
        and is_instruction_file(each_path, repository_root, config)
    ]
    return (
        budget_findings(repository_root, config)
        + personal_name_findings(repository_root, all_scoped_files)
        + nesting_findings(repository_root, config, all_scoped_files)
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", default=".")
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="a changed file, relative to the repository root; repeat for each",
    )
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="check every instruction file in the tree, not only the changed ones",
    )
    return parser


def _scoped_files(
    args: argparse.Namespace, repository_root: Path, config: InstructionBudgetConfig
) -> list[Path]:
    if args.all_files:
        return instruction_files(repository_root, config)
    return [(repository_root / each_path).resolve() for each_path in args.changed_file]


def _print_findings(all_findings: Iterable[InstructionFinding]) -> None:
    for each_finding in all_findings:
        print(
            FINDING_LINE_TEMPLATE.format(
                file_path=each_finding.file_path,
                rule_id=each_finding.rule_id,
                message=each_finding.message,
            )
        )


def main(all_argv: Sequence[str]) -> int:
    """Check the repository and print one line per finding.

    Args:
        all_argv: Command-line arguments, without the program name.

    Returns:
        GATE_PASSED_EXIT_CODE when no finding remains, otherwise GATE_FAILED_EXIT_CODE.
    """
    args = _build_parser().parse_args(all_argv)
    repository_root = Path(args.repository_root).resolve()
    config = load_config(repository_root)
    if config is None:
        print(
            MISSING_CONFIG_MESSAGE_TEMPLATE.format(
                config=INSTRUCTION_BUDGET_CONFIG_FILE_NAME
            )
        )
        return GATE_FAILED_EXIT_CODE
    all_findings = check_repository(
        repository_root, config, _scoped_files(args, repository_root, config)
    )
    _print_findings(all_findings)
    if all_findings:
        return GATE_FAILED_EXIT_CODE
    print(PASSED_MESSAGE)
    return GATE_PASSED_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
