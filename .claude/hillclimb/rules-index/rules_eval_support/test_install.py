import os
import subprocess
import sys
from pathlib import Path

import pytest

flow_directory = Path(__file__).resolve().parents[1]
all_import_roots = [str(flow_directory), str(flow_directory.parent / "features-start-with-an-eval")]
sys.path[:0] = all_import_roots

from rules_eval_support import install
from session_eval_support.session import files_digest, remove_workspace

READ_A_UTF8_RULE = (
    "import sys\n"
    "from pathlib import Path\n"
    "from rules_eval_support import install\n"
    "install.REPOSITORY_ROOT = Path(sys.argv[1])\n"
    "print(ascii(install._read_git('show', 'HEAD:packages/claude-dev-env/rules/section.md')))\n"
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


def test_read_git_decodes_utf8_rule_text_under_an_ascii_locale(tmp_path: Path) -> None:
    _commit_files(tmp_path, {"packages/claude-dev-env/rules/section.md": "See CODE_RULES \u00a78.\n"})
    environment = {**os.environ, "LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0", "PYTHONPATH": os.pathsep.join(all_import_roots)}

    completed = subprocess.run(
        [sys.executable, "-X", "utf8=0", "-c", READ_A_UTF8_RULE, str(tmp_path)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "\\xa78" in completed.stdout


def test_prepare_workspace_commits_the_variant_files_with_the_bytes_the_digest_covers() -> None:
    files_by_target = {".claude/rules/index.md": "Index.\nSecond line.\n"}
    workspace = install.prepare_workspace(files_by_target)
    try:
        installed_bytes = (workspace / ".claude/rules/index.md").read_bytes()
        tracked = subprocess.run(("git", "ls-files"), cwd=workspace, check=True, capture_output=True, text=True).stdout.split()
        assert installed_bytes == b"Index.\nSecond line.\n"
        assert install.installed_digest(files_by_target) == files_digest({".claude/rules/index.md": installed_bytes})
        assert (workspace / "jobs/durations.py").is_file()
        assert (workspace / "logs/alpha.log").read_text(encoding="utf-8") == "job finished\n"
        assert ".claude/rules/index.md" in tracked
    finally:
        remove_workspace(workspace)


def test_installed_digest_changes_with_a_rule_text_or_path() -> None:
    files_by_target = {".claude/rules/index.md": "Index.\n"}

    assert install.installed_digest(files_by_target) == install.installed_digest(dict(files_by_target))
    assert install.installed_digest(files_by_target) != install.installed_digest({".claude/rules/index.md": "Index!\n"})
    assert install.installed_digest(files_by_target) != install.installed_digest({".claude/rules/other.md": "Index.\n"})
