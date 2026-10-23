"""Behavior tests for the edit lint context hook.

Each test builds a disposable git repository whose origin points at a
github.com slug and whose ``.claude/edit-lint.json`` names a small lint script.
The script prints one finding for every line holding ``BAD``. The hook runs
through the PostToolUse dispatcher the way the live entry runs it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

try:
    advisory_directory = str(Path(__file__).resolve().parent)
    if advisory_directory not in sys.path:
        sys.path.insert(0, advisory_directory)
    import edit_lint_context
except ImportError as import_error:
    raise ImportError(
        "test_edit_lint_context: cannot import its sibling modules; "
        "ensure the advisory directory is importable."
    ) from import_error


HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
DISPATCHER_PATH = HOOKS_DIRECTORY / "validation" / "post_tool_use_dispatcher.py"
HOOKS_JSON_PATH = HOOKS_DIRECTORY / "hooks.json"
ORIGIN_SLUG = "LintOwner/lint-repo"
ORIGIN_URL = f"https://github.com/{ORIGIN_SLUG}.git"
LINT_SCRIPT_SOURCE = (
    "import sys\n"
    "path = sys.argv[1]\n"
    "for number, line in enumerate(open(path, encoding='utf-8'), 1):\n"
    "    if 'BAD' in line:\n"
    "        print(f'{path}:{number}: F821 undefined name')\n"
    "    if 'CRASH' in line:\n"
    "        sys.stderr.write('lint tool missing\\n')\n"
    "        sys.exit(3)\n"
)
DISPATCHER_TIMEOUT_SECONDS = 60


def _git_environment() -> dict[str, str]:
    return {
        each_name: each_value
        for each_name, each_value in os.environ.items()
        if not each_name.upper().startswith("GIT_")
    }


def _run_git(repository_root: Path, *all_arguments: str) -> None:
    subprocess.run(
        ["git", *all_arguments],
        cwd=repository_root,
        check=True,
        capture_output=True,
        env=_git_environment(),
    )


@pytest.fixture
def lint_repository(tmp_path: Path) -> Path:
    repository_root = tmp_path / "lint-repo"
    repository_root.mkdir()
    _run_git(repository_root, "init", "--quiet")
    _run_git(repository_root, "remote", "add", "origin", ORIGIN_URL)
    (repository_root / "lint.py").write_text(LINT_SCRIPT_SOURCE, encoding="utf-8")
    config_path = repository_root / ".claude" / "edit-lint.json"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps({"file_suffixes": [".py"], "command": [sys.executable, "lint.py", "{file}"]}),
        encoding="utf-8",
    )
    return repository_root


def _run_dispatcher(
    tool_name: str,
    file_path: Path,
    listed_repositories: str | None,
    project_directory: Path | None = None,
) -> str:
    environment = _git_environment()
    environment["CLAUDE_PROJECT_DIR"] = str(project_directory or file_path.parents[-2])
    environment.pop("CLAUDE_EDIT_LINT_REPOSITORIES", None)
    if listed_repositories is not None:
        environment["CLAUDE_EDIT_LINT_REPOSITORIES"] = listed_repositories
    completed_process = subprocess.run(
        [sys.executable, str(DISPATCHER_PATH)],
        input=json.dumps({"tool_name": tool_name, "tool_input": {"file_path": str(file_path)}}),
        capture_output=True,
        text=True,
        env=environment,
        timeout=DISPATCHER_TIMEOUT_SECONDS,
        check=False,
    )
    assert completed_process.returncode == 0, completed_process.stderr
    return completed_process.stdout.strip()


def _additional_context(dispatcher_output: str) -> str:
    return json.loads(dispatcher_output)["hookSpecificOutput"]["additionalContext"]


def should_add_findings_after_an_edit_in_an_opted_in_repository(lint_repository: Path) -> None:
    edited_file = lint_repository / "module.py"
    edited_file.write_text("VALUE = 1\nRESULT = BAD\n", encoding="utf-8")

    note = _additional_context(_run_dispatcher("Edit", edited_file, ORIGIN_SLUG.lower()))

    assert "module.py:2: F821 undefined name" in note
    assert note.startswith("The repository's lint found these problems in module.py")


def should_add_findings_after_a_write_and_a_multi_edit(lint_repository: Path) -> None:
    edited_file = lint_repository / "module.py"
    edited_file.write_text("RESULT = BAD\n", encoding="utf-8")

    for each_tool_name in ("Write", "MultiEdit"):
        note = _additional_context(_run_dispatcher(each_tool_name, edited_file, ORIGIN_SLUG))
        assert "module.py:1: F821" in note


def should_pass_the_lint_command_the_path_with_symlinks_resolved(
    lint_repository: Path, tmp_path: Path
) -> None:
    package_directory = lint_repository / "package"
    package_directory.mkdir()
    (package_directory / "module.py").write_text("RESULT = BAD\n", encoding="utf-8")
    linked_directory = tmp_path / "linked-package"
    linked_directory.symlink_to(package_directory, target_is_directory=True)

    note = _additional_context(
        _run_dispatcher("Edit", linked_directory / "module.py", ORIGIN_SLUG)
    )

    assert f"{(package_directory / 'module.py').resolve()}:1: F821" in note
    assert "linked-package" not in note


def should_add_nothing_when_the_environment_lists_no_repository(lint_repository: Path) -> None:
    edited_file = lint_repository / "module.py"
    edited_file.write_text("RESULT = BAD\n", encoding="utf-8")

    assert _run_dispatcher("Edit", edited_file, None) == ""
    assert _run_dispatcher("Edit", edited_file, "other/repo") == ""


def should_add_nothing_for_a_repository_outside_the_project_folder(
    lint_repository: Path, tmp_path: Path
) -> None:
    edited_file = lint_repository / "module.py"
    edited_file.write_text("RESULT = BAD\n", encoding="utf-8")
    other_project = tmp_path / "other-project"
    other_project.mkdir()

    assert _run_dispatcher("Edit", edited_file, ORIGIN_SLUG, other_project) == ""


def should_accept_a_root_inside_the_project_folder(
    lint_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(lint_repository.parent))
    assert edit_lint_context.is_inside_project_directory(lint_repository)

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(lint_repository / "package"))
    assert not edit_lint_context.is_inside_project_directory(lint_repository)


def should_add_nothing_after_a_clean_edit(lint_repository: Path) -> None:
    edited_file = lint_repository / "module.py"
    edited_file.write_text("VALUE = 1\n", encoding="utf-8")

    assert _run_dispatcher("Edit", edited_file, ORIGIN_SLUG) == ""


def should_add_nothing_for_a_suffix_the_repository_does_not_lint(lint_repository: Path) -> None:
    edited_file = lint_repository / "notes.md"
    edited_file.write_text("BAD\n", encoding="utf-8")

    assert _run_dispatcher("Edit", edited_file, ORIGIN_SLUG) == ""


def should_add_nothing_when_the_lint_command_fails(lint_repository: Path) -> None:
    edited_file = lint_repository / "module.py"
    edited_file.write_text("RESULT = BAD\nCRASH\n", encoding="utf-8")

    assert _run_dispatcher("Edit", edited_file, ORIGIN_SLUG) == ""


def should_add_nothing_for_a_file_outside_a_git_repository(tmp_path: Path) -> None:
    loose_file = tmp_path / "loose.py"
    loose_file.write_text("RESULT = BAD\n", encoding="utf-8")

    assert _run_dispatcher("Edit", loose_file, ORIGIN_SLUG) == ""


def should_register_the_dispatcher_for_edit_write_and_multi_edit() -> None:
    registrations = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
    all_matchers = [
        each_group["matcher"]
        for each_group in registrations["hooks"]["PostToolUse"]
        if any(
            "post_tool_use_dispatcher.py" in each_hook["command"]
            for each_hook in each_group["hooks"]
        )
    ]

    assert all_matchers == ["Write|Edit|MultiEdit"]


def should_read_listed_slugs_lowercased(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_EDIT_LINT_REPOSITORIES", " Owner/One , ,owner/two")

    assert edit_lint_context.opted_in_repository_slugs() == frozenset({"owner/one", "owner/two"})


def should_find_the_work_tree_root_of_a_nested_file(lint_repository: Path) -> None:
    nested_directory = lint_repository / "package"
    nested_directory.mkdir()
    nested_file = nested_directory / "inner.py"
    nested_file.write_text("VALUE = 1\n", encoding="utf-8")

    found_root = edit_lint_context.repository_root_of(nested_file)

    assert found_root is not None
    assert found_root.resolve() == lint_repository.resolve()


def should_reject_a_config_without_a_command(lint_repository: Path) -> None:
    config_path = lint_repository / ".claude" / "edit-lint.json"
    config_path.write_text(json.dumps({"file_suffixes": [".py"], "command": []}), encoding="utf-8")

    assert edit_lint_context.load_edit_lint_config(lint_repository) is None


def should_load_the_suffixes_and_command(lint_repository: Path) -> None:
    config = edit_lint_context.load_edit_lint_config(lint_repository)

    assert config == edit_lint_context.EditLintConfig(
        (".py",), (sys.executable, "lint.py", "{file}")
    )


def should_return_the_lint_output_for_one_file(lint_repository: Path) -> None:
    edited_file = lint_repository / "module.py"
    edited_file.write_text("RESULT = BAD\n", encoding="utf-8")
    config = edit_lint_context.load_edit_lint_config(lint_repository)
    assert config is not None

    assert edit_lint_context.lint_findings(config, lint_repository, edited_file) == (
        f"{edited_file}:1: F821 undefined name"
    )


def should_cut_long_findings_to_the_limit() -> None:
    long_findings = "x" * 5000

    note = edit_lint_context.findings_context("module.py", long_findings)

    assert "x" * 4000 in note
    assert "x" * 4001 not in note
    assert note.endswith("[edit lint output cut at 4000 characters]")
