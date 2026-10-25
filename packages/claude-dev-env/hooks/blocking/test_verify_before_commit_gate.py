"""Behavior tests for the verify-before-commit PreToolUse gate."""

import json
import subprocess
import sys
from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path
from unittest.mock import patch

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import verify_before_commit_gate as gate
from hooks_constants.verify_before_commit_gate_constants import DENY_REASON

PROMPT_ENTRY = {"type": "user", "message": {"content": "Fix the parser and commit it."}}
SLASH_PROMPT_ENTRY = {
    "type": "user",
    "message": {
        "content": "<command-message>verify</command-message>\n<command-name>/verify</command-name>"
    },
}
SKILL_BODY_ENTRY = {
    "type": "user",
    "isMeta": True,
    "message": {
        "content": [{"type": "text", "text": "Base directory for this skill: verify"}]
    },
}
TOOL_RESULT_ENTRY = {
    "type": "user",
    "message": {
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_1",
                "content": "Launching skill: verify",
            }
        ]
    },
}

REFUSED_TOOL_RESULT_ENTRY = {
    "type": "user",
    "message": {
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_1",
                "content": "<tool_use_error>Skill verify cannot be used with Skill tool</tool_use_error>",
                "is_error": True,
            }
        ]
    },
}


def _skill_entry(skill_name: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "Skill",
                    "input": {"skill": skill_name},
                }
            ]
        },
    }


def _git(repository: Path, *all_arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repository), *all_arguments], check=True, capture_output=True
    )


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    _git(repository_root, "init", "-q")
    _git(repository_root, "config", "user.email", "gate@example.com")
    _git(repository_root, "config", "user.name", "Gate Test")
    (repository_root / ".agents" / "skills" / "verify").mkdir(parents=True)
    (repository_root / ".agents" / "skills" / "verify" / "SKILL.md").write_text(
        "verify\n", encoding="utf-8"
    )
    (repository_root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repository_root / "README.md").write_text("Readme\n", encoding="utf-8")
    _git(repository_root, "add", "-A")
    _git(repository_root, "commit", "-q", "-m", "base")
    return repository_root


def _transcript(tmp_path: Path, *all_entries: dict[str, object]) -> Path:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(
        "".join(json.dumps(each_entry) + "\n" for each_entry in all_entries),
        encoding="utf-8",
    )
    return transcript_path


def _payload(
    command: str, cwd: Path, transcript_path: Path, tool_name: str = "Bash"
) -> dict[str, object]:
    return {
        "tool_name": tool_name,
        "tool_input": {"command": command},
        "cwd": str(cwd),
        "transcript_path": str(transcript_path),
    }


def _unverified(tmp_path: Path) -> Path:
    return _transcript(tmp_path, PROMPT_ENTRY)


def _is_denied(payload: dict[str, object]) -> bool:
    decision = gate.decision_for(payload)
    if decision is None:
        return False
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert decision["hookSpecificOutput"]["permissionDecisionReason"] == DENY_REASON
    return True


def _run_main(payload: dict[str, object]) -> tuple[int, str]:
    output = StringIO()
    input_stream = TextIOWrapper(
        BytesIO(json.dumps(payload).encode("utf-8")), encoding="utf-8"
    )
    with patch("sys.stdin", input_stream), patch("sys.stdout", output):
        exit_code = gate.main()
    return exit_code, output.getvalue()


def test_staged_code_commit_without_verify_is_denied(
    repository: Path, tmp_path: Path
) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repository, "add", "app.py")
    exit_code, output = _run_main(
        _payload("git commit -m change", repository, _unverified(tmp_path))
    )
    assert exit_code == 0
    decision = json.loads(output)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "verify" in decision["permissionDecisionReason"]


def test_same_command_git_add_of_code_is_denied_with_an_empty_index(
    repository: Path, tmp_path: Path
) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert _is_denied(
        _payload(
            "git add app.py && git commit -m change", repository, _unverified(tmp_path)
        )
    )


def test_same_command_git_add_all_picks_up_a_new_code_file(
    repository: Path, tmp_path: Path
) -> None:
    (repository / "new_module.py").write_text("NAME = 'new'\n", encoding="utf-8")
    assert _is_denied(
        _payload("git add -A; git commit -m add", repository, _unverified(tmp_path))
    )


def test_same_command_git_add_of_docs_passes_while_code_stays_unstaged(
    repository: Path, tmp_path: Path
) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    (repository / "README.md").write_text("Readme two\n", encoding="utf-8")
    assert not _is_denied(
        _payload(
            "git add README.md; git commit -m docs", repository, _unverified(tmp_path)
        )
    )


def test_commit_all_flag_counts_modified_code(repository: Path, tmp_path: Path) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert _is_denied(
        _payload("git commit -am change", repository, _unverified(tmp_path))
    )
    assert _is_denied(
        _payload("git commit --all -m change", repository, _unverified(tmp_path))
    )


def test_commit_all_flag_with_only_docs_modified_passes(
    repository: Path, tmp_path: Path
) -> None:
    (repository / "README.md").write_text("Readme two\n", encoding="utf-8")
    assert not _is_denied(
        _payload("git commit -am docs", repository, _unverified(tmp_path))
    )


def test_docs_only_commit_passes(repository: Path, tmp_path: Path) -> None:
    (repository / "README.md").write_text("Readme two\n", encoding="utf-8")
    (repository / "docs").mkdir()
    (repository / "docs" / "guide.md").write_text("Guide\n", encoding="utf-8")
    _git(repository, "add", "-A")
    assert not _is_denied(
        _payload("git commit -m docs", repository, _unverified(tmp_path))
    )


def test_data_files_under_docs_folder_pass(repository: Path, tmp_path: Path) -> None:
    (repository / "docs" / "records").mkdir(parents=True)
    (repository / "docs" / "records" / "proof.json").write_text("{}\n", encoding="utf-8")
    (repository / "docs" / "ruleset.yaml").write_text("rules: []\n", encoding="utf-8")
    _git(repository, "add", "-A")
    assert not _is_denied(
        _payload("git commit -m records", repository, _unverified(tmp_path))
    )


def test_code_under_docs_folder_is_denied(repository: Path, tmp_path: Path) -> None:
    (repository / "docs").mkdir()
    (repository / "docs" / "conf.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repository, "add", "-A")
    assert _is_denied(
        _payload("git commit -m conf", repository, _unverified(tmp_path))
    )


def test_json_outside_docs_folder_is_denied(repository: Path, tmp_path: Path) -> None:
    (repository / "config.json").write_text("{}\n", encoding="utf-8")
    _git(repository, "add", "-A")
    assert _is_denied(
        _payload("git commit -m config", repository, _unverified(tmp_path))
    )


def test_tests_only_commit_passes(repository: Path, tmp_path: Path) -> None:
    (repository / "test_app.py").write_text(
        "def test_value() -> None:\n    pass\n", encoding="utf-8"
    )
    (repository / "tests").mkdir()
    (repository / "tests" / "helpers.py").write_text("HELPER = 1\n", encoding="utf-8")
    (repository / "install.test.mjs").write_text("export {};\n", encoding="utf-8")
    _git(repository, "add", "-A")
    assert not _is_denied(
        _payload("git commit -m tests", repository, _unverified(tmp_path))
    )


def test_docs_plus_code_commit_is_denied(repository: Path, tmp_path: Path) -> None:
    (repository / "README.md").write_text("Readme two\n", encoding="utf-8")
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repository, "add", "-A")
    assert _is_denied(
        _payload("git commit -m mixed", repository, _unverified(tmp_path))
    )


def test_refused_verify_skill_call_is_denied(repository: Path, tmp_path: Path) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repository, "add", "app.py")
    transcript_path = _transcript(
        tmp_path, PROMPT_ENTRY, _skill_entry("verify"), REFUSED_TOOL_RESULT_ENTRY
    )
    assert _is_denied(_payload("git commit -m change", repository, transcript_path))


def test_verify_skill_call_after_the_last_prompt_passes(
    repository: Path, tmp_path: Path
) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repository, "add", "app.py")
    for each_name in ("verify", "plugin:verify"):
        transcript_path = _transcript(
            tmp_path,
            PROMPT_ENTRY,
            _skill_entry(each_name),
            TOOL_RESULT_ENTRY,
            SKILL_BODY_ENTRY,
        )
        assert not _is_denied(
            _payload("git commit -m change", repository, transcript_path)
        )


def test_verify_slash_command_in_the_last_prompt_passes(
    repository: Path, tmp_path: Path
) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repository, "add", "app.py")
    transcript_path = _transcript(
        tmp_path, PROMPT_ENTRY, SLASH_PROMPT_ENTRY, SKILL_BODY_ENTRY
    )
    exit_code, output = _run_main(
        _payload("git commit -m change", repository, transcript_path)
    )
    assert (exit_code, output) == (0, "")


def test_verify_loaded_in_a_previous_turn_does_not_count(
    repository: Path, tmp_path: Path
) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repository, "add", "app.py")
    transcript_path = _transcript(
        tmp_path, PROMPT_ENTRY, _skill_entry("verify"), SKILL_BODY_ENTRY, PROMPT_ENTRY
    )
    assert _is_denied(_payload("git commit -m change", repository, transcript_path))


def test_another_skill_does_not_count(repository: Path, tmp_path: Path) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repository, "add", "app.py")
    transcript_path = _transcript(tmp_path, PROMPT_ENTRY, _skill_entry("verify-rdp"))
    assert _is_denied(_payload("git commit -m change", repository, transcript_path))


def test_repository_without_a_verify_skill_passes(
    repository: Path, tmp_path: Path
) -> None:
    _git(repository, "rm", "-q", "-r", ".agents")
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repository, "add", "-A")
    assert not _is_denied(
        _payload("git commit -m change", repository, _unverified(tmp_path))
    )


def test_claude_skills_verify_directory_activates_the_gate(
    repository: Path, tmp_path: Path
) -> None:
    _git(repository, "rm", "-q", "-r", ".agents")
    (repository / ".claude" / "skills" / "verify").mkdir(parents=True)
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert _is_denied(
        _payload(
            "git add app.py; git commit -m change", repository, _unverified(tmp_path)
        )
    )


def test_powershell_and_git_directory_option_reach_the_repository(
    repository: Path, tmp_path: Path
) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    command = (
        f'git -C "{repository}" add app.py; git -C "{repository}" commit -m change'
    )
    assert _is_denied(
        _payload(command, tmp_path, _unverified(tmp_path), tool_name="PowerShell")
    )


@pytest.mark.parametrize(
    "command",
    [
        "git commit app.py -m change",
        "git commit -m change -- app.py",
        "git commit -am README.md app.py",
        "git commit --only app.py --message change",
    ],
)
def test_should_deny_a_pathspec_commit_of_unstaged_code(
    repository: Path, tmp_path: Path, command: str
) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert _is_denied(_payload(command, repository, _unverified(tmp_path)))


def test_should_pass_a_docs_pathspec_commit_while_code_stays_staged(
    repository: Path, tmp_path: Path
) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repository, "add", "app.py")
    (repository / "README.md").write_text("Readme two\n", encoding="utf-8")
    assert not _is_denied(
        _payload("git commit -m docs README.md", repository, _unverified(tmp_path))
    )


def test_should_read_a_message_value_as_text_and_not_as_a_pathspec(
    repository: Path, tmp_path: Path
) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    (repository / "README.md").write_text("Readme two\n", encoding="utf-8")
    assert not _is_denied(
        _payload(
            "git commit -m app.py README.md", repository, _unverified(tmp_path)
        )
    )


@pytest.mark.parametrize(
    ("command_template", "tool_name"),
    [
        ('cd "{repository}" && git add app.py && git commit -m change', "Bash"),
        ('cd "{repository}"; git commit -am change', "Bash"),
        ('Set-Location -Path "{repository}"; git commit -am change', "PowerShell"),
    ],
)
def test_should_check_the_repository_a_cd_moves_into(
    repository: Path, tmp_path: Path, command_template: str, tool_name: str
) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    command = command_template.format(repository=repository)
    assert _is_denied(
        _payload(command, tmp_path, _unverified(tmp_path), tool_name=tool_name)
    )


def test_should_keep_the_directory_when_a_cd_target_is_a_variable(
    repository: Path, tmp_path: Path
) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert _is_denied(
        _payload(
            'cd "$WORK"; git commit -am change', repository, _unverified(tmp_path)
        )
    )


def test_should_pass_a_cd_into_a_repository_without_a_verify_skill(
    repository: Path, tmp_path: Path
) -> None:
    other_repository = tmp_path / "other"
    other_repository.mkdir()
    _git(other_repository, "init", "-q")
    (other_repository / "tool.py").write_text("NAME = 1\n", encoding="utf-8")
    command = f'cd "{other_repository}" && git add tool.py && git commit -m add'
    assert not _is_denied(_payload(command, repository, _unverified(tmp_path)))


def test_commands_other_than_commit_pass(repository: Path, tmp_path: Path) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repository, "add", "app.py")
    for each_command in ("git status", "git push origin HEAD", "echo git commit"):
        assert not _is_denied(_payload(each_command, repository, _unverified(tmp_path)))
    assert (
        gate.decision_for(
            {"tool_name": "Write", "tool_input": {"command": "git commit"}}
        )
        is None
    )


def test_unreadable_transcript_passes(repository: Path, tmp_path: Path) -> None:
    (repository / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repository, "add", "app.py")
    assert not _is_denied(
        _payload("git commit -m change", repository, tmp_path / "missing.jsonl")
    )


def test_directory_outside_a_repository_passes(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    assert not _is_denied(
        _payload("git commit -m change", outside, _unverified(tmp_path))
    )
