import io
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

import sent_file_question_gate

GATE_SCRIPT_PATH = Path(sent_file_question_gate.__file__)

ASKING_FILES = [
    (
        "questions_heading.md",
        "# Status\n\nThe docs build is green.\n\n## Questions for you\n\n1. The release date\n",
        "Questions for you",
    ),
    ("open_questions.md", "## Open questions\n\n- The rate limit value\n", "Open questions"),
    ("decisions.md", "**Decisions needed**\n\n- The release date\n", "Decisions needed"),
    (
        "should_i.md",
        "The branch is pushed. Should I archive the old branches?\n",
        "Should I archive the old branches?",
    ),
    (
        "do_you_want.md",
        "- Do you want the cache cleared before the rerun?\n",
        "Do you want the cache cleared before the rerun?",
    ),
    (
        "choice.md",
        "The change is live. Keep it merged, or revert it?\n",
        "Keep it merged, or revert it?",
    ),
    (
        "short_choice.md",
        "Both fixes pass. Tag now or wait for the nightly build?\n",
        "Tag now or wait for the nightly build?",
    ),
    (
        "want_me.txt",
        "Checks passed.\nWant me to open the pull request?\n",
        "Want me to open the pull request?",
    ),
    ("proceed.md", "Three files changed. Proceed?\n", "Proceed?"),
    (
        "wrapped.md",
        "The deploy finished and the logs are clean. Would you like\nme to remove the old build folder?\n",
        "Would you like me to remove the old build folder?",
    ),
    (
        "table.md",
        "| Item | Question |\n|---|---|\n| Cache | Should we clear it? |\n",
        "Should we clear it?",
    ),
    (
        "prefer.html",
        "<html><body><h1>Plan</h1><p>Two layouts fit. Which option do you prefer?</p></body></html>",
        "Which option do you prefer?",
    ),
    ("open.html", "<h2>Open questions</h2><ul><li>Rate limit value</li></ul>", "Open questions"),
    (
        "decide.htm",
        "<p>The key expires Friday. <b>Should I</b> rotate it now?</p>",
        "Should I rotate it now?",
    ),
    ("yes_or_no.md", "Checks passed. Should I merge it? Yes or no.\n", "Should I merge it?"),
    (
        "full_width.md",
        "Do you want the cache cleared？ Reply yes to clear it.\n",
        "Do you want the cache cleared?",
    ),
    (
        "can_i.md",
        "The logs fill the disk. Can I delete the old ones?\n",
        "Can I delete the old ones?",
    ),
    (
        "choice_reply.md",
        "Is it a bug or a flake? Let me know before noon.\n",
        "Is it a bug or a flake?",
    ),
    ("no_rush.md", "The plan is ready. Do you approve? No rush.\n", "Do you approve?"),
    ("wish_then_context.md", "Do you want the cache cleared? It takes a minute.\n", "Do you want"),
    ("thoughts.md", "The draft is up.\n\nThoughts?\n", "Thoughts?"),
    ("are_we_good.md", "Tests pass. Are we good to ship?\n", "Are we good to ship?"),
    (
        "checkbox.md",
        "- [ ] Should I archive the old branches?\n",
        "Should I archive the old branches?",
    ),
    (
        "decisions_from_you.md",
        "## Decisions needed from you\n\n- Release date\n",
        "Decisions needed",
    ),
    ("need_your_input.md", "### Need your input\n\n- Release date\n", "Need your input"),
]

CLEAN_FILES = [
    ("faq.md", "## How do I install it?\n\nRun the installer.\n"),
    ("faq_you.md", "Do you need admin rights? Only for the system install.\n"),
    ("troubleshooting.md", "## Troubleshooting\n\nDid you set `HOME`? Set it before the run.\n"),
    ("q_and_a_split.md", "Q: Can you run it offline?\n\nA: Yes.\n"),
    ("heading_question.md", "## Should I pin the version?\n\nPin it in the lock file.\n"),
    ("bold_question.md", "**Can you run it offline?**\n\nIt runs offline.\n"),
    ("fenced.md", "Run this:\n\n```\nread -p 'Should I continue? ' answer\n```\n"),
    ("quoted.md", "You wrote:\n\n> Should we ship this today?\n\nIt shipped at noon.\n"),
    ("code_span.md", "The prompt reads `Do you want to continue?` on start.\n"),
    ("answered.md", "Does the gate hold a second stop? No. It passes a held stop.\n"),
    ("answered_yes.md", "Can you rerun it? Yes, the rerun button sits on the run page.\n"),
    ("q_and_a.md", "Q: Can you run it offline?\nA: Yes.\n"),
    ("answered_cell.md", "| Question | Answer |\n|---|---|\n| Does it retry? | Twice |\n"),
    ("statement.md", "# Report\n\nThe build passed. Two tests were added.\n"),
    ("rhetorical.md", "Why did the build fail? The cache key changed.\n"),
    ("url.md", "The page is at https://example.com/search?q=1 now.\n"),
    ("quoted_example.md", 'Ask the user one thing, such as "Do you want approach A or B?"\n'),
    (
        "curly_quoted.md",
        "Preferences: “Do you want the cache kept?” go through the question tool.\n",
    ),
    (
        "quoted_pair.md",
        'Then ask: "Does this map cover what you need? Any rules to add?" and wait.\n',
    ),
    (
        "long_list_or.md",
        "What files, folders, or areas of the code does this change touch in the build?\n",
    ),
    ("bare_questions.md", "## Questions\n\nThe team answered each one below.\n"),
    ("decisions_taken.md", "## Decisions\n\n- The cache stays on.\n"),
    (
        "pre.html",
        "<p>The script prints a prompt.</p><pre>Do you want this?</pre><script>var x = 'Should I?';</script>",
    ),
    ("heading_question.html", "<h3>Should you rotate the key?</h3><p>Rotate it every 90 days.</p>"),
    ("quote.html", "<blockquote>Should we ship this?</blockquote><p>It shipped.</p>"),
    ("image.png", "Should I archive the old branches?\n"),
    ("faq_item.md", "## FAQ\n\n- Can I use it offline? After the first sync.\n"),
    (
        "details.html",
        "<details><summary>Can I use it offline?</summary><p>After the first sync.</p></details>",
    ),
    (
        "indented_code.md",
        "Run the prompt:\n\n    read -p 'Do you want to continue? ' answer\n\nIt waits for input.\n",
    ),
    (
        "self_answered.md",
        "Is it a bug or a flake? Logs show the same stack on each run, so a flake.\n",
    ),
]


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool_name: str,
    tool_input: object,
    working_directory: Path,
) -> tuple[int, str]:
    hook_input = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "cwd": str(working_directory),
    }
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = sent_file_question_gate.main()
    return exit_code, capsys.readouterr().err


def written_file(folder: Path, file_name: str, file_text: str) -> Path:
    file_path = folder / file_name
    file_path.write_text(file_text, encoding="utf-8")
    return file_path


@pytest.mark.parametrize(("file_name", "file_text", "quoted_question"), ASKING_FILES)
def test_should_deny_a_sent_file_that_asks_the_user(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    file_name: str,
    file_text: str,
    quoted_question: str,
) -> None:
    file_path = written_file(tmp_path, file_name, file_text)
    exit_code, reason = run_gate(
        monkeypatch, capsys, "SendUserFile", {"files": [str(file_path)]}, tmp_path
    )
    assert exit_code == 2
    assert quoted_question in reason
    assert file_name in reason
    assert "AskUserQuestion" in reason


@pytest.mark.parametrize(("file_name", "file_text"), CLEAN_FILES)
def test_should_allow_a_sent_file_that_asks_nothing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    file_name: str,
    file_text: str,
) -> None:
    file_path = written_file(tmp_path, file_name, file_text)
    exit_code, reason = run_gate(
        monkeypatch, capsys, "SendUserFile", {"files": [str(file_path)]}, tmp_path
    )
    assert (exit_code, reason) == (0, "")


@pytest.mark.parametrize(("file_name", "file_text", "quoted_question"), ASKING_FILES)
def test_should_deny_a_page_publish_that_asks_the_user(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    file_name: str,
    file_text: str,
    quoted_question: str,
) -> None:
    file_path = written_file(tmp_path, file_name, file_text)
    exit_code, reason = run_gate(
        monkeypatch, capsys, "Artifact", {"file_path": str(file_path)}, tmp_path
    )
    assert exit_code == 2
    assert quoted_question in reason


def test_should_allow_a_page_that_saves_the_answer_through_a_capability(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    file_path = written_file(
        tmp_path,
        "cards.html",
        "<h2>Which layout do you prefer?</h2><p>Which option do you prefer?</p>",
    )
    tool_input = {"action": "publish", "file_path": str(file_path), "capabilities": {"db": {}}}
    assert run_gate(monkeypatch, capsys, "Artifact", tool_input, tmp_path) == (0, "")


@pytest.mark.parametrize(
    "tool_input",
    [
        {"action": "read", "url": "https://claude.ai/artifact/x", "file_path": "ask.md"},
        {
            "action": "publish",
            "url": "https://claude.ai/artifact/x",
            "asset": True,
            "file_path": "ask.md",
        },
        {"action": "publish", "type_url": "https://claude.ai/artifact/t", "file_path": "ask.md"},
        {"action": "list"},
    ],
)
def test_should_allow_an_artifact_call_that_publishes_no_page(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    tool_input: dict[str, object],
) -> None:
    written_file(tmp_path, "ask.md", "Should I archive the old branches?\n")
    assert run_gate(monkeypatch, capsys, "Artifact", tool_input, tmp_path) == (0, "")


def test_should_read_a_relative_path_from_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    written_file(tmp_path, "status.md", "Should I archive the old branches?\n")
    exit_code, reason = run_gate(
        monkeypatch, capsys, "SendUserFile", {"files": ["status.md"]}, tmp_path
    )
    assert exit_code == 2
    assert "status.md" in reason


def test_should_name_the_file_that_asks_among_several(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    clean_path = written_file(tmp_path, "clean.md", "The build passed.\n")
    asking_path = written_file(tmp_path, "asking.md", "Do you want the logs too?\n")
    tool_input = {"files": [str(clean_path), str(asking_path)]}
    exit_code, reason = run_gate(monkeypatch, capsys, "SendUserFile", tool_input, tmp_path)
    assert exit_code == 2
    assert "asking.md" in reason
    assert "clean.md" not in reason


@pytest.mark.parametrize(
    ("tool_name", "tool_input"),
    [
        ("SendUserFile", {"files": ["missing.md"]}),
        ("SendUserFile", {"files": "not-a-list"}),
        ("SendUserFile", "not-a-dict"),
        ("Write", {"file_path": "ask.md", "content": "Should I archive the old branches?"}),
    ],
)
def test_should_allow_a_payload_it_cannot_read(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    tool_name: str,
    tool_input: object,
) -> None:
    assert run_gate(monkeypatch, capsys, tool_name, tool_input, tmp_path) == (0, "")


def test_should_deny_through_the_script_entry_point(tmp_path: Path) -> None:
    file_path = written_file(tmp_path, "status.md", "Should I archive the old branches?\n")
    hook_input = {
        "hook_event_name": "PreToolUse",
        "tool_name": "SendUserFile",
        "tool_input": {"files": [str(file_path)]},
        "cwd": str(tmp_path),
    }
    completed = subprocess.run(
        [sys.executable, str(GATE_SCRIPT_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env={"HOME": str(tmp_path), "PATH": ""},
        check=False,
    )
    assert completed.returncode == 2
    assert "Should I archive the old branches?" in completed.stderr


def test_question_for_user_should_return_none_for_plain_statements() -> None:
    assert sent_file_question_gate.question_for_user("The build passed.\n", is_html=False) is None


@pytest.mark.parametrize(
    "file_text",
    [
        "# T" + " " * 3000 + "x",
        "**a**" + " " * 50000,
        "**a**" + " " * 50000 + "x",
        "## Open" + " " * 50000 + "questions #" + " " * 50000 + "x",
    ],
)
def test_question_for_user_should_read_long_space_runs_in_linear_time(file_text: str) -> None:
    started_at = time.perf_counter()
    sent_file_question_gate.question_for_user(file_text, is_html=False)
    assert time.perf_counter() - started_at < 1


@pytest.mark.parametrize("capability_name", ["fetch", "sample", "mcp", "tts"])
def test_should_deny_a_page_whose_capability_saves_no_answer(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    capability_name: str,
) -> None:
    file_path = written_file(tmp_path, "page.html", "<p>Which option do you prefer?</p>")
    tool_input = {
        "action": "publish",
        "file_path": str(file_path),
        "capabilities": {capability_name: {}},
    }
    exit_code, reason = run_gate(monkeypatch, capsys, "Artifact", tool_input, tmp_path)
    assert exit_code == 2
    assert "Which option do you prefer?" in reason


@pytest.mark.parametrize("capability_name", ["db", "artifact", "self"])
def test_should_allow_each_capability_that_saves_the_answer(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    capability_name: str,
) -> None:
    file_path = written_file(tmp_path, "page.html", "<p>Which option do you prefer?</p>")
    tool_input = {
        "action": "publish",
        "file_path": str(file_path),
        "capabilities": {capability_name: {}, "user": {}},
    }
    assert run_gate(monkeypatch, capsys, "Artifact", tool_input, tmp_path) == (0, "")


@pytest.mark.parametrize(
    ("question_at_start", "quoted_question"),
    [(True, "Should I archive the old branches?"), (False, "Do you want the logs too?")],
)
def test_should_read_the_start_and_end_of_a_file_over_the_size_limit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    question_at_start: bool,
    quoted_question: str,
) -> None:
    filler_text = "The build passed on every runner. é\n" * 20000
    file_text = (
        quoted_question + "\n\n" + filler_text
        if question_at_start
        else filler_text + "\n" + quoted_question + "\n"
    )
    file_path = written_file(tmp_path, "large.md", file_text)
    assert file_path.stat().st_size > 262144
    exit_code, reason = run_gate(
        monkeypatch, capsys, "SendUserFile", {"files": [str(file_path)]}, tmp_path
    )
    assert exit_code == 2
    assert quoted_question in reason


@pytest.mark.parametrize(
    "file_bytes",
    [
        b"\x00\x01Should I archive it?\xff\xfe",
        b"Should I archive the old branches?\n\xff\xfe\xfa",
    ],
)
def test_should_allow_a_file_that_is_not_utf8_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    file_bytes: bytes,
) -> None:
    file_path = tmp_path / "binary.md"
    file_path.write_bytes(file_bytes)
    assert run_gate(monkeypatch, capsys, "SendUserFile", {"files": [str(file_path)]}, tmp_path) == (
        0,
        "",
    )


def test_should_quote_at_most_a_short_line_of_a_long_question(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    long_question = "Should I archive " + "the old branch, " * 60 + "now?"
    file_path = written_file(tmp_path, "long.md", long_question + "\n")
    exit_code, reason = run_gate(
        monkeypatch, capsys, "SendUserFile", {"files": [str(file_path)]}, tmp_path
    )
    assert exit_code == 2
    quoted_text = reason.split('"')[1]
    assert len(quoted_text) <= 160
    assert quoted_text.startswith("Should I archive the old branch,")
    assert quoted_text.endswith("...")
