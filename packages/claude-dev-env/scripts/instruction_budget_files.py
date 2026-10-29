"""Find the instruction files a repository loads, and measure their launch budget.

The budget counts the bytes an agent loads at launch: each entry instruction
file, its ``@`` imports, and each rule without ``paths:`` frontmatter.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import NamedTuple

from dev_env_scripts_constants.followup_constants import INSTRUCTION_BUDGET_RULE_ID
from dev_env_scripts_constants.instruction_budget_constants import (
    ALL_ENTRY_INSTRUCTION_FILE_NAMES,
    ALL_INSTRUCTION_FILE_NAMES,
    ALL_SKIPPED_DIRECTORY_NAMES,
    BUDGET_FINDING_MESSAGE_TEMPLATE,
    CLAUDE_FOLDER_NAME,
    DEFAULT_MAX_LINK_HOPS,
    DEFAULT_RULES_DIR_RELATIVE_PATH,
    FENCED_BLOCK_PATTERN,
    FRONTMATTER_DELIMITER,
    IMPORT_LINE_PATTERN,
    INSTRUCTION_BUDGET_CONFIG_FILE_NAME,
    MARKDOWN_SUFFIX,
    MAX_LAUNCH_BYTES_KEY,
    MAX_LINK_HOPS_KEY,
    PATHS_FRONTMATTER_PREFIX,
    RULES_DIRS_KEY,
    TEXT_ENCODING,
)


class InstructionBudgetConfig(NamedTuple):
    """The limits one repository sets in its budget file.

    Attributes:
        max_launch_bytes: Cap on the bytes an agent loads at launch.
        max_link_hops: Most link hops allowed from an entry file to an instruction file.
        rules_dirs: Extra rule folders, relative to the repository root.
    """

    max_launch_bytes: int
    max_link_hops: int
    rules_dirs: tuple[str, ...]


class InstructionFinding(NamedTuple):
    """One instruction-budget finding.

    Attributes:
        rule_id: The check that raised the finding.
        file_path: Repository-relative path the finding names.
        message: The text a reader acts on.
    """

    rule_id: str
    file_path: str
    message: str


def load_config(repository_root: Path) -> InstructionBudgetConfig | None:
    """Read the repository's budget file.

    Args:
        repository_root: Directory that holds the budget file.

    Returns:
        The parsed limits, or None when the repository has no budget file.
    """
    config_path = repository_root / INSTRUCTION_BUDGET_CONFIG_FILE_NAME
    if not config_path.is_file():
        return None
    raw_config = json.loads(config_path.read_text(encoding=TEXT_ENCODING))
    return InstructionBudgetConfig(
        max_launch_bytes=int(raw_config[MAX_LAUNCH_BYTES_KEY]),
        max_link_hops=int(raw_config.get(MAX_LINK_HOPS_KEY, DEFAULT_MAX_LINK_HOPS)),
        rules_dirs=tuple(raw_config.get(RULES_DIRS_KEY, ())),
    )


def read_instruction_text(path: Path) -> str:
    """Read an instruction file as text, replacing bytes that do not decode.

    Args:
        path: File to read.

    Returns:
        The file's text.
    """
    return path.read_text(encoding=TEXT_ENCODING, errors="replace")


def read_text_outside_fences(path: Path) -> str:
    """Read an instruction file as text with its fenced code blocks removed.

    Args:
        path: File to read.

    Returns:
        The file's text, minus every fenced block.
    """
    return FENCED_BLOCK_PATTERN.sub("", read_instruction_text(path))


def _rules_directories(
    repository_root: Path, config: InstructionBudgetConfig
) -> list[Path]:
    all_relative_paths = (DEFAULT_RULES_DIR_RELATIVE_PATH, *config.rules_dirs)
    return [(repository_root / each_path).resolve() for each_path in all_relative_paths]


def _entry_files(repository_root: Path) -> list[Path]:
    all_entry_paths = [
        each_directory / each_name
        for each_directory in (repository_root, repository_root / CLAUDE_FOLDER_NAME)
        for each_name in ALL_ENTRY_INSTRUCTION_FILE_NAMES
    ]
    return [each_path.resolve() for each_path in all_entry_paths if each_path.is_file()]


def _has_paths_frontmatter(text: str) -> bool:
    all_lines = text.splitlines()
    if not all_lines or all_lines[0] != FRONTMATTER_DELIMITER:
        return False
    for each_line in all_lines[1:]:
        if each_line == FRONTMATTER_DELIMITER:
            return False
        if each_line.startswith(PATHS_FRONTMATTER_PREFIX):
            return True
    return False


def _import_closure(start: Path, all_found: dict[Path, None]) -> None:
    if start in all_found or not start.is_file():
        return
    all_found[start] = None
    for each_target in IMPORT_LINE_PATTERN.findall(read_text_outside_fences(start)):
        _import_closure((start.parent / each_target).resolve(), all_found)


def rule_files(repository_root: Path, config: InstructionBudgetConfig) -> list[Path]:
    """List the markdown files under the repository's rule folders.

    Args:
        repository_root: Resolved repository root.
        config: The repository's budget limits, which add its rule folders.

    Returns:
        Each markdown file in an existing rule folder, sorted within each folder.
    """
    all_rule_files: list[Path] = []
    for each_rules_directory in _rules_directories(repository_root, config):
        if each_rules_directory.is_dir():
            all_rule_files.extend(
                sorted(each_rules_directory.rglob(f"*{MARKDOWN_SUFFIX}"))
            )
    return all_rule_files


def launch_files(repository_root: Path, config: InstructionBudgetConfig) -> list[Path]:
    """List the files an agent loads at launch.

    Args:
        repository_root: Resolved repository root.
        config: The repository's budget limits, which add its rule folders.

    Returns:
        Each entry file and its imports, then each unscoped rule, once each.
    """
    all_launch: dict[Path, None] = {}
    for each_entry_file in _entry_files(repository_root):
        _import_closure(each_entry_file, all_launch)
    for each_rule in rule_files(repository_root, config):
        if not _has_paths_frontmatter(read_instruction_text(each_rule)):
            all_launch[each_rule] = None
    return list(all_launch)


def measure_launch_bytes(repository_root: Path, config: InstructionBudgetConfig) -> int:
    """Sum the launch-time bytes of the repository's instruction files.

    Args:
        repository_root: Resolved repository root.
        config: The repository's budget limits.

    Returns:
        The byte total of every file in launch_files.
    """
    return sum(
        each_path.stat().st_size for each_path in launch_files(repository_root, config)
    )


def budget_findings(
    repository_root: Path, config: InstructionBudgetConfig
) -> list[InstructionFinding]:
    """Report a launch total over the repository's cap.

    Args:
        repository_root: Resolved repository root.
        config: The repository's budget limits.

    Returns:
        One finding when the launch total exceeds the cap, else an empty list.
    """
    total_bytes = measure_launch_bytes(repository_root, config)
    if total_bytes <= config.max_launch_bytes:
        return []
    return [
        InstructionFinding(
            rule_id=INSTRUCTION_BUDGET_RULE_ID,
            file_path=INSTRUCTION_BUDGET_CONFIG_FILE_NAME,
            message=BUDGET_FINDING_MESSAGE_TEMPLATE.format(
                total=total_bytes, cap=config.max_launch_bytes
            ),
        )
    ]


def _walk_files(repository_root: Path) -> list[Path]:
    all_files: list[Path] = []
    for each_directory, each_directory_names, each_file_names in os.walk(
        repository_root
    ):
        each_directory_names[:] = [
            each_name
            for each_name in each_directory_names
            if each_name not in ALL_SKIPPED_DIRECTORY_NAMES
        ]
        all_files.extend(
            Path(each_directory) / each_name for each_name in each_file_names
        )
    return all_files


def is_instruction_file(
    path: Path, repository_root: Path, config: InstructionBudgetConfig
) -> bool:
    """Tell whether a file is an instruction file the budget covers.

    Args:
        path: Resolved path of the file.
        repository_root: Resolved repository root.
        config: The repository's budget limits, which add its rule folders.

    Returns:
        True for CLAUDE.md, AGENTS.md, and SKILL.md, and for any markdown file
        under a rule folder. False for every other file.
    """
    if path.name in ALL_INSTRUCTION_FILE_NAMES:
        return True
    if path.suffix != MARKDOWN_SUFFIX:
        return False
    return any(
        each_rules_directory in path.parents
        for each_rules_directory in _rules_directories(repository_root, config)
    )


def instruction_files(
    repository_root: Path, config: InstructionBudgetConfig
) -> list[Path]:
    """List every instruction file in the repository tree.

    Args:
        repository_root: Resolved repository root.
        config: The repository's budget limits.

    Returns:
        The resolved instruction files, in walk order.
    """
    return [
        each_path
        for each_path in _walk_files(repository_root)
        if is_instruction_file(each_path, repository_root, config)
    ]


def root_files(repository_root: Path, config: InstructionBudgetConfig) -> list[Path]:
    """List the files an agent reads without following a link.

    Args:
        repository_root: Resolved repository root.
        config: The repository's budget limits, which add its rule folders.

    Returns:
        Each entry file, then each rule file.
    """
    return _entry_files(repository_root) + rule_files(repository_root, config)
