import os
import subprocess
import sys
from pathlib import Path

import pytest

flow_directory = Path(__file__).resolve().parents[1]
all_import_roots = [str(flow_directory), str(flow_directory.parent / "features-start-with-an-eval")]
sys.path[:0] = all_import_roots

from rules_eval_support import install

READ_A_UTF8_RULE = (
    "from rules_eval_support.install import _read_git\n"
    "print(ascii(_read_git('show', 'HEAD:packages/claude-dev-env/rules/code-standards.md')))\n"
)


def _commit_files(repository: Path, text_by_path: dict[str, str]) -> None:
    for each_path, each_text in text_by_path.items():
        target = repository / each_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(each_text, encoding="utf-8")
    for each_command in (
        ("git", "init", "-q", "-b", "main"),
        ("git", "add", "-A"),
        ("git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-q", "-m", "rules"),
    ):
        subprocess.run(each_command, cwd=repository, check=True, capture_output=True)


def test_variant_files_keeps_unscoped_rules_and_all_guides(monkeypatch: pytest.MonkeyPatch) -> None:
    sources = {
        "HEAD:packages/claude-dev-env/rules": "index.md\0scoped.md\0",
        "HEAD:packages/claude-dev-env/docs/rule-guides": "guide.md\0",
        "HEAD:packages/claude-dev-env/rules/index.md": "Always loaded.\n",
        "HEAD:packages/claude-dev-env/rules/scoped.md": "---\npaths: src/**\n---\nScoped.\n",
        "HEAD:packages/claude-dev-env/docs/rule-guides/guide.md": "Guide.\n",
    }
    monkeypatch.setattr(install, "_read_git", lambda *args: sources[args[-1]])

    assert install.variant_files("HEAD") == {
        ".claude/rules/index.md": "Always loaded.\n",
        ".claude/docs/rule-guides/guide.md": "Guide.\n",
    }


def test_variant_files_includes_rules_in_subfolders_and_with_spaces(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _commit_files(
        tmp_path,
        {
            "packages/claude-dev-env/rules/index.md": "Index.\n",
            "packages/claude-dev-env/rules/team/nested.md": "Nested.\n",
            "packages/claude-dev-env/rules/my rule.md": "Spaced.\n",
            "packages/claude-dev-env/docs/rule-guides/shell/guide.md": "Guide.\n",
        },
    )
    monkeypatch.setattr(install, "REPOSITORY_ROOT", tmp_path)

    assert install.variant_files("HEAD") == {
        ".claude/rules/index.md": "Index.\n",
        ".claude/rules/team/nested.md": "Nested.\n",
        ".claude/rules/my rule.md": "Spaced.\n",
        ".claude/docs/rule-guides/shell/guide.md": "Guide.\n",
    }


def test_read_git_decodes_utf8_rule_text_under_an_ascii_locale() -> None:
    environment = {**os.environ, "LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0", "PYTHONPATH": os.pathsep.join(all_import_roots)}

    completed = subprocess.run(
        [sys.executable, "-X", "utf8=0", "-c", READ_A_UTF8_RULE],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "\\xa7" in completed.stdout


def test_prepare_workspace_commits_the_fixture_and_the_variant_files() -> None:
    workspace = install.prepare_workspace({".claude/rules/index.md": "Index.\n"})

    assert (workspace / ".claude/rules/index.md").read_text(encoding="utf-8") == "Index.\n"
    assert (workspace / "jobs/durations.py").is_file()
    assert (workspace / "logs/alpha.log").read_text(encoding="utf-8") == "job finished\n"
    tracked = subprocess.run(("git", "ls-files"), cwd=workspace, check=True, capture_output=True, text=True).stdout.split()
    assert ".claude/rules/index.md" in tracked


def test_installed_digest_changes_with_a_rule_text_or_path() -> None:
    files_by_target = {".claude/rules/index.md": "Index.\n"}

    assert install.installed_digest(files_by_target) == install.installed_digest(dict(files_by_target))
    assert install.installed_digest(files_by_target) != install.installed_digest({".claude/rules/index.md": "Index!\n"})
    assert install.installed_digest(files_by_target) != install.installed_digest({".claude/rules/other.md": "Index.\n"})
