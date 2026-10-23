#!/usr/bin/env python3
"""PostToolUse hook that runs a repository's lint on each file the agent edits.

The agent edits ``tools/report.py`` in a repository that opts in. The hook runs
that repository's lint command on the file and hands the findings back to the
agent, so it fixes them in the same turn::

    environment list:  owner/repo
    <repo>/.claude/edit-lint.json:
        {"file_suffixes": [".py"],
         "command": ["python", "lint.py", "--advisory", "{file}"]}

    Edit tools/report.py  ->  additionalContext:
        "The repository's lint found these problems in tools/report.py ..."

A repository takes part only when its origin ``owner/repo`` slug is in
``CLAUDE_EDIT_LINT_REPOSITORIES`` and it commits ``.claude/edit-lint.json``.
The command runs from the repository root, and ``{file}`` in it becomes the
edited path. Its standard output is the findings; empty output adds nothing.
A command that exits non-zero, times out, or cannot start adds nothing and
writes one diagnostic line to stderr. The hook never blocks and never edits
the file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    _hooks_directory = str(Path(__file__).resolve().parent.parent)
    _blocking_directory = str(Path(_hooks_directory) / "blocking")
    for each_bootstrap_directory in (_hooks_directory, _blocking_directory):
        if each_bootstrap_directory not in sys.path:
            sys.path.insert(0, each_bootstrap_directory)
    from hooks_constants.edit_lint_context_constants import (
        ALL_EDIT_TOOL_NAMES,
        ALL_GIT_TOPLEVEL_COMMAND,
        COMMAND_KEY,
        CONFIG_RELATIVE_PATH,
        FILE_PLACEHOLDER,
        FILE_SUFFIXES_KEY,
        FINDINGS_CONTEXT_TEMPLATE,
        GIT_COMMAND_TIMEOUT_SECONDS,
        LINT_COMMAND_TIMEOUT_SECONDS,
        LINT_FAILURE_DIAGNOSTIC_TEMPLATE,
        MAXIMUM_FINDINGS_CHARACTERS,
        REPOSITORIES_ENVIRONMENT_VARIABLE,
        REPOSITORY_SEPARATOR,
        TRUNCATION_NOTICE,
    )
    from hooks_constants.post_tool_use_context import write_post_tool_use_context_to_stdout
    from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
    from hooks_constants.subprocess_window import hidden_window_creation_flags
    from pii_prevention_blocker_parts.repository_exemption import repository_origin_slug
except ImportError as import_error:
    raise ImportError(
        "edit_lint_context: cannot import its sibling modules; "
        "ensure the hooks directory is importable."
    ) from import_error


@dataclass(frozen=True)
class EditLintConfig:
    """A repository's edit lint settings from ``.claude/edit-lint.json``.

    Attributes:
        all_file_suffixes: File suffixes the command lints, such as ``.py``.
        all_command_parts: The command and its arguments, with ``{file}``
            where the edited path goes.
    """

    all_file_suffixes: tuple[str, ...]
    all_command_parts: tuple[str, ...]


def opted_in_repository_slugs() -> frozenset[str]:
    """Return the lowercased ``owner/repo`` slugs the environment value lists.

    Returns:
        Each non-empty comma-separated entry of
        ``CLAUDE_EDIT_LINT_REPOSITORIES``, stripped and lowercased.
    """
    listed = os.environ.get(REPOSITORIES_ENVIRONMENT_VARIABLE, "")
    return frozenset(
        each.strip().casefold() for each in listed.split(REPOSITORY_SEPARATOR) if each.strip()
    )


def repository_root_of(file_path: Path) -> Path | None:
    """Return the git work tree root that holds the file, or None.

    Args:
        file_path: Absolute path of the edited file.

    Returns:
        The work tree root, or None when the file sits outside a git work tree
        or git cannot run.
    """
    try:
        completed_process = subprocess.run(
            list(ALL_GIT_TOPLEVEL_COMMAND),
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
            cwd=str(file_path.parent),
            creationflags=hidden_window_creation_flags(),
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if completed_process.returncode != 0:
        return None
    return Path(completed_process.stdout.strip())


def load_edit_lint_config(repository_root: Path) -> EditLintConfig | None:
    """Read the repository's ``.claude/edit-lint.json``, or None when unusable.

    Args:
        repository_root: The git work tree root.

    Returns:
        The parsed settings, or None when the file is missing, is not JSON, or
        lacks a non-empty string list under ``file_suffixes`` or ``command``.
    """
    try:
        raw_config = json.loads(
            (repository_root / CONFIG_RELATIVE_PATH).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    if not isinstance(raw_config, dict):
        return None
    all_file_suffixes = _string_tuple(raw_config.get(FILE_SUFFIXES_KEY))
    all_command_parts = _string_tuple(raw_config.get(COMMAND_KEY))
    if not all_file_suffixes or not all_command_parts:
        return None
    return EditLintConfig(all_file_suffixes, all_command_parts)


def _string_tuple(raw_value: object) -> tuple[str, ...]:
    if not isinstance(raw_value, list):
        return ()
    if not all(isinstance(each, str) and each for each in raw_value):
        return ()
    return tuple(raw_value)


def lint_findings(config: EditLintConfig, repository_root: Path, file_path: Path) -> str:
    """Run the lint command on one file and return its findings text.

    Args:
        config: The repository's edit lint settings.
        repository_root: The directory the command runs from.
        file_path: The edited file, put where ``{file}`` stands.

    Returns:
        The command's standard output, stripped. An empty string when the
        command printed nothing, exited non-zero, timed out, or could not
        start.
    """
    completed_process = _run_lint_command(config, repository_root, file_path)
    if completed_process is None:
        return ""
    if completed_process.returncode != 0:
        last_error_line = (completed_process.stderr.strip().splitlines() or [""])[-1]
        _write_failure_diagnostic(
            file_path, f"exit {completed_process.returncode}: {last_error_line}"
        )
        return ""
    return completed_process.stdout.strip()


def _run_lint_command(
    config: EditLintConfig, repository_root: Path, file_path: Path
) -> subprocess.CompletedProcess[str] | None:
    all_arguments = [
        each_part.replace(FILE_PLACEHOLDER, str(file_path))
        for each_part in config.all_command_parts
    ]
    try:
        return subprocess.run(
            all_arguments,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=LINT_COMMAND_TIMEOUT_SECONDS,
            cwd=str(repository_root),
            creationflags=hidden_window_creation_flags(),
        )
    except subprocess.TimeoutExpired:
        _write_failure_diagnostic(file_path, "timed out")
    except OSError as start_error:
        _write_failure_diagnostic(file_path, str(start_error))
    return None


def _write_failure_diagnostic(file_path: Path, failure_text: str) -> None:
    sys.stderr.write(LINT_FAILURE_DIAGNOSTIC_TEMPLATE % (file_path, failure_text))


def findings_context(file_label: str, findings_text: str) -> str:
    """Return the note the agent reads, with the findings cut to the size limit.

    Args:
        file_label: The edited file as the note names it.
        findings_text: The lint command's findings.

    Returns:
        The note text.
    """
    if len(findings_text) > MAXIMUM_FINDINGS_CHARACTERS:
        findings_text = findings_text[:MAXIMUM_FINDINGS_CHARACTERS] + TRUNCATION_NOTICE.format(
            limit=MAXIMUM_FINDINGS_CHARACTERS
        )
    return FINDINGS_CONTEXT_TEMPLATE.format(file=file_label, findings=findings_text)


def _edited_file_path(all_hook_fields: dict[str, object]) -> Path | None:
    if all_hook_fields.get("tool_name") not in ALL_EDIT_TOOL_NAMES:
        return None
    tool_input = all_hook_fields.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw_path = tool_input.get("file_path")
    if not isinstance(raw_path, str) or not raw_path:
        return None
    file_path = Path(raw_path)
    return file_path if file_path.is_absolute() and file_path.is_file() else None


def main() -> None:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return
    all_opted_in_slugs = opted_in_repository_slugs()
    if not all_opted_in_slugs:
        return
    file_path = _edited_file_path(hook_input)
    if file_path is None:
        return
    repository_root = repository_root_of(file_path)
    if repository_root is None:
        return
    if repository_origin_slug(repository_root) not in all_opted_in_slugs:
        return
    config = load_edit_lint_config(repository_root)
    if config is None or file_path.suffix not in config.all_file_suffixes:
        return
    findings_text = lint_findings(config, repository_root, file_path)
    if not findings_text:
        return
    try:
        file_label = file_path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError:
        file_label = str(file_path)
    write_post_tool_use_context_to_stdout(findings_context(file_label, findings_text))


if __name__ == "__main__":
    main()
