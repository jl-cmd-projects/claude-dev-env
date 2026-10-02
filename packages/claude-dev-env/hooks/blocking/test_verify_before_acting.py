import io
import json
import re
from pathlib import Path

import pytest

import verify_before_acting

ACTING_MESSAGE_ID = "msg_acting"
EARLIER_MESSAGE_ID = "msg_earlier"
TOOL_USE_ID = "toolu_target"
HEDGED_SENTENCE = "The config probably lives in settings.json."
CLEAN_SENTENCE = "The config lives in settings.json, as the read above showed."
LOG_RELATIVE_PATH = Path(".claude") / "logs" / "verify-before-acting.jsonl"
WRITE_INPUT = {"file_path": "settings.json", "content": "{}"}


def thinking_record(message_id: str, thinking_text: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "id": message_id,
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": thinking_text, "signature": "sig"}],
        },
    }


def tool_use_record(
    message_id: str, tool_use_id: str, tool_name: str, tool_input: dict[str, object]
) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "id": message_id,
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": tool_use_id, "name": tool_name, "input": tool_input}
            ],
        },
    }


def tool_result_record(tool_use_id: str) -> dict[str, object]:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": "ok"}],
        },
    }


def write_transcript(directory: Path, all_lines: list[object]) -> Path:
    transcript_path = directory / "transcript.jsonl"
    all_texts = [
        each_line if isinstance(each_line, str) else json.dumps(each_line)
        for each_line in all_lines
    ]
    transcript_path.write_text("\n".join(all_texts) + "\n", encoding="utf-8")
    return transcript_path


def acting_transcript(
    directory: Path, thinking_text: str, tool_name: str, tool_input: dict[str, object]
) -> Path:
    return write_transcript(
        directory,
        [
            thinking_record(ACTING_MESSAGE_ID, thinking_text),
            tool_use_record(ACTING_MESSAGE_ID, TOOL_USE_ID, tool_name, tool_input),
        ],
    )


def run_hook(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool_name: str,
    tool_input: dict[str, object],
    transcript_path: Path,
) -> tuple[int, str]:
    hook_input = {
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_use_id": TOOL_USE_ID,
        "transcript_path": str(transcript_path),
    }
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = verify_before_acting.main()
    return exit_code, capsys.readouterr().out


def logged_outcomes(home_directory: Path) -> list[str]:
    log_path = home_directory / LOG_RELATIVE_PATH
    if not log_path.exists():
        return []
    all_records = [
        json.loads(each_line)
        for each_line in log_path.read_text(encoding="utf-8").splitlines()
        if each_line
    ]
    return [each_record["outcome"] for each_record in all_records]


def expected_block(tool_name: str, quoted_sentence: str) -> dict[str, object]:
    return {
        "decision": "block",
        "reason": (
            f'The reasoning behind this {tool_name} call hedges: "{quoted_sentence}" '
            "Check that claim now with a read-only tool, then continue. "
            "If the check contradicts it, undo this change first."
        ),
        "hookSpecificOutput": {"hookEventName": "PostToolUse"},
    }


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_should_block_a_write_after_hedged_reasoning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = acting_transcript(
        tmp_path, f"I need the config.\n{HEDGED_SENTENCE} Writing it now.", "Write", WRITE_INPUT
    )
    exit_code, stdout_text = run_hook(monkeypatch, capsys, "Write", WRITE_INPUT, transcript_path)
    assert exit_code == 0
    assert json.loads(stdout_text) == expected_block("Write", HEDGED_SENTENCE)
    assert logged_outcomes(tmp_path) == ["blocked"]


def test_should_log_the_quoted_hedge_sentence_on_a_block(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = acting_transcript(tmp_path, HEDGED_SENTENCE, "Write", WRITE_INPUT)
    run_hook(monkeypatch, capsys, "Write", WRITE_INPUT, transcript_path)
    log_line = (tmp_path / LOG_RELATIVE_PATH).read_text(encoding="utf-8").splitlines()[0]
    log_record = json.loads(log_line)
    assert log_record["tool_name"] == "Write"
    assert log_record["tool_use_id"] == TOOL_USE_ID
    assert log_record["hedge_sentence"] == HEDGED_SENTENCE
    assert log_record["timestamp"]


def test_should_allow_a_write_after_clean_reasoning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = acting_transcript(tmp_path, CLEAN_SENTENCE, "Write", WRITE_INPUT)
    exit_code, stdout_text = run_hook(monkeypatch, capsys, "Write", WRITE_INPUT, transcript_path)
    assert (exit_code, stdout_text) == (0, "")
    assert logged_outcomes(tmp_path) == ["allowed_clean"]


@pytest.mark.parametrize(
    ("tool_name", "command"),
    [
        ("Bash", "gh pr view 12 --json state"),
        ("PowerShell", "Get-Content settings.json"),
        ("PowerShell", "Test-Path settings.json"),
        ("Bash", "gh api repos/o/r/pulls/12"),
        ("Bash", "git status 2>&1"),
        ("Bash", "git log --oneline > /dev/null"),
        ("Bash", "cat notes.txt"),
        ("Bash", "cat touch.txt"),
        ("Bash", "ls -la"),
        ("Bash", "ls mkdir_notes"),
        ("Bash", "grep -rn rm src"),
        ("Bash", 'grep -n "cp " notes.md'),
        ("Bash", "git status"),
        ("Bash", "git diff"),
        ("Bash", "git diff -- cp.py"),
        ("Bash", "gh pr view 12"),
        ("Bash", "sed -n 1,5p notes.txt"),
        ("Bash", "sed --silent 1p notes.txt"),
        ("Bash", "git log --oneline -- rm.py"),
        ("Bash", "python pull_request.py --help"),
        ("Bash", "awk '$1 > 5' notes.txt"),
        ("Bash", "jq '.count > 3' data.json"),
        ("Bash", "gh pr list --json number --jq 'map(select(.number > 5))'"),
        ("Bash", 'python -c "print(1 > 0)"'),
        ("Bash", "grep -c '>' notes.txt"),
        ("Bash", "git log --format='%h > %s'"),
        ("Bash", "gh api -X GET search/issues -f q=repo:o/r"),
        ("Bash", "gh api --method GET repos/o/r/pulls -f state=open"),
        ("Bash", "git --no-pager log"),
        ("Bash", "git --git-dir=/repo/.git log --oneline"),
        ("Bash", "git -C /repo stash list"),
        ("Bash", "git -c core.pager=cat diff"),
        ("Bash", 'pwsh -NoProfile -Command "git status"'),
        ("PowerShell", "Get-Content x.txt > $null"),
    ],
)
def test_should_pass_a_read_only_command_untouched(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    tool_name: str,
    command: str,
) -> None:
    tool_input = {"command": command}
    transcript_path = acting_transcript(tmp_path, HEDGED_SENTENCE, tool_name, tool_input)
    exit_code, stdout_text = run_hook(monkeypatch, capsys, tool_name, tool_input, transcript_path)
    assert (exit_code, stdout_text) == (0, "")
    assert not (tmp_path / LOG_RELATIVE_PATH).exists()


@pytest.mark.parametrize(
    ("tool_name", "command"),
    [
        ("Bash", "git push origin feat/x"),
        ("Bash", 'git -C "C:/repo dir" commit -F message.txt'),
        ("Bash", "gh pr merge 12 --squash"),
        ("Bash", "gh issue comment 4 --body-file body.md"),
        ("Bash", "gh api repos/o/r/issues/4/comments -X POST"),
        ("Bash", "gh api repos/o/r/pulls/12 --method PATCH"),
        ("Bash", "gh api repos/o/r/issues -f title=x"),
        ("Bash", "gh run rerun 99"),
        ("Bash", "gh workflow run ci.yml"),
        ("PowerShell", "Remove-Item -Force C:/scratch/x.txt"),
        ("PowerShell", "set-content x.txt 'y'"),
        ("Bash", "echo hi > notes.txt"),
        ("Bash", "rm notes.txt"),
        ("Bash", "rm -rf build"),
        ("Bash", "rmdir out"),
        ("Bash", "unlink link.txt"),
        ("Bash", "touch notes.txt"),
        ("Bash", "cp source.txt notes.txt"),
        ("Bash", "mv old.txt new.txt"),
        ("Bash", "mkdir -p out"),
        ("Bash", "echo hi | tee notes.txt"),
        ("Bash", "sed -i 's/a/b/' notes.txt"),
        ("Bash", "sed -i.bak 's/a/b/' notes.txt"),
        ("Bash", "sed -e 's/a/b/' -i notes.txt"),
        ("Bash", "sed --in-place 's/a/b/' notes.txt"),
        ("Bash", "ln notes.txt link.txt"),
        ("Bash", "ln -s target link"),
        ("Bash", "ln -sf target link"),
        ("Bash", "git status && rm notes.txt"),
        ("Bash", "sudo rm notes.txt"),
        ("Bash", "find . -name '*.tmp' | xargs rm"),
        ("Bash", "/bin/rm notes.txt"),
        ("Bash", "python ~/.agents/skills/pull-request/scripts/pull_request.py create --repo o/r"),
        ("Bash", "python pull_request.py edit --repo o/r --number 12 --body-file body.md"),
        ("Bash", "python pull_request.py comment --repo o/r --number 12 --body-file body.md"),
        ("Bash", "python pull_request.py review --repo o/r --number 12 --event approve"),
        ("Bash", 'pwsh -NoProfile -Command "git push origin HEAD"'),
        ("Bash", "cd repo && git checkout -b feat/x"),
        ("Bash", "echo hi>notes.txt"),
        ("Bash", "echo hi >> notes.txt"),
        ("Bash", "make 2> errors.log"),
        ("Bash", "make &> out.log"),
        ("PowerShell", "rm C:/scratch/x.txt"),
        ("PowerShell", "mkdir out"),
    ],
)
def test_should_block_a_mutating_command_after_hedged_reasoning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    tool_name: str,
    command: str,
) -> None:
    tool_input = {"command": command}
    transcript_path = acting_transcript(tmp_path, HEDGED_SENTENCE, tool_name, tool_input)
    exit_code, stdout_text = run_hook(monkeypatch, capsys, tool_name, tool_input, transcript_path)
    assert exit_code == 0
    assert json.loads(stdout_text) == expected_block(tool_name, HEDGED_SENTENCE)


@pytest.mark.parametrize(
    "global_options",
    [
        "--git-dir=/repo/.git",
        "--git-dir /repo/.git",
        "--work-tree=/repo",
        "--work-tree /repo",
        "-C /repo",
        "-c user.name=x",
        "--no-pager",
        "--namespace=n",
        "--namespace n",
        "-c user.name=x -C /repo",
    ],
)
@pytest.mark.parametrize("subcommand", ["push origin HEAD", "commit -F message.txt"])
def test_should_block_a_git_change_behind_global_options(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    global_options: str,
    subcommand: str,
) -> None:
    tool_input = {"command": f"git {global_options} {subcommand}"}
    transcript_path = acting_transcript(tmp_path, HEDGED_SENTENCE, "Bash", tool_input)
    exit_code, stdout_text = run_hook(monkeypatch, capsys, "Bash", tool_input, transcript_path)
    assert exit_code == 0
    assert json.loads(stdout_text) == expected_block("Bash", HEDGED_SENTENCE)


@pytest.mark.parametrize(
    "tool_name",
    [
        "Edit",
        "MultiEdit",
        "NotebookEdit",
        "Agent",
        "Task",
        "apply_patch",
        "mcp__gmail__send_message",
        "mcp__github__issue_write",
        "mcp__github__sub_issue_write",
        "mcp__github__pull_request_review_write",
        "mcp__github__add_issue_comment",
        "mcp__atlassian__createJiraIssue",
        "mcp__trello__trelloWriteCard",
    ],
)
def test_should_block_each_always_mutating_tool_after_hedged_reasoning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    tool_name: str,
) -> None:
    transcript_path = acting_transcript(tmp_path, HEDGED_SENTENCE, tool_name, {})
    exit_code, stdout_text = run_hook(monkeypatch, capsys, tool_name, {}, transcript_path)
    assert exit_code == 0
    assert json.loads(stdout_text)["decision"] == "block"


def test_should_register_a_matcher_covering_every_mutating_tool_name() -> None:
    hooks_configuration = json.loads(
        (Path(__file__).resolve().parent.parent / "hooks.json").read_text(encoding="utf-8")
    )
    all_matchers = [
        each_entry["matcher"]
        for each_entry in hooks_configuration["hooks"]["PostToolUse"]
        if any(
            "verify_before_acting.py" in each_hook["command"] for each_hook in each_entry["hooks"]
        )
    ]
    assert len(all_matchers) == 1
    matcher_pattern = re.compile(all_matchers[0])
    all_expected_names = (
        verify_before_acting.ALL_ALWAYS_MUTATING_TOOL_NAMES
        | verify_before_acting.ALL_SHELL_TOOL_NAMES
    )
    assert {
        each_name for each_name in all_expected_names if not matcher_pattern.fullmatch(each_name)
    } == set()


@pytest.mark.parametrize(
    "tool_name",
    [
        "TodoWrite",
        "TaskUpdate",
        "Read",
        "mcp__gmail__get_thread",
        "mcp__github__issue_read",
        "mcp__github__list_pull_requests",
        "mcp__github__search_issues",
        "mcp__github__get_post",
        "mcp__trello__trelloReadCard",
    ],
)
def test_should_pass_a_tool_the_matcher_over_reaches_untouched(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    tool_name: str,
) -> None:
    transcript_path = acting_transcript(tmp_path, HEDGED_SENTENCE, tool_name, {})
    exit_code, stdout_text = run_hook(monkeypatch, capsys, tool_name, {}, transcript_path)
    assert (exit_code, stdout_text) == (0, "")
    assert not (tmp_path / LOG_RELATIVE_PATH).exists()


def test_should_allow_and_log_unseen_when_the_tool_use_id_is_absent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_transcript(
        tmp_path,
        [
            thinking_record(ACTING_MESSAGE_ID, HEDGED_SENTENCE),
            tool_use_record(ACTING_MESSAGE_ID, "toolu_other", "Write", WRITE_INPUT),
        ],
    )
    exit_code, stdout_text = run_hook(monkeypatch, capsys, "Write", WRITE_INPUT, transcript_path)
    assert (exit_code, stdout_text) == (0, "")
    assert logged_outcomes(tmp_path) == ["reasoning_unseen"]


def test_should_allow_and_log_unseen_when_the_thinking_text_is_empty(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = acting_transcript(tmp_path, "", "Write", WRITE_INPUT)
    exit_code, stdout_text = run_hook(monkeypatch, capsys, "Write", WRITE_INPUT, transcript_path)
    assert (exit_code, stdout_text) == (0, "")
    assert logged_outcomes(tmp_path) == ["reasoning_unseen"]


def test_should_allow_and_log_unseen_when_the_transcript_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    missing_path = tmp_path / "missing.jsonl"
    exit_code, stdout_text = run_hook(monkeypatch, capsys, "Write", WRITE_INPUT, missing_path)
    assert (exit_code, stdout_text) == (0, "")
    assert logged_outcomes(tmp_path) == ["reasoning_unseen"]


def test_should_skip_malformed_lines_and_still_block(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_transcript(
        tmp_path,
        [
            "{not json",
            thinking_record(ACTING_MESSAGE_ID, HEDGED_SENTENCE),
            f'{{"truncated": "{ACTING_MESSAGE_ID}',
            "[1, 2]",
            tool_use_record(ACTING_MESSAGE_ID, TOOL_USE_ID, "Write", WRITE_INPUT),
        ],
    )
    exit_code, stdout_text = run_hook(monkeypatch, capsys, "Write", WRITE_INPUT, transcript_path)
    assert exit_code == 0
    assert json.loads(stdout_text) == expected_block("Write", HEDGED_SENTENCE)


def test_should_read_only_the_thinking_of_the_acting_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_transcript(
        tmp_path,
        [
            thinking_record(EARLIER_MESSAGE_ID, "The file probably exists."),
            tool_use_record(EARLIER_MESSAGE_ID, "toolu_read", "Read", {"file_path": "x"}),
            tool_result_record("toolu_read"),
            thinking_record(ACTING_MESSAGE_ID, CLEAN_SENTENCE),
            tool_use_record(ACTING_MESSAGE_ID, TOOL_USE_ID, "Write", WRITE_INPUT),
            tool_result_record(TOOL_USE_ID),
        ],
    )
    exit_code, stdout_text = run_hook(monkeypatch, capsys, "Write", WRITE_INPUT, transcript_path)
    assert (exit_code, stdout_text) == (0, "")
    assert logged_outcomes(tmp_path) == ["allowed_clean"]


def test_should_join_thinking_records_that_share_the_message_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_transcript(
        tmp_path,
        [
            thinking_record(ACTING_MESSAGE_ID, CLEAN_SENTENCE),
            {"type": "progress", "data": {"note": "unrelated record"}},
            thinking_record(ACTING_MESSAGE_ID, HEDGED_SENTENCE),
            tool_use_record(ACTING_MESSAGE_ID, TOOL_USE_ID, "Write", WRITE_INPUT),
            tool_result_record(TOOL_USE_ID),
        ],
    )
    exit_code, stdout_text = run_hook(monkeypatch, capsys, "Write", WRITE_INPUT, transcript_path)
    assert exit_code == 0
    assert json.loads(stdout_text) == expected_block("Write", HEDGED_SENTENCE)


@pytest.mark.parametrize(
    "thinking_text",
    [
        "That outcome is unlikely given the log line.",
        "I think the next step is to write the file.",
        "The tests should pass once this lands.",
    ],
)
def test_should_not_count_plan_words_or_partial_words_as_hedges(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    thinking_text: str,
) -> None:
    transcript_path = acting_transcript(tmp_path, thinking_text, "Write", WRITE_INPUT)
    exit_code, stdout_text = run_hook(monkeypatch, capsys, "Write", WRITE_INPUT, transcript_path)
    assert (exit_code, stdout_text) == (0, "")
    assert logged_outcomes(tmp_path) == ["allowed_clean"]


@pytest.mark.parametrize(
    "hedge_phrase",
    ["might be", "may be", "Maybe", "appears to", "I suspect", "my theory", "not sure"],
)
def test_should_block_on_each_hedge_phrase(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    hedge_phrase: str,
) -> None:
    transcript_path = acting_transcript(
        tmp_path, f"The cause {hedge_phrase} the stale cache.", "Write", WRITE_INPUT
    )
    exit_code, stdout_text = run_hook(monkeypatch, capsys, "Write", WRITE_INPUT, transcript_path)
    assert exit_code == 0
    assert json.loads(stdout_text)["decision"] == "block"


def test_should_keep_the_hedge_word_when_trimming_a_long_sentence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    long_sentence = ("word " * 60) + "this is probably the cause " + ("tail " * 40) + "end."
    transcript_path = acting_transcript(tmp_path, long_sentence, "Write", WRITE_INPUT)
    exit_code, stdout_text = run_hook(monkeypatch, capsys, "Write", WRITE_INPUT, transcript_path)
    reason = json.loads(stdout_text)["reason"]
    quoted_sentence = reason.split('"')[1]
    assert exit_code == 0
    assert "probably" in quoted_sentence
    assert quoted_sentence.startswith("...")
    assert quoted_sentence.endswith("...")
    assert len(quoted_sentence) <= 166
