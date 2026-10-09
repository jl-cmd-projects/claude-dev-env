"""Build one variant's workspace: the fixture project plus the rules that variant loads."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from rules_eval_support.config.constants import (
    ALL_LOG_FILE_NAMES,
    FIXTURE_OVERLAY_DIRECTORY,
    FRONTMATTER_DELIMITER,
    GUIDES_SOURCE_DIRECTORY,
    GUIDES_TARGET_DIRECTORY,
    LOG_FILE_TEXT,
    MARKDOWN_SUFFIX,
    PATHS_FRONTMATTER_KEY,
    REPOSITORY_ROOT,
    RULES_SOURCE_DIRECTORY,
    RULES_TARGET_DIRECTORY,
    SIBLING_FLOW_ROOT,
    WORKSPACE_PREFIX,
)


def _git_output(*all_arguments: str) -> str:
    return subprocess.run(
        ("git", *all_arguments),
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _markdown_names(ref: str, directory: str) -> list[str]:
    return [
        each_path
        for each_path in _git_output("ls-tree", "--name-only", f"{ref}:{directory}").split()
        if each_path.endswith(MARKDOWN_SUFFIX)
    ]


def _loads_in_every_session(rule_text: str) -> bool:
    all_lines = rule_text.splitlines()
    if not all_lines or all_lines[0] != FRONTMATTER_DELIMITER:
        return True
    for each_line in all_lines[1:]:
        if each_line == FRONTMATTER_DELIMITER:
            return True
        if each_line.startswith(PATHS_FRONTMATTER_KEY):
            return False
    return True


def variant_files(ref: str) -> dict[str, str]:
    """Return the always-loaded rules and every rule guide at a git ref.

    ::

        variant_files("HEAD") -> {".claude/rules/index.md": "...",
                                  ".claude/docs/rule-guides/research-mode.md": "...", ...}

    Args:
        ref: The commit whose rules the variant loads.

    Returns:
        Each workspace path mapped to its text. Rules scoped by ``paths:``
        stay out, because no case opens a file they match.
    """
    files_by_target: dict[str, str] = {}
    for each_name in _markdown_names(ref, RULES_SOURCE_DIRECTORY):
        rule_text = _git_output("show", f"{ref}:{RULES_SOURCE_DIRECTORY}/{each_name}")
        if _loads_in_every_session(rule_text):
            files_by_target[f"{RULES_TARGET_DIRECTORY}/{each_name}"] = rule_text
    for each_name in _markdown_names(ref, GUIDES_SOURCE_DIRECTORY):
        files_by_target[f"{GUIDES_TARGET_DIRECTORY}/{each_name}"] = _git_output(
            "show", f"{ref}:{GUIDES_SOURCE_DIRECTORY}/{each_name}"
        )
    return files_by_target


def prepare_workspace(files_by_target: dict[str, str]) -> Path:
    """Copy the fixture project, its overlay, and a variant's rules into a new git workspace.

    Args:
        files_by_target: The variant's files from variant_files.

    Returns:
        The workspace directory, committed on branch main.
    """
    workspace = Path(tempfile.mkdtemp(prefix=WORKSPACE_PREFIX))
    shutil.copytree(SIBLING_FLOW_ROOT / "fixture", workspace, dirs_exist_ok=True)
    shutil.copytree(FIXTURE_OVERLAY_DIRECTORY, workspace, dirs_exist_ok=True)
    for each_log_name in ALL_LOG_FILE_NAMES:
        log_path = workspace / each_log_name
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(LOG_FILE_TEXT, encoding="utf-8")
    for each_target, each_text in files_by_target.items():
        target_path = workspace / each_target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(each_text, encoding="utf-8")
    for each_command in (
        ("git", "init", "-q", "-b", "main"),
        ("git", "add", "-A"),
        ("git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", "fixture"),
    ):
        subprocess.run(each_command, cwd=workspace, check=True, capture_output=True)
    return workspace
