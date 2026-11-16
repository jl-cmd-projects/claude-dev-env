"""Behavior tests for telling the auto mode rule flow's own steps apart."""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_mode_rule_steps import RuleFlowSetting, is_rule_flow_step

RULE_BRANCH = "claude/auto-mode-rule-own-push"


def _repository(tmp_path: Path, branch_name: str = RULE_BRANCH) -> Path:
    repository_root = tmp_path / "agent-channels"
    (repository_root / ".git").mkdir(parents=True, exist_ok=True)
    (repository_root / ".git" / "HEAD").write_text(
        f"ref: refs/heads/{branch_name}\n", encoding="utf-8"
    )
    return repository_root


def _worktree(tmp_path: Path, branch_name: str) -> Path:
    worktree_git_directory = tmp_path / "agent-channels" / ".git" / "worktrees" / "rule"
    worktree_git_directory.mkdir(parents=True)
    (worktree_git_directory / "HEAD").write_text(
        f"ref: refs/heads/{branch_name}\n", encoding="utf-8"
    )
    (worktree_git_directory / "commondir").write_text("../..\n", encoding="utf-8")
    worktree_directory = tmp_path / "scratch" / "agent-channels-rule"
    worktree_directory.mkdir(parents=True)
    (worktree_directory / ".git").write_text(
        f"gitdir: {worktree_git_directory}\n", encoding="utf-8"
    )
    (worktree_git_directory / "gitdir").write_text(
        f"{worktree_directory / '.git'}\n", encoding="utf-8"
    )
    return worktree_directory


def _is_step(
    tmp_path: Path,
    command: str,
    working_folder: Path | None = None,
    has_allowed_entry: bool = True,
    head_branch: str = RULE_BRANCH,
) -> bool:
    repository_root = _repository(tmp_path, head_branch)
    setting = RuleFlowSetting(repository_root, has_allowed_entry)
    folder = working_folder or repository_root
    return is_rule_flow_step("Bash", {"command": command}, str(folder), setting)


@pytest.mark.parametrize(
    "command",
    [
        "python3 setup/add_auto_mode_rule.py add --label 'Own push' --rule-file r.txt --ledger e.json",
        "python3 setup/add_auto_mode_rule.py validate --base origin/main",
    ],
)
def test_should_count_the_rule_tool_run_from_agent_channels_without_an_allowed_entry(
    tmp_path: Path, command: str
) -> None:
    assert _is_step(tmp_path, command, has_allowed_entry=False)


@pytest.mark.parametrize(
    "command",
    [
        f"git push -u origin {RULE_BRANCH}",
        f"git push origin {RULE_BRANCH}",
        'git commit -m "Add the Own push auto mode rule"',
    ],
)
def test_should_count_a_rule_branch_commit_or_push_with_an_allowed_entry(
    tmp_path: Path, command: str
) -> None:
    assert _is_step(tmp_path, command)
    assert not _is_step(tmp_path, command, has_allowed_entry=False)


def test_should_count_the_table_shapes_in_a_rule_worktree_of_agent_channels(
    tmp_path: Path,
) -> None:
    worktree_directory = _worktree(tmp_path, RULE_BRANCH)
    assert _is_step(tmp_path, "python3 setup/add_auto_mode_rule.py validate", worktree_directory)
    assert _is_step(tmp_path, 'git commit -m "Add"', worktree_directory)
    assert _is_step(tmp_path, f"git push -u origin {RULE_BRANCH}", worktree_directory)


@pytest.mark.parametrize(
    "command",
    [
        "cd /tmp/agent-channels-rule && python3 setup/add_auto_mode_rule.py validate",
        "cd ..",
        "python3 setup/add_auto_mode_rule.py validate\npython3 setup/add_auto_mode_rule.py add",
        "python3 setup/add_auto_mode_rule.py validate | tail -5",
        "python3 setup/add_auto_mode_rule.py validate; rm -rf ~/build",
        "python3 setup/add_auto_mode_rule.py add --label $LABEL",
        "python3 setup/add_auto_mode_rule.py add --label `id`",
        "python3 setup/add_auto_mode_rule.py add > ~/.bashrc",
        "python3 setup/add_auto_mode_rule.py add --label 'a;b'",
        "LABEL=x python3 setup/add_auto_mode_rule.py add",
        "python setup/add_auto_mode_rule.py add",
        "python3 ./setup/add_auto_mode_rule.py add",
        "python3 /tmp/other/setup/add_auto_mode_rule.py add",
        "python3 setup/add_auto_mode_rule.py remove",
        "python3 setup/add_auto_mode_rule.py",
        "python3 'setup/add_auto_mode_rule.py",
        "cat setup/add_auto_mode_rule.py",
        "git push --all origin",
        "git push --mirror origin",
        "git push --tags origin",
        f"git push --delete origin {RULE_BRANCH}",
        f"git push -f origin {RULE_BRANCH}",
        f"git push https://github.com/other/repo.git {RULE_BRANCH}",
        f"git -c core.sshCommand=/tmp/x push -u origin {RULE_BRANCH}",
        f"git -C /tmp/agent-channels push -u origin {RULE_BRANCH}",
        f"git push origin HEAD:refs/heads/{RULE_BRANCH}",
        f"git push origin {RULE_BRANCH} main",
        "git push -u origin",
        "git push origin claude/project-thread-rule",
        "git push origin claude/auto-mode-rule-Own_Push",
        "git add setup/auto-mode-allow.d/own-push.txt",
        "git commit -m Add -a",
        "git commit -am Add",
        "rm -rf ~/agent-channels-old/build",
        "git commit -m {a,--amend}",
        "git commit -m *",
        "git commit -m [s]etup",
        "git commit -m a?",
        "python3 setup/add_auto_mode_rule.py add --label {a,b}",
        "git commit\t-m Add",
    ],
)
def test_should_not_count_any_command_outside_the_table(tmp_path: Path, command: str) -> None:
    assert not _is_step(tmp_path, command)


def test_should_not_count_a_copied_worktree_folder(tmp_path: Path) -> None:
    worktree_directory = _worktree(tmp_path, RULE_BRANCH)
    copied_directory = tmp_path / "elsewhere" / "agent-channels-rule"
    copied_directory.mkdir(parents=True)
    (copied_directory / ".git").write_text(
        (worktree_directory / ".git").read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert _is_step(tmp_path, f"git push origin {RULE_BRANCH}", worktree_directory)
    assert not _is_step(tmp_path, f"git push origin {RULE_BRANCH}", copied_directory)
    assert not _is_step(
        tmp_path, "python3 setup/add_auto_mode_rule.py validate", copied_directory
    )


def test_should_not_count_a_folder_whose_git_file_links_to_a_worktree(tmp_path: Path) -> None:
    worktree_directory = _worktree(tmp_path, RULE_BRANCH)
    linking_directory = tmp_path / "elsewhere" / "agent-channels-rule"
    linking_directory.mkdir(parents=True)
    (linking_directory / ".git").symlink_to(worktree_directory / ".git")
    assert not _is_step(tmp_path, f"git push origin {RULE_BRANCH}", linking_directory)
    assert not _is_step(
        tmp_path, "python3 setup/add_auto_mode_rule.py validate", linking_directory
    )


def test_should_not_count_a_commit_while_head_is_on_another_branch(tmp_path: Path) -> None:
    assert not _is_step(tmp_path, 'git commit -m "Add"', head_branch="main")
    worktree_directory = _worktree(tmp_path, "claude/project-thread-rule")
    assert not _is_step(tmp_path, 'git commit -m "Add"', worktree_directory)


@pytest.mark.parametrize("folder_name", ["agent-channels-old", "agent-channels/docs", ""])
def test_should_not_count_a_table_shape_from_another_folder(
    tmp_path: Path, folder_name: str
) -> None:
    _repository(tmp_path)
    working_folder = tmp_path / folder_name
    working_folder.mkdir(parents=True, exist_ok=True)
    assert not _is_step(tmp_path, "python3 setup/add_auto_mode_rule.py validate", working_folder)
    assert not _is_step(tmp_path, f"git push -u origin {RULE_BRANCH}", working_folder)


def test_should_count_agent_channels_reached_through_a_symbolic_link(tmp_path: Path) -> None:
    repository_root = _repository(tmp_path)
    linked_folder = tmp_path / "linked-channels"
    linked_folder.symlink_to(repository_root)
    assert _is_step(tmp_path, "python3 setup/add_auto_mode_rule.py validate", linked_folder)


@pytest.mark.parametrize("working_folder", [None, "", "agent-channels"])
def test_should_not_count_a_step_with_no_absolute_working_folder(
    tmp_path: Path, working_folder: str | None
) -> None:
    setting = RuleFlowSetting(_repository(tmp_path), True)
    tool_input = {"command": "python3 setup/add_auto_mode_rule.py validate"}
    assert not is_rule_flow_step("Bash", tool_input, working_folder, setting)


def test_should_not_count_an_edit_of_the_rule_tool(tmp_path: Path) -> None:
    repository_root = _repository(tmp_path)
    setting = RuleFlowSetting(repository_root, True)
    tool_input = {"file_path": str(repository_root / "setup" / "add_auto_mode_rule.py")}
    assert not is_rule_flow_step("Edit", tool_input, str(repository_root), setting)


def test_should_not_count_a_worktree_whose_git_file_cannot_be_read(tmp_path: Path) -> None:
    worktree_directory = _worktree(tmp_path, RULE_BRANCH)
    (worktree_directory / ".git").write_bytes(b"\xff\xfe not text")
    assert not _is_step(
        tmp_path, "python3 setup/add_auto_mode_rule.py validate", worktree_directory
    )
