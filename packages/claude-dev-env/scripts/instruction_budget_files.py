"""Find the instruction files a repository loads, and measure their launch budget.

The budget counts the bytes an agent loads at launch: each entry file, its
``@`` imports to four hops deep, and each rule without ``paths:`` frontmatter.
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
    IMPORT_PATTERN,
    INLINE_CODE_SPAN_PATTERN,
    INSTRUCTION_BUDGET_CONFIG_FILE_NAME,
    INSTRUCTION_TEXT_ENCODING,
    MARKDOWN_SUFFIX,
    MAX_IMPORT_HOPS,
    MAX_LAUNCH_BYTES_KEY,
    MAX_LINK_HOPS_KEY,
    PATHS_FRONTMATTER_PREFIX,
    RULES_DIRS_KEY,
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


class InstructionBudgetConfigError(ValueError):
    """The repository's budget file exists but does not hold valid limits."""


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


def _whole_number(raw_number: object, key: str) -> int:
    if (
        isinstance(raw_number, bool)
        or not isinstance(raw_number, int)
        or raw_number < 0
    ):
        raise ValueError(f"{key} must be a whole number, zero or more")
    return raw_number


def _is_folder_inside_repository(raw_folder: object) -> bool:
    if not isinstance(raw_folder, str):
        return False
    folder_path = Path(raw_folder)
    return (
        bool(folder_path.parts)
        and not folder_path.is_absolute()
        and ".." not in folder_path.parts
    )


def _parse_rules_dirs(raw_rules_dirs: object) -> tuple[str, ...]:
    if not isinstance(raw_rules_dirs, list) or not all(
        _is_folder_inside_repository(each_folder) for each_folder in raw_rules_dirs
    ):
        raise ValueError(
            f"{RULES_DIRS_KEY} must be a list of folders inside the repository"
        )
    return tuple(raw_rules_dirs)


def _budget_config_from(raw_config: dict) -> InstructionBudgetConfig:
    return InstructionBudgetConfig(
        max_launch_bytes=_whole_number(
            raw_config[MAX_LAUNCH_BYTES_KEY], MAX_LAUNCH_BYTES_KEY
        ),
        max_link_hops=_whole_number(
            raw_config.get(MAX_LINK_HOPS_KEY, DEFAULT_MAX_LINK_HOPS),
            MAX_LINK_HOPS_KEY,
        ),
        rules_dirs=_parse_rules_dirs(raw_config.get(RULES_DIRS_KEY, [])),
    )


def load_config(repository_root: Path) -> InstructionBudgetConfig | None:
    """Read the repository's budget file.

    Args:
        repository_root: Directory that holds the budget file.

    Returns:
        The parsed limits, or None when the repository has no budget file.

    Raises:
        InstructionBudgetConfigError: When the budget file is not valid JSON or lacks valid limits.
    """
    config_path = repository_root / INSTRUCTION_BUDGET_CONFIG_FILE_NAME
    if not config_path.is_file():
        return None
    try:
        raw_config = json.loads(
            config_path.read_text(encoding=INSTRUCTION_TEXT_ENCODING)
        )
        return _budget_config_from(raw_config)
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as error:
        raise InstructionBudgetConfigError(str(error)) from error


def read_instruction_text(path: Path) -> str:
    """Read an instruction file as text, replacing bytes that do not decode.

    Args:
        path: File to read.

    Returns:
        The file's text.
    """
    return path.read_text(encoding=INSTRUCTION_TEXT_ENCODING, errors="replace")


def read_text_outside_fences(path: Path) -> str:
    """Read an instruction file as text with its fenced code blocks removed.

    Args:
        path: File to read.

    Returns:
        The file's text, minus every fenced block.
    """
    return FENCED_BLOCK_PATTERN.sub("", read_instruction_text(path))


def import_targets(text_outside_fences: str) -> list[str]:
    """List the ``@`` import paths that sit outside code spans and fenced blocks.

    Args:
        text_outside_fences: Instruction text with its fenced blocks removed.

    Returns:
        Each import path, in order of appearance. An import may sit anywhere in
        a line, after whitespace.
    """
    text_outside_code = INLINE_CODE_SPAN_PATTERN.sub("", text_outside_fences)
    return IMPORT_PATTERN.findall(text_outside_code)


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
    if not all_lines or all_lines[0].rstrip() != FRONTMATTER_DELIMITER:
        return False
    for each_line in all_lines[1:]:
        if each_line.rstrip() == FRONTMATTER_DELIMITER:
            return False
        if each_line.startswith(PATHS_FRONTMATTER_PREFIX):
            return True
    return False


def is_existing_file(path: Path) -> bool:
    """Tell whether a path names an existing file.

    Args:
        path: Path to test.

    Returns:
        True for an existing file. False for any other path or rejected name.
    """
    try:
        return path.is_file()
    except OSError:
        return False


def _imported_paths(source_path: Path) -> list[Path]:
    return [
        (source_path.parent / each_target).resolve()
        for each_target in import_targets(read_text_outside_fences(source_path))
    ]


def _unseen_imports(all_sources: list[Path], all_found: dict[Path, None]) -> list[Path]:
    all_candidates = [
        each_path
        for each_source in all_sources
        for each_path in _imported_paths(each_source)
    ]
    all_unseen: list[Path] = []
    for each_path in all_candidates:
        if is_existing_file(each_path) and each_path not in all_found:
            all_found[each_path] = None
            all_unseen.append(each_path)
    return all_unseen


def _import_closure(all_starts: list[Path]) -> list[Path]:
    all_found = {each_start: None for each_start in all_starts if each_start.is_file()}
    all_current = list(all_found)
    for each_hop in range(MAX_IMPORT_HOPS):
        all_current = _unseen_imports(all_current, all_found)
    return list(all_found)


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
                each_path.resolve()
                for each_path in sorted(
                    each_rules_directory.rglob(f"*{MARKDOWN_SUFFIX}")
                )
                if each_path.is_file()
            )
    return all_rule_files


def launch_files(repository_root: Path, config: InstructionBudgetConfig) -> list[Path]:
    """List the files an agent loads at launch.

    Args:
        repository_root: Resolved repository root.
        config: The repository's budget limits, which add its rule folders.

    Returns:
        Each entry file and unscoped rule, then the files they import, once each.
    """
    all_unscoped_rules = [
        each_rule
        for each_rule in rule_files(repository_root, config)
        if not _has_paths_frontmatter(read_instruction_text(each_rule))
    ]
    return _import_closure(_entry_files(repository_root) + all_unscoped_rules)


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
            (Path(each_directory) / each_name).resolve()
            for each_name in each_file_names
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
