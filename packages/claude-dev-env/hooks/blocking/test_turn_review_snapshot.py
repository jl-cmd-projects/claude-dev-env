import subprocess
from pathlib import Path

import pytest

from turn_review_snapshot import turn_changed_paths, working_tree_snapshot


def git(repository: Path, *all_arguments: str) -> str:
    return subprocess.run(
        ["git", *all_arguments], cwd=repository, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "service.py").write_text("call()\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "start")
    return tmp_path


def test_should_chain_a_snapshot_onto_the_previous_one(repository: Path) -> None:
    base_commit = working_tree_snapshot(repository, None)
    assert base_commit is not None
    assert git(repository, "rev-parse", f"{base_commit}^") == git(repository, "rev-parse", "HEAD")
    (repository / "service.py").write_text("call(1)\n")
    turn_commit = working_tree_snapshot(repository, base_commit)
    assert turn_commit is not None
    assert git(repository, "rev-parse", f"{turn_commit}^") == base_commit
    assert turn_changed_paths(repository, base_commit, turn_commit) == ["service.py"]


def test_should_count_an_untracked_file_and_leave_the_user_index_alone(repository: Path) -> None:
    base_commit = working_tree_snapshot(repository, None)
    assert base_commit is not None
    (repository / "notes.txt").write_text("new\n")
    turn_commit = working_tree_snapshot(repository, base_commit)
    assert turn_commit is not None
    assert turn_changed_paths(repository, base_commit, turn_commit) == ["notes.txt"]
    assert git(repository, "status", "--porcelain") == "?? notes.txt"


def test_should_return_the_base_when_nothing_changed(repository: Path) -> None:
    base_commit = working_tree_snapshot(repository, None)
    assert base_commit is not None
    assert working_tree_snapshot(repository, base_commit) == base_commit
    assert turn_changed_paths(repository, base_commit, base_commit) == []


def test_should_return_none_outside_a_repository(tmp_path: Path) -> None:
    assert working_tree_snapshot(tmp_path, None) is None


def test_should_name_a_non_ascii_path_as_written(repository: Path) -> None:
    base_commit = working_tree_snapshot(repository, None)
    assert base_commit is not None
    (repository / "caf\u00e9.py").write_text("call()\n")
    turn_commit = working_tree_snapshot(repository, base_commit)
    assert turn_commit is not None
    assert turn_changed_paths(repository, base_commit, turn_commit) == ["caf\u00e9.py"]


def test_should_list_a_path_whose_name_is_not_utf8(repository: Path) -> None:
    base_commit = git(repository, "rev-parse", "HEAD")
    blob = git(repository, "hash-object", "-w", "service.py")
    tree = subprocess.run(
        ["git", "mktree"],
        cwd=repository,
        input=b"100644 blob " + blob.encode() + b"\tcaf\xe9.py\n",
        check=True,
        capture_output=True,
    ).stdout.decode().strip()
    turn_commit = git(repository, "commit-tree", tree, "-p", base_commit, "-m", "odd name")
    assert turn_changed_paths(repository, base_commit, turn_commit) == ["caf\udce9.py"]


def test_should_snapshot_on_a_host_with_no_git_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_global_config = tmp_path / "empty-gitconfig"
    empty_global_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_global_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for each_name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(each_name, raising=False)
    repository = tmp_path / "repository"
    repository.mkdir()
    git(repository, "init", "-q", "-b", "main")
    (repository / "service.py").write_text("call()\n")
    git(repository, "add", "-A")
    git(repository, "-c", "user.name=Start", "-c", "user.email=start", "commit", "-q", "-m", "start")
    git(repository, "config", "user.useConfigOnly", "true")
    (repository / "service.py").write_text("call_again()\n")
    base_commit = git(repository, "rev-parse", "HEAD")
    turn_commit = working_tree_snapshot(repository, None)
    assert turn_changed_paths(repository, base_commit, turn_commit) == ["service.py"]


def test_should_keep_the_leading_space_of_a_changed_path(repository: Path) -> None:
    base_commit = working_tree_snapshot(repository, None)
    (repository / " notes.txt").write_text("new\n")
    turn_commit = working_tree_snapshot(repository, base_commit)
    assert turn_changed_paths(repository, base_commit, turn_commit) == [" notes.txt"]
