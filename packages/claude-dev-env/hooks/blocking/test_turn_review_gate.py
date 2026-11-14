import json
import os
import subprocess
import sys
import tempfile
import time
from io import StringIO
from pathlib import Path

import pytest

import turn_review_gate
import turn_review_snapshot
from pii_prevention_blocker_parts import repository_exemption

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
if os.environ.get("STUB_BLOCK_STATE_WRITE"):
    for each_state_file in Path(os.environ["TMPDIR"]).glob("turn-review-*.json"):
        each_state_file.unlink()
        each_state_file.mkdir()
print(json.dumps({"type": "result", "is_error": False, "result": os.environ["STUB_REVIEW_TEXT"]}))
"""


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home_directory = tmp_path / "home"
    home_directory.mkdir()
    monkeypatch.setenv("HOME", str(home_directory))
    monkeypatch.setenv("USERPROFILE", str(home_directory))
    return home_directory


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
    if os.name == "nt":
        stub_script = stub_directory / "claude_stub.py"
        stub_script.write_text(STUB_CLAUDE_SOURCE)
        (stub_directory / "claude.cmd").write_text(f'@"{sys.executable}" "{stub_script}" %*\r\n')
    else:
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


def run_hook(
    environment: dict[str, str], hook_event_name: str, prompt_text: str = "next task"
) -> dict[str, object]:
    hook_input = {
        "hook_event_name": hook_event_name,
        "session_id": SESSION_ID,
        "cwd": "/",
        "prompt": prompt_text,
    }
    completed_process = subprocess.run(
        [sys.executable, str(GATE_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    hook_output = json.loads(completed_process.stdout) if completed_process.stdout.strip() else {}
    if not hook_output:
        assert completed_process.returncode == 0, completed_process.stderr
        assert completed_process.stdout == ""
        assert completed_process.stderr == ""
        return hook_output
    assert completed_process.returncode == 2, completed_process.stderr
    assert completed_process.stderr == str(hook_output["reason"])
    return hook_output


def start_hook(environment: dict[str, str], hook_event_name: str) -> subprocess.Popen[str]:
    hook_input = {"hook_event_name": hook_event_name, "session_id": SESSION_ID, "cwd": "/"}
    running_hook = subprocess.Popen(
        [sys.executable, str(GATE_PATH)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    assert running_hook.stdin is not None
    running_hook.stdin.write(json.dumps(hook_input))
    running_hook.stdin.close()
    return running_hook


def wait_for_review_calls(environment: dict[str, str], expected_count: int) -> None:
    deadline = time.monotonic() + 20
    while len(review_calls(environment)) < expected_count:
        assert time.monotonic() < deadline, "the review never started"
        time.sleep(0.05)


def saved_state(environment: dict[str, str]) -> dict[str, object]:
    [state_file] = Path(environment["TMPDIR"]).glob("turn-review-*.json")
    return json.loads(state_file.read_text())


def age_last_wake(environment: dict[str, str], seconds: float) -> None:
    [state_file] = Path(environment["TMPDIR"]).glob("turn-review-*.json")
    state = json.loads(state_file.read_text())
    state["last_wake_at"] = state["last_wake_at"] - seconds
    state_file.write_text(json.dumps(state))


def edit_service(project: Path, round_number: int) -> None:
    (project / "app" / "src" / "service.py").write_text(
        f"def update():\n    call({round_number})\n"
    )


def turn_review_log(home_directory: Path) -> str:
    log_path = home_directory / ".claude" / "logs" / "turn-review.log"
    return log_path.read_text() if log_path.exists() else ""


def registered_turn_review_hooks(event_name: str) -> list[dict[str, object]]:
    all_events = json.loads((GATE_PATH.parent.parent / "hooks.json").read_text())["hooks"]
    return [
        each_hook
        for each_group in all_events[event_name]
        for each_hook in each_group["hooks"]
        if str(each_hook.get("command", "")).endswith("/hooks/blocking/turn_review_gate.py")
    ]


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


def test_should_log_the_block_under_the_isolated_home_folder(
    project: Path, gate_environment: dict[str, str], isolated_home: Path
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    run_hook(gate_environment, "Stop")
    all_logged_records = (isolated_home / ".claude" / "logs" / "hook-blocks.log").read_text().splitlines()
    assert [json.loads(each_line)["hook"] for each_line in all_logged_records] == ["turn_review_gate.py"]


def test_should_block_the_stop_with_the_finding_when_the_review_state_cannot_be_saved(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    stop_output = run_hook({**gate_environment, "STUB_BLOCK_STATE_WRITE": "1"}, "Stop")
    assert stop_output["decision"] == "block"
    assert FINDING_TEXT in str(stop_output["reason"])


def test_should_tell_the_agent_to_fix_a_finding_unless_the_user_asked_for_it(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    block_reason = str(run_hook(gate_environment, "Stop")["reason"])
    assert "Fix each one." in block_reason
    assert "before you end the turn" not in block_reason
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
    monkeypatch.setattr(turn_review_gate, "REVIEW_TIMEOUT_SECONDS", 4)
    all_roots = turn_review_gate._opted_in_repository_roots(
        turn_review_gate._opted_in_repository_slugs()
    )
    turn_review_gate._record_prompt_baselines(SESSION_ID, all_roots, "next task")
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


def test_should_reset_the_block_count_on_a_user_prompt_after_a_capped_stop(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    for each_round in range(3):
        edit_service(project, each_round)
        run_hook(gate_environment, "Stop")
    assert run_hook(gate_environment, "Stop") == {}
    age_last_wake(gate_environment, 60)
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop")["decision"] == "block"


def test_should_reset_the_block_count_on_a_user_prompt_after_two_wakes(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    all_decisions = []
    for each_round in range(2):
        edit_service(project, each_round)
        all_decisions.append(run_hook(gate_environment, "Stop").get("decision"))
    age_last_wake(gate_environment, 60)
    run_hook(gate_environment, "UserPromptSubmit")
    for each_round in range(2, 6):
        edit_service(project, each_round)
        all_decisions.append(run_hook(gate_environment, "Stop").get("decision"))
    assert all_decisions == ["block", "block", "block", "block", "block", None]


def test_should_keep_the_block_count_on_a_task_notification_prompt(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    for each_round in range(3):
        edit_service(project, each_round)
        run_hook(gate_environment, "Stop")
    age_last_wake(gate_environment, 60)
    run_hook(
        gate_environment,
        "UserPromptSubmit",
        "<task-notification>review done</task-notification>",
    )
    drop_retry(project)
    assert run_hook(gate_environment, "Stop") == {}
    assert len(review_calls(gate_environment)) == 3


def test_should_reset_the_block_count_on_a_stop_that_changed_nothing(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    edit_service(project, 0)
    all_decisions = [run_hook(gate_environment, "Stop").get("decision")]
    all_decisions.append(run_hook(gate_environment, "Stop").get("decision"))
    for each_round in range(1, 4):
        edit_service(project, each_round)
        all_decisions.append(run_hook(gate_environment, "Stop").get("decision"))
    assert all_decisions == ["block", None, "block", "block", "block"]


def test_should_review_the_turn_when_the_next_prompt_runs_before_its_stop(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    run_hook(gate_environment, "UserPromptSubmit")
    stop_output = run_hook(gate_environment, "Stop")
    assert stop_output["decision"] == "block"
    assert FINDING_TEXT in str(stop_output["reason"])


def test_should_take_a_new_baseline_on_the_prompt_after_a_stop_claimed_the_turn(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    run_hook(gate_environment, "Stop")
    (project / "app" / "notes.txt").write_text("the user's own edit between the turns\n")
    run_hook(gate_environment, "UserPromptSubmit")
    assert run_hook(gate_environment, "Stop") == {}
    assert len(review_calls(gate_environment)) == 1


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


def _hang_git_calls(monkeypatch: pytest.MonkeyPatch, hung_folder: Path, hung_word: str) -> None:
    original_run = subprocess.run

    def selectively_hanging_run(all_arguments: list[str], **all_keywords: object) -> object:
        if (
            all_arguments[0] == "git"
            and all_keywords.get("cwd") == str(hung_folder)
            and hung_word in all_arguments
        ):
            timeout_seconds = float(all_keywords["timeout"])
            time.sleep(timeout_seconds)
            raise subprocess.TimeoutExpired(all_arguments, timeout_seconds)
        return original_run(all_arguments, **all_keywords)

    monkeypatch.setattr(subprocess, "run", selectively_hanging_run)


def _run_gate_in_process(
    monkeypatch: pytest.MonkeyPatch, gate_environment: dict[str, str], hook_event_name: str
) -> int:
    for each_name in ("PATH", "CLAUDE_PROJECT_DIR", "CLAUDE_TURN_REVIEW_REPOSITORIES", "STUB_REVIEW_LOG", "STUB_REVIEW_TEXT"):
        monkeypatch.setenv(each_name, gate_environment[each_name])
    monkeypatch.delenv("CLAUDE_TURN_REVIEW_CHILD", raising=False)
    monkeypatch.setattr(tempfile, "tempdir", gate_environment["TMPDIR"])
    hook_input = {"hook_event_name": hook_event_name, "session_id": SESSION_ID, "cwd": "/"}
    monkeypatch.setattr(sys, "stdin", StringIO(json.dumps(hook_input)))
    return turn_review_gate.main()


def test_should_end_the_stop_inside_its_run_budget_when_git_hangs_after_a_long_review(
    project: Path, gate_environment: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    second_repository = project / "lib"
    second_repository.mkdir()
    git(second_repository, "init", "-q", "-b", "main")
    git(second_repository, "remote", "add", "origin", f"https://github.com/{REPOSITORY_SLUG}.git")
    git(second_repository, "-c", "user.name=Test", "-c", "user.email=test", "commit", "-q", "--allow-empty", "-m", "start")
    _run_gate_in_process(monkeypatch, gate_environment, "UserPromptSubmit")
    drop_retry(project)
    monkeypatch.setenv("STUB_REVIEW_SECONDS", "10")
    monkeypatch.setattr(turn_review_gate, "REVIEW_TIMEOUT_SECONDS", 2)
    monkeypatch.setattr(turn_review_gate, "STOP_RUN_BUDGET_SECONDS", 1.5, raising=False)
    monkeypatch.setattr(turn_review_snapshot, "GIT_COMMAND_TIMEOUT_SECONDS", 2)
    monkeypatch.setattr(repository_exemption, "GIT_COMMAND_TIMEOUT_SECONDS", 2)
    _hang_git_calls(monkeypatch, second_repository, "config")
    started_at = time.monotonic()

    _run_gate_in_process(monkeypatch, gate_environment, "Stop")

    assert time.monotonic() - started_at < 2.5


def test_should_end_the_prompt_inside_its_run_budget_when_git_add_hangs(
    project: Path, gate_environment: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(turn_review_gate, "PROMPT_RUN_BUDGET_SECONDS", 1.0, raising=False)
    monkeypatch.setattr(turn_review_snapshot, "GIT_COMMAND_TIMEOUT_SECONDS", 2)
    _hang_git_calls(monkeypatch, project / "app", "add")
    started_at = time.monotonic()

    assert _run_gate_in_process(monkeypatch, gate_environment, "UserPromptSubmit") == 0
    assert time.monotonic() - started_at < 1.5


def test_should_keep_counting_holds_when_each_wake_fires_a_prompt_event(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    all_decisions = []
    for each_round in range(4):
        (project / "app" / "src" / "service.py").write_text(
            f"def update():\n    call({each_round})\n"
        )
        all_decisions.append(run_hook(gate_environment, "Stop").get("decision"))
        run_hook(gate_environment, "UserPromptSubmit")
    assert all_decisions == ["block", "block", "block", None]
    assert len(review_calls(gate_environment)) == 3


def test_should_stay_capped_on_a_prompt_that_comes_right_after_the_third_hold(
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
    assert run_hook(gate_environment, "Stop") == {}
    assert len(review_calls(gate_environment)) == 3


def test_should_review_a_range_once_when_a_second_stop_comes_during_the_review(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    first_stop = start_hook({**gate_environment, "STUB_REVIEW_SECONDS": "3"}, "Stop")
    wait_for_review_calls(gate_environment, 1)
    second_stop_output = run_hook(gate_environment, "Stop")
    first_stdout, first_stderr = first_stop.communicate(timeout=30)
    assert second_stop_output == {}
    assert first_stop.returncode == 2, first_stderr
    assert json.loads(first_stdout)["decision"] == "block"
    assert len(review_calls(gate_environment)) == 1


def test_should_keep_the_baselines_a_prompt_saves_during_a_review(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    first_stop = start_hook({**gate_environment, "STUB_REVIEW_SECONDS": "3"}, "Stop")
    wait_for_review_calls(gate_environment, 1)
    (project / "app" / "notes.txt").write_text("the user's own edit before the next prompt\n")
    run_hook(gate_environment, "UserPromptSubmit")
    prompt_baselines = saved_state(gate_environment)["baselines"]
    first_stop.communicate(timeout=30)
    assert saved_state(gate_environment)["baselines"] == prompt_baselines
    assert saved_state(gate_environment)["blocks_in_a_row"] == 1


def test_should_pass_the_stop_quietly_while_another_run_holds_the_state_lock(
    project: Path, gate_environment: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    state_before = saved_state(gate_environment)
    drop_retry(project)
    monkeypatch.setattr(tempfile, "tempdir", gate_environment["TMPDIR"])
    with turn_review_gate._state_lock(SESSION_ID, turn_review_gate.STATE_LOCK_WAIT_SECONDS) as is_locked:
        assert is_locked
        assert run_hook(gate_environment, "Stop") == {}
    assert review_calls(gate_environment) == []
    assert saved_state(gate_environment) == state_before


def test_should_print_nothing_when_the_review_times_out(
    project: Path,
    gate_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    isolated_home: Path,
) -> None:
    _run_gate_in_process(monkeypatch, gate_environment, "UserPromptSubmit")
    drop_retry(project)
    monkeypatch.setenv("STUB_REVIEW_SECONDS", "5")
    monkeypatch.setattr(turn_review_gate, "REVIEW_TIMEOUT_SECONDS", 2)
    capsys.readouterr()
    assert _run_gate_in_process(monkeypatch, gate_environment, "Stop") == 0
    assert capsys.readouterr() == ("", "")
    assert "did not finish: timed out" in turn_review_log(isolated_home)


def test_should_log_a_failed_review_to_the_turn_review_log(
    project: Path, gate_environment: dict[str, str], isolated_home: Path
) -> None:
    gate_environment["STUB_REVIEW_EXIT_CODE"] = "1"
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    assert run_hook(gate_environment, "Stop") == {}
    assert "did not finish: exit 1" in turn_review_log(isolated_home)


def test_should_log_a_turn_over_the_file_limit_to_the_turn_review_log(
    project: Path, gate_environment: dict[str, str], isolated_home: Path
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    for each_index in range(31):
        (project / "app" / "src" / f"module_{each_index}.py").write_text("value = 1\n")
    assert run_hook(gate_environment, "Stop") == {}
    assert "31 files changed this turn" in turn_review_log(isolated_home)


def test_should_log_each_stop_with_its_stop_hook_active_flag(
    gate_environment: dict[str, str], isolated_home: Path
) -> None:
    hook_input = {
        "hook_event_name": "Stop",
        "session_id": SESSION_ID,
        "cwd": "/",
        "stop_hook_active": True,
    }
    subprocess.run(
        [sys.executable, str(GATE_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env=gate_environment,
        check=True,
    )
    assert "Stop stop_hook_active=True" in turn_review_log(isolated_home)


def test_should_register_the_stop_review_to_run_in_the_background() -> None:
    [stop_registration] = registered_turn_review_hooks("Stop")
    assert stop_registration["asyncRewake"] is True
    assert stop_registration["timeout"] > turn_review_gate.STOP_RUN_BUDGET_SECONDS
    assert str(stop_registration["rewakeSummary"]).strip()


def test_should_keep_the_prompt_snapshot_in_the_foreground() -> None:
    [prompt_registration] = registered_turn_review_hooks("UserPromptSubmit")
    assert "asyncRewake" not in prompt_registration
    assert "async" not in prompt_registration


def test_should_hold_a_headless_stop_through_the_decision_and_the_exit_code(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    hook_input = {"hook_event_name": "Stop", "session_id": SESSION_ID, "cwd": "/"}
    completed_process = subprocess.run(
        [sys.executable, str(GATE_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env=gate_environment,
        check=False,
    )
    assert completed_process.returncode == 2
    hold_output = json.loads(completed_process.stdout)
    assert hold_output["decision"] == "block"
    assert hold_output["reason"] == completed_process.stderr
    assert FINDING_TEXT in completed_process.stderr


def test_should_wait_for_the_state_lock_before_it_claims_the_turn(
    project: Path, gate_environment: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    monkeypatch.setattr(tempfile, "tempdir", gate_environment["TMPDIR"])
    with turn_review_gate._state_lock(SESSION_ID, turn_review_gate.STATE_LOCK_WAIT_SECONDS) as is_locked:
        assert is_locked
        running_stop = start_hook(gate_environment, "Stop")
        time.sleep(0.5)
    stop_stdout, stop_stderr = running_stop.communicate(timeout=30)
    assert running_stop.returncode == 2, stop_stderr
    assert json.loads(stop_stdout)["decision"] == "block"


def test_should_count_the_hold_when_the_lock_frees_late_after_the_review(
    project: Path, gate_environment: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    monkeypatch.setattr(tempfile, "tempdir", gate_environment["TMPDIR"])
    running_stop = start_hook({**gate_environment, "STUB_REVIEW_SECONDS": "1"}, "Stop")
    wait_for_review_calls(gate_environment, 1)
    with turn_review_gate._state_lock(SESSION_ID, turn_review_gate.STATE_LOCK_WAIT_SECONDS) as is_locked:
        assert is_locked
        time.sleep(turn_review_gate.STATE_LOCK_WAIT_SECONDS + 1.5)
    stop_stdout, stop_stderr = running_stop.communicate(timeout=30)
    assert running_stop.returncode == 2, stop_stderr
    assert json.loads(stop_stdout)["decision"] == "block"
    assert saved_state(gate_environment)["blocks_in_a_row"] == 1


def test_should_pass_the_stop_quietly_when_the_lock_stays_busy_after_the_review(
    project: Path,
    gate_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    isolated_home: Path,
) -> None:
    _run_gate_in_process(monkeypatch, gate_environment, "UserPromptSubmit")
    drop_retry(project)
    original_acquire = turn_review_gate._acquire_with_wait
    all_lock_calls: list[int] = []

    def acquire_only_the_first_time(file_descriptor: int, wait_seconds: float) -> bool:
        all_lock_calls.append(file_descriptor)
        if len(all_lock_calls) > 1:
            return False
        return original_acquire(file_descriptor, wait_seconds)

    monkeypatch.setattr(turn_review_gate, "_acquire_with_wait", acquire_only_the_first_time)
    capsys.readouterr()
    assert _run_gate_in_process(monkeypatch, gate_environment, "Stop") == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")
    assert len(all_lock_calls) == 2
    assert "Stop left the review state alone" in turn_review_log(isolated_home)


def test_should_review_both_turns_when_two_prompts_in_a_row_beat_their_stops(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    edit_service(project, 0)
    run_hook(gate_environment, "UserPromptSubmit")
    assert run_hook(gate_environment, "Stop")["decision"] == "block"
    edit_service(project, 1)
    run_hook(gate_environment, "UserPromptSubmit")
    assert run_hook(gate_environment, "Stop")["decision"] == "block"
    assert len(review_calls(gate_environment)) == 2


def test_should_close_the_turn_on_a_stop_long_after_the_prompt_that_found_it_open(
    project: Path, gate_environment: dict[str, str]
) -> None:
    run_hook(gate_environment, "UserPromptSubmit")
    drop_retry(project)
    run_hook(gate_environment, "UserPromptSubmit")
    [state_file] = Path(gate_environment["TMPDIR"]).glob("turn-review-*.json")
    state = json.loads(state_file.read_text())
    state["open_turn_prompt_at"] = state["open_turn_prompt_at"] - 60
    state_file.write_text(json.dumps(state))
    run_hook(gate_environment, "Stop")
    (project / "app" / "notes.txt").write_text("the user's own edit between the turns\n")
    run_hook(gate_environment, "UserPromptSubmit")
    assert run_hook(gate_environment, "Stop") == {}
    assert len(review_calls(gate_environment)) == 1
