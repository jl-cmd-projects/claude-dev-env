import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import turn_review_gate

GATE_PATH = Path(turn_review_gate.__file__)
SESSION_ID = "turn-review-session"
REPOSITORY_SLUG = "owner/app"
FINDING_TEXT = "src/service.py:3 - The diff drops the retry, so one failed call loses the update."
STUB_CLAUDE_SOURCE = """#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

log_path = Path(os.environ["STUB_REVIEW_LOG"])
calls = json.loads(log_path.read_text()) if log_path.exists() else []
calls.append({"argv": sys.argv[1:], "cwd": os.getcwd(), "environment": dict(os.environ)})
log_path.write_text(json.dumps(calls))
exit_code = int(os.environ.get("STUB_REVIEW_EXIT_CODE", "0"))
if exit_code:
    sys.exit(exit_code)
time.sleep(float(os.environ.get("STUB_REVIEW_SECONDS", "0")))
print(json.dumps({"type": "result", "is_error": False, "result": os.environ["STUB_REVIEW_TEXT"]}))
"""


def git(repository: Path, *all_arguments: str) -> str:
    return subprocess.run(
        ["git", *all_arguments], cwd=repository, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    project_directory = tmp_path / "workspace"
    repository = project_directory / "app"
    (repository / "src").mkdir(parents=True)
    git(repository, "init", "-q", "-b", "main")
    git(repository, "config", "user.email", "test@example.com")
    git(repository, "config", "user.name", "Test")
    git(repository, "remote", "add", "origin", f"https://github.com/{REPOSITORY_SLUG}.git")
    (repository / "src" / "service.py").write_text("@with_retry\ndef update():\n    call()\n")
    git(repository, "add", "-A")
    git(repository, "commit", "-q", "-m", "start")
    return project_directory


@pytest.fixture
def gate_environment(tmp_path: Path, project: Path) -> dict[str, str]:
    stub_directory = tmp_path / "bin"
    stub_directory.mkdir()
    stub_claude = stub_directory / "claude"
    stub_claude.write_text(STUB_CLAUDE_SOURCE)
    stub_claude.chmod(0o755)
    state_directory = tmp_path / "state"
    state_directory.mkdir()
    environment = {
        each_name: each_value
        for each_name, each_value in os.environ.items()
        if not each_name.startswith(("CLAUDE", "GIT_"))
    }
    environment.update(
        {
            "PATH": f"{stub_directory}{os.pathsep}{os.environ['PATH']}",
            "TMPDIR": str(state_directory),
            "CLAUDE_PROJECT_DIR": str(project),
            "CLAUDE_TURN_REVIEW_REPOSITORIES": f"other/repo, {REPOSITORY_SLUG.upper()}",
            "STUB_REVIEW_LOG": str(tmp_path / "review-calls.json"),
            "STUB_REVIEW_TEXT": FINDING_TEXT,
            "CLAUDE_CODE_SESSION_ID": "parent-session",
            "CLAUDE_CODE_REMOTE_SESSION_ID": "parent-remote-session",
        }
    )
    return environment


def run_hook(environment: dict[str, str], hook_event_name: str) -> dict[str, object]:
    hook_input = {"hook_event_name": hook_event_name, "session_id": SESSION_ID, "cwd": "/"}
    completed_process = subprocess.run(
        [sys.executable, str(GATE_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env=environment,
        check=True,
    )
    return json.loads(completed_process.stdout) if completed_process.stdout.strip() else {}


def review_calls(environment: dict[str, str]) -> list[dict[str, object]]:
    log_path = Path(environment["STUB_REVIEW_LOG"])
    return json.loads(log_path.read_text()) if log_path.exists() else []


def drop_retry(project: Path) -> None:
    (project / "app" / "src" / "service.py").write_text("def update():\n    call()\n")


def test_should_block_the_stop_with_the_finding_when_the_turn_leaves_a_bug(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    stop_output = run_hook(gate_environment, "Stop")
    assert stop_output["decision"] == "block"
    assert FINDING_TEXT in str(stop_output["reason"])
    assert "app" in str(stop_output["reason"])


def test_should_tell_the_agent_to_fix_a_finding_unless_the_user_asked_for_it(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    block_reason = str(run_hook(gate_environment, "Stop")["reason"])
    assert "Fix each one before you end the turn." in block_reason
    assert "is not a request for the problem it causes" in block_reason
    assert "quote those words in your reply" in block_reason


def test_should_review_only_the_edits_made_after_the_prompt(
    project: Path, gate_environment: dict[str, str]
) -> None:
    repository = project / "app"
    (repository / "notes.txt").write_text("work the user left before the prompt\n")
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    run_hook(gate_environment, "Stop")
    [review_call] = review_calls(gate_environment)
    prompt_text = review_call["argv"][review_call["argv"].index("-p") + 1]
    assert prompt_text.startswith("/code-review low ")
    turn_range = prompt_text.split()[-1]
    base_commit, turn_commit = turn_range.split("..")
    assert git(repository, "diff", "--name-only", base_commit, turn_commit) == "src/service.py"
    assert git(repository, "rev-parse", f"{turn_commit}^") == base_commit
    assert Path(str(review_call["cwd"])).resolve() == repository.resolve()


def test_should_run_the_review_outside_the_parent_session(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    run_hook(gate_environment, "Stop")
    [review_call] = review_calls(gate_environment)
    review_environment = review_call["environment"]
    assert "CLAUDE_CODE_SESSION_ID" not in review_environment
    assert "CLAUDE_CODE_REMOTE_SESSION_ID" not in review_environment
    assert review_environment["CLAUDE_TURN_REVIEW_CHILD"] == "1"
    assert "--permission-mode" in review_call["argv"]
    assert review_call["argv"][review_call["argv"].index("--permission-mode") + 1] == "dontAsk"
    assert "Bash(git diff:*)" in review_call["argv"]
    assert not any("git -C" in each_argument for each_argument in review_call["argv"])
    denied_rules = review_call["argv"][review_call["argv"].index("--disallowedTools") + 1 :]
    assert "Bash(git * -c *)" in denied_rules
    assert "Bash(git *--output*)" in denied_rules
    settings_text = review_call["argv"][review_call["argv"].index("--settings") + 1]
    assert json.loads(settings_text) == {"disableAllHooks": True}
    argv = review_call["argv"]
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--tools") + 1] == "Read,Grep,Glob,Bash"
    assert "--no-session-persistence" in argv
    assert "Agent" not in argv


def test_should_ignore_a_saved_baseline_that_is_not_a_commit_name(
    tmp_path: Path, project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    [state_file] = (tmp_path / "state").glob("turn-review-*.json")
    saved_state = json.loads(state_file.read_text())
    planted_output = tmp_path / "planted.txt"
    saved_state["baselines"] = {
        each_root: f"--output={planted_output}" for each_root in saved_state["baselines"]
    }
    state_file.write_text(json.dumps(saved_state))
    drop_retry(project)
    run_hook(gate_environment, "Stop")
    assert not planted_output.exists()
    assert review_calls(gate_environment) == []


def test_should_ignore_a_saved_baseline_that_names_a_revision_expression(
    tmp_path: Path, project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    [state_file] = (tmp_path / "state").glob("turn-review-*.json")
    saved_state = json.loads(state_file.read_text())
    saved_state["baselines"] = {each_root: "HEAD" for each_root in saved_state["baselines"]}
    state_file.write_text(json.dumps(saved_state))
    drop_retry(project)
    run_hook(gate_environment, "Stop")
    assert review_calls(gate_environment) == []


def test_should_read_the_json_findings_after_an_empty_list_in_the_prose(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["STUB_REVIEW_TEXT"] = (
        "load() now returns `[]` on error.\n"
        '```json\n[{"file": "src/service.py", "line": 1, "summary": "The retry is gone."}]\n```'
    )
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop")["decision"] == "block"


def test_should_keep_a_json_finding_whose_summary_holds_an_empty_list(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["STUB_REVIEW_TEXT"] = (
        '[{"file": "src/service.py", "line": 1, "summary": "load() now returns [] on error."}]'
    )
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop")["decision"] == "block"


def test_should_keep_the_json_findings_before_an_empty_list_in_the_prose(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["STUB_REVIEW_TEXT"] = (
        '```json\n[{"file": "src/service.py", "line": 1, "summary": "The retry is gone."}]\n```\n'
        "Callers that pass `[]` are unaffected."
    )
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop")["decision"] == "block"


def test_should_skip_a_project_folder_it_cannot_read(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / "locked").mkdir()
    original_exists = Path.exists

    def exists_or_denied(self: Path, *all_arguments: object, **all_options: object) -> bool:
        if self.parent.name == "locked":
            raise PermissionError(13, "Permission denied", str(self))
        return original_exists(self, *all_arguments, **all_options)

    monkeypatch.setattr(Path, "exists", exists_or_denied)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    all_roots = turn_review_gate._opted_in_repository_roots(frozenset({REPOSITORY_SLUG}))
    assert all_roots == [(project / "app").resolve()]


def test_should_read_a_text_finding_beside_an_inline_empty_list(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["STUB_REVIEW_TEXT"] = (
        "src/service.py:1 resets the cache to `[]` before the retry."
    )
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop")["decision"] == "block"


def test_should_allow_the_stop_without_a_review_when_the_turn_changed_nothing(
    gate_environment: dict[str, str],
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    assert run_hook(gate_environment, "Stop") == {}
    assert review_calls(gate_environment) == []


def test_should_allow_the_stop_when_the_review_finds_nothing(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["STUB_REVIEW_TEXT"] = (
        "(none)\n\nThe diff only changes one line in `src/service.py:1`."
    )
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop") == {}
    assert len(review_calls(gate_environment)) == 1


def test_should_block_on_a_finding_the_review_reports_as_json(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["STUB_REVIEW_TEXT"] = (
        '```json\n[{"file": "src/service.py", "line": 1, '
        '"summary": "The retry is gone."}]\n```'
    )
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    stop_output = run_hook(gate_environment, "Stop")
    assert stop_output["decision"] == "block"
    assert "src/service.py:1 The retry is gone." in str(stop_output["reason"])


def test_should_read_the_json_findings_after_a_bracket_in_the_prose(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["STUB_REVIEW_TEXT"] = (
        "See [service](src/service.py#L1).\n"
        '```json\n[{"file": "src/service.py", "line": 1, "summary": "The retry is gone."}]\n```'
    )
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop")["decision"] == "block"


def test_should_allow_the_stop_when_the_json_findings_are_empty(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["STUB_REVIEW_TEXT"] = "Checked src/service.py:1 and kept it.\n```json\n[]\n```"
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop") == {}


def test_should_allow_the_stop_when_the_finding_names_a_longer_path(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["STUB_REVIEW_TEXT"] = "vendor/src/service.py:3 - An unchanged copy has a bug."
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop") == {}


def test_should_block_on_a_text_finding_before_an_empty_json_list(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["STUB_REVIEW_TEXT"] = "src/service.py:1 The retry is gone.\n```json\n[]\n```"
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert "src/service.py:1 The retry is gone." in str(
        run_hook(gate_environment, "Stop")["reason"]
    )


def test_should_allow_the_stop_when_a_clean_review_cites_a_changed_line_in_prose(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["STUB_REVIEW_TEXT"] = "I checked src/service.py:1 and found no problems."
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop") == {}


def test_should_block_on_a_listed_finding_that_opens_with_the_changed_path(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["STUB_REVIEW_TEXT"] = (
        "I found one problem.\n\n- `src/service.py:1` - The retry is gone."
    )
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert "`src/service.py:1` - The retry is gone." in str(
        run_hook(gate_environment, "Stop")["reason"]
    )


def test_should_share_one_review_time_budget_across_the_checkouts(
    project: Path, gate_environment: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    second_repository = project / "lib"
    second_repository.mkdir()
    git(second_repository, "init", "-q", "-b", "main")
    git(second_repository, "remote", "add", "origin", f"https://github.com/{REPOSITORY_SLUG}.git")
    git(second_repository, "-c", "user.name=Test", "-c", "user.email=test", "commit", "-q", "--allow-empty", "-m", "start")
    for each_name in ("PATH", "CLAUDE_PROJECT_DIR", "CLAUDE_TURN_REVIEW_REPOSITORIES", "STUB_REVIEW_LOG", "STUB_REVIEW_TEXT"):
        monkeypatch.setenv(each_name, gate_environment[each_name])
    monkeypatch.setenv("STUB_REVIEW_SECONDS", "5")
    monkeypatch.setattr(tempfile, "tempdir", gate_environment["TMPDIR"])
    monkeypatch.setattr(turn_review_gate, "REVIEW_TIMEOUT_SECONDS", 2)
    all_roots = turn_review_gate._opted_in_repository_roots(
        turn_review_gate._opted_in_repository_slugs()
    )
    turn_review_gate._record_prompt_baselines(SESSION_ID, all_roots)
    drop_retry(project)
    (second_repository / "notes.txt").write_text("new\n")
    turn_review_gate._turn_block_reason(SESSION_ID, all_roots)
    assert [each_call["cwd"] for each_call in review_calls(gate_environment)] == [
        str(project / "app")
    ]


def test_should_review_only_the_fix_on_the_stop_after_a_block(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    run_hook(gate_environment, "Stop")
    assert run_hook(gate_environment, "Stop") == {}
    assert len(review_calls(gate_environment)) == 1


def test_should_stop_blocking_after_three_blocks_in_a_row(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    all_decisions = []
    for each_round in range(4):
        (project / "app" / "src" / "service.py").write_text(
            f"def update():\n    call({each_round})\n"
        )
        all_decisions.append(run_hook(gate_environment, "Stop").get("decision"))
    assert all_decisions == ["block", "block", "block", None]
    assert len(review_calls(gate_environment)) == 3


def test_should_reset_the_block_count_on_a_new_prompt(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    for each_round in range(3):
        (project / "app" / "src" / "service.py").write_text(
            f"def update():\n    call({each_round})\n"
        )
        run_hook(gate_environment, "Stop")
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop")["decision"] == "block"


def test_should_skip_a_turn_that_changed_more_than_thirty_files(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    for each_index in range(31):
        (project / "app" / "src" / f"module_{each_index}.py").write_text("value = 1\n")
    assert run_hook(gate_environment, "Stop") == {}
    assert review_calls(gate_environment) == []


def test_should_leave_a_repository_the_environment_does_not_list(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["CLAUDE_TURN_REVIEW_REPOSITORIES"] = "other/repo"
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop") == {}
    assert review_calls(gate_environment) == []


def test_should_do_nothing_inside_a_review_run(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["CLAUDE_TURN_REVIEW_CHILD"] = "1"
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop") == {}
    assert review_calls(gate_environment) == []


def test_should_allow_the_stop_when_the_review_command_fails(
    project: Path, gate_environment: dict[str, str]
) -> None:
    gate_environment["STUB_REVIEW_EXIT_CODE"] = "1"
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop") == {}
    assert len(review_calls(gate_environment)) == 1


def test_should_start_the_turn_on_the_first_stop_without_a_prompt_snapshot(
    project: Path, gate_environment: dict[str, str]
) -> None:
    drop_retry(project)
    assert run_hook(gate_environment, "Stop") == {}
    (project / "app" / "src" / "service.py").write_text("def update():\n    call(1)\n")
    assert run_hook(gate_environment, "Stop")["decision"] == "block"
