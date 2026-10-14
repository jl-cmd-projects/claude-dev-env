import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

flow_directory = Path(__file__).resolve().parents[1]
all_import_roots = [str(flow_directory), str(flow_directory.parent / "features-start-with-an-eval")]
sys.path[:0] = all_import_roots

from rules_eval_support import install
from session_eval_support.session import prepare_workspace, remove_workspace

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


def test_workspace_files_holds_the_overlay_logs_and_variant_files_without_caches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    overlay = tmp_path / "fixture_overlay"
    shutil.copytree(install.FIXTURE_OVERLAY_DIRECTORY, overlay, ignore=shutil.ignore_patterns("__pycache__"))
    (overlay / "jobs" / "__pycache__").mkdir()
    (overlay / "jobs" / "__pycache__" / "durations.cpython-313.pyc").write_bytes(b"cache")
    monkeypatch.setattr(install, "FIXTURE_OVERLAY_DIRECTORY", overlay)

    bytes_by_target = install.workspace_files({".claude/rules/index.md": "Index.\nSecond line.\n"})

    assert bytes_by_target[".claude/rules/index.md"] == b"Index.\nSecond line.\n"
    assert bytes_by_target["logs/alpha.log"] == b"job finished\n"
    assert bytes_by_target["jobs/durations.py"] == (install.FIXTURE_OVERLAY_DIRECTORY / "jobs/durations.py").read_bytes()
    assert not any("__pycache__" in each_target for each_target in bytes_by_target)


def test_workspace_files_install_into_a_committed_workspace() -> None:
    workspace = prepare_workspace(install.workspace_files({".claude/rules/index.md": "Index.\n"}))
    try:
        tracked = subprocess.run(("git", "ls-files"), cwd=workspace, check=True, capture_output=True, text=True).stdout.split()
        assert {".claude/rules/index.md", "jobs/durations.py", "logs/alpha.log", "README.md"} <= set(tracked)
    finally:
        remove_workspace(workspace)
