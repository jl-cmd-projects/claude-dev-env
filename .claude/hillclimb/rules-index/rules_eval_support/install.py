"""Gather one variant's workspace files: the fixture overlay, the logs, and the rules that variant loads."""

import subprocess

from rules_eval_support.config.constants import (
    ALL_LOG_FILE_NAMES,
    FIXTURE_OVERLAY_DIRECTORY,
    FRONTMATTER_DELIMITER,
    GUIDES_SOURCE_DIRECTORY,
    GIT_EXECUTABLE,
    GUIDES_TARGET_DIRECTORY,
    LOG_FILE_TEXT,
    MARKDOWN_SUFFIX,
    PATH_LIST_SEPARATOR,
    PATHS_FRONTMATTER_KEY,
    PYTHON_CACHE_DIRECTORY_NAME,
    REPOSITORY_ROOT,
    RULES_SOURCE_DIRECTORY,
    RULES_TARGET_DIRECTORY,
)


def _read_git(*all_arguments: str) -> str:
    return subprocess.run(
        (GIT_EXECUTABLE, *all_arguments),
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout


def _markdown_names(ref: str, directory: str) -> list[str]:
    return [
        each_path
        for each_path in _read_git("ls-tree", "-r", "-z", "--name-only", f"{ref}:{directory}").split(PATH_LIST_SEPARATOR)
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
        stay out of both variants, so the comparison covers the
        always-loaded rules only.
    """
    files_by_target: dict[str, str] = {}
    for each_name in _markdown_names(ref, RULES_SOURCE_DIRECTORY):
        rule_text = _read_git("show", f"{ref}:{RULES_SOURCE_DIRECTORY}/{each_name}")
        if _loads_in_every_session(rule_text):
            files_by_target[f"{RULES_TARGET_DIRECTORY}/{each_name}"] = rule_text
    for each_name in _markdown_names(ref, GUIDES_SOURCE_DIRECTORY):
        files_by_target[f"{GUIDES_TARGET_DIRECTORY}/{each_name}"] = _read_git(
            "show", f"{ref}:{GUIDES_SOURCE_DIRECTORY}/{each_name}"
        )
    return files_by_target


def workspace_files(files_by_target: dict[str, str]) -> dict[str, bytes]:
    """Return every file a rules workspace adds to the fixture project, as bytes.

    ::

        workspace_files({".claude/rules/index.md": "..."})
        -> {"jobs/durations.py": b"...", "logs/alpha.log": b"job finished\\n",
            ".claude/rules/index.md": b"...", ...}

    Args:
        files_by_target: The variant's files from variant_files.

    Returns:
        The fixture overlay, the log files, and the variant's rules and
        guides, each workspace path mapped to its bytes. Compiled Python
        caches in the overlay stay out.
    """
    bytes_by_target = {
        each_path.relative_to(FIXTURE_OVERLAY_DIRECTORY).as_posix(): each_path.read_bytes()
        for each_path in sorted(FIXTURE_OVERLAY_DIRECTORY.rglob("*"))
        if each_path.is_file() and PYTHON_CACHE_DIRECTORY_NAME not in each_path.parts
    }
    bytes_by_target.update({each_log_name: LOG_FILE_TEXT.encode("utf-8") for each_log_name in ALL_LOG_FILE_NAMES})
    bytes_by_target.update({each_target: each_text.encode("utf-8") for each_target, each_text in files_by_target.items()})
    return bytes_by_target
