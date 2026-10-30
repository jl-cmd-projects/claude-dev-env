"""Check instruction files for the launch byte budget, named people, and link nesting.

A repository opts in with ``instruction-budget.json`` at its root::

    {"max_launch_bytes": 7504, "max_link_hops": 2, "rules_dirs": ["packages/claude-dev-env/rules"]}

The budget counts the bytes an agent loads at launch: each entry instruction
file, its ``@`` imports, and each rule without ``paths:`` frontmatter. The name
check runs on the instruction files the caller names, and on every launch file once
the change touches an instruction file, since a new import loads an unchanged doc. The nesting check covers
every instruction file on every run, since one edited, deleted, or added link
moves the files behind it, and so does a new cap in the budget file.

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
    INSTRUCTION_BUDGET_RULE_ID,
    INSTRUCTION_NESTING_RULE_ID,
)
from dev_env_scripts_constants.instruction_budget_constants import (
    FINDING_LINE_TEMPLATE,
    INSTRUCTION_BUDGET_CONFIG_FILE_NAME,
    MALFORMED_CONFIG_MESSAGE_TEMPLATE,
    MISSING_CONFIG_MESSAGE_TEMPLATE,
    PASSED_MESSAGE,
)
from instruction_budget_files import (
    InstructionBudgetConfig,
    InstructionBudgetConfigError,
    InstructionFinding,
    budget_findings,
    instruction_files,
    is_existing_file,
    is_instruction_file,
    launch_files,
    load_config,
)
from instruction_budget_links import nesting_findings
from instruction_budget_names import personal_name_findings


def scoped_instruction_files(
    repository_root: Path,
    config: InstructionBudgetConfig,
    all_changed_files: Iterable[Path],
) -> list[Path]:
    """Keep the changed files whose text an agent loads as instructions.

    Args:
        repository_root: Resolved repository root.
        config: The repository's budget limits.
        all_changed_files: Resolved paths the change touched.

    Returns:
        Each existing changed file that is an instruction file, or that a
        launch file imports.
    """
    all_launch = set(launch_files(repository_root, config))
    return [
        each_path
        for each_path in all_changed_files
        if is_existing_file(each_path)
        and (
            is_instruction_file(each_path, repository_root, config)
            or each_path in all_launch
        )
    ]


def with_launch_files(
    repository_root: Path,
    config: InstructionBudgetConfig,
    all_changed_files: list[Path],
) -> list[Path]:
    """Add the launch files to the changed files once a change touches an instruction file.

    A new import loads an unchanged doc at launch, so the name check reads it too.

    Args:
        repository_root: Resolved repository root.
        config: The repository's budget limits.
        all_changed_files: Resolved paths the change touched.

    Returns:
        The changed files, then each launch file, once each. The changed files
        alone when none is an instruction file.
    """
    if not scoped_instruction_files(repository_root, config, all_changed_files):
        return all_changed_files
    return list(
        dict.fromkeys(all_changed_files + launch_files(repository_root, config))
    )


def check_repository(
    repository_root: Path,
    config: InstructionBudgetConfig,
    all_changed_files: Iterable[Path],
) -> list[InstructionFinding]:
    """Run the budget and nesting checks on the whole tree, and the name check on changed files.

    Args:
        repository_root: Resolved repository root.
        config: The repository's budget limits.
        all_changed_files: Resolved paths the change touched. Paths that are
            missing, or that an agent does not load as instructions, skip the
            name check.

    Returns:
        Every finding, budget first, then names, then nesting.
    """
    all_scoped_files = scoped_instruction_files(
        repository_root, config, all_changed_files
    )
    return (
        budget_findings(repository_root, config)
        + personal_name_findings(repository_root, all_scoped_files)
        + nesting_findings(
            repository_root, config, instruction_files(repository_root, config)
        )
    )


def _files_over_cap_without(
    repository_root: Path, config: InstructionBudgetConfig, excluded_file: Path
) -> set[str]:
    all_files = instruction_files(repository_root, config)
    return {
        each_finding.file_path
        for each_finding in nesting_findings(
            repository_root, config, all_files, excluded_file
        )
    }


def findings_caused_by(
    repository_root: Path, config: InstructionBudgetConfig, written_path: Path
) -> list[InstructionFinding]:
    """Run the checks for one written file, and keep only the nesting it causes.

    A nesting finding stays when it disappears once the written file is treated
    as absent. A write of the budget file keeps every finding.

    Args:
        repository_root: Resolved repository root.
        config: The repository's budget limits.
        written_path: Resolved path of the file the agent wrote.

    Returns:
        The budget and name findings, then each nesting finding the file causes.
    """
    all_changed = with_launch_files(repository_root, config, [written_path])
    all_findings = check_repository(repository_root, config, all_changed)
    if written_path.name == INSTRUCTION_BUDGET_CONFIG_FILE_NAME:
        return all_findings
    all_files_without = _files_over_cap_without(repository_root, config, written_path)
    return [
        each_finding
        for each_finding in all_findings
        if each_finding.rule_id != INSTRUCTION_NESTING_RULE_ID
        or each_finding.file_path not in all_files_without
    ]


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
        return list(
            dict.fromkeys(
                instruction_files(repository_root, config)
                + launch_files(repository_root, config)
            )
        )
    return with_launch_files(
        repository_root,
        config,
        [(repository_root / each_path).resolve() for each_path in args.changed_file],
    )


def finding_line(finding: InstructionFinding) -> str:
    """Format a finding as the one line the command line and the hook print.

    Args:
        finding: The finding to print.

    Returns:
        The file path, the rule ID in brackets, and the message.
    """
    return FINDING_LINE_TEMPLATE.format(
        file_path=finding.file_path,
        rule_id=finding.rule_id,
        message=finding.message,
    )


def _report_findings(all_findings: list[InstructionFinding]) -> int:
    for each_finding in all_findings:
        print(finding_line(each_finding))
    if all_findings:
        return GATE_FAILED_EXIT_CODE
    print(PASSED_MESSAGE)
    return GATE_PASSED_EXIT_CODE


def _malformed_config_line(error: InstructionBudgetConfigError) -> str:
    return finding_line(
        InstructionFinding(
            rule_id=INSTRUCTION_BUDGET_RULE_ID,
            file_path=INSTRUCTION_BUDGET_CONFIG_FILE_NAME,
            message=MALFORMED_CONFIG_MESSAGE_TEMPLATE.format(error=error),
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
    try:
        config = load_config(repository_root)
    except InstructionBudgetConfigError as error:
        print(_malformed_config_line(error))
        return GATE_FAILED_EXIT_CODE
    if config is None:
        print(
            MISSING_CONFIG_MESSAGE_TEMPLATE.format(
                config=INSTRUCTION_BUDGET_CONFIG_FILE_NAME
            )
        )
        return GATE_FAILED_EXIT_CODE
    return _report_findings(
        check_repository(
            repository_root, config, _scoped_files(args, repository_root, config)
        )
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
