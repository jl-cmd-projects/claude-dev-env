"""Behavior tests for the pieces-per-level note.

Every case runs the script the way the harness does: one JSON payload on
stdin, then a read of the exit code, stdout, and stderr. Each case must exit 0
with an empty stderr and no permission decision.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
advisory_directory = str(Path(__file__).resolve().parent)
if advisory_directory not in sys.path:
    sys.path.insert(0, advisory_directory)

import pieces_per_level_note
from hooks_constants.pieces_per_level_note_constants import MAXIMUM_COMMAND_CHARACTERS

SCRIPT_PATH = Path(__file__).resolve().parent / "pieces_per_level_note.py"
HOOKS_JSON_PATH = Path(__file__).resolve().parent.parent / "hooks.json"
RUN_TIMEOUT_SECONDS = 30
HOSTILE_INPUT_SECONDS_BOUND = 1.0
HOSTILE_SUBPROCESS_SECONDS_BOUND = 8.0

MIXED_SUBJECT = (
    "fix(convert): always publish drawn icons, put Tips on the tray, stop the label smear"
)
MIXED_TITLE = "fix(convert): always publish, put Tips on the tray, draw a plain home label"
ALL_SINGLE_BEHAVIOUR_SUBJECTS = (
    "fix(lock): darken or lighten the lock video behind lock elements",
    "perf(themes): copy queued themes on a bounded thread pool",
    "feat(evals): add theme metadata evals with frozen dataset and rerun commands",
)
THREE_PAIR_BODY = "\n".join(
    [
        "## What this does",
        "Publishes icons.",
        "",
        "## Proof in practice",
        "Without the change: `run publish` printed `skipped`.",
        "With the change: `run publish` printed `published`.",
        "Without the change: `run tray` showed no Tips.",
        "With the change: `run tray` showed Tips.",
        "Without the change: `run label` smeared.",
        "With the change: `run label` drew plain.",
    ]
)
SIX_TOPIC_BODY = "\n".join(
    ["## What this does"] + [f"- **Topic {each_number}.** text" for each_number in range(6)]
)
ONE_PAIR_BODY = "\n".join(
    [
        "## What this does",
        "- **One topic.** text",
        "",
        "## Proof in practice",
        "Without the change: `run a` failed.",
        "With the change: `run a` passed.",
    ]
)


def _run(stdin_text: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT_SECONDS,
        check=False,
    )


def _shell_payload(command: str, working_directory: str = "") -> str:
    all_fields: dict[str, object] = {"tool_name": "Bash", "tool_input": {"command": command}}
    if working_directory:
        all_fields["cwd"] = working_directory
    return json.dumps(all_fields)


def _mcp_payload(title: str, body: str) -> str:
    return json.dumps(
        {
            "tool_name": "mcp__github__create_pull_request",
            "tool_input": {"owner": "acme", "repo": "widgets", "title": title, "body": body},
        }
    )


def _context(completed: subprocess.CompletedProcess[str]) -> str:
    assert completed.returncode == 0
    assert completed.stderr == ""
    all_fields = json.loads(completed.stdout)
    assert list(all_fields) == ["hookSpecificOutput"]
    all_specific = all_fields["hookSpecificOutput"]
    assert set(all_specific) == {"hookEventName", "additionalContext"}
    assert all_specific["hookEventName"] == "PreToolUse"
    return all_specific["additionalContext"]


def _assert_silent(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == 0
    assert completed.stderr == ""
    assert completed.stdout == ""


def test_the_mixed_commit_subject_gets_a_note_that_names_each_piece() -> None:
    note = _context(_run(_shell_payload(f'git commit -m "{MIXED_SUBJECT}"')))
    assert '"always publish drawn icons"' in note
    assert '"put Tips on the tray"' in note
    assert '"stop the label smear"' in note
    assert "its own commit and its own stack level" in note
    assert "`git reset --soft HEAD~1`" in note
    assert "`gt create`" in note


def test_a_heredoc_commit_message_gets_the_note() -> None:
    command = (
        f"git add -A && git commit -m \"$(cat <<'EOF'\n{MIXED_SUBJECT}\n\nbody; more\nEOF\n)\""
    )
    assert '"put Tips on the tray"' in _context(_run(_shell_payload(command)))


@pytest.mark.parametrize(
    "command",
    [
        f'git commit -am "{MIXED_SUBJECT}"',
        f'git commit --message="{MIXED_SUBJECT}"',
        f'git commit --message "{MIXED_SUBJECT}"',
        f"git -C repo commit -m '{MIXED_SUBJECT}' -m 'second paragraph'",
        f"pwsh -Command \"git commit -m '{MIXED_SUBJECT}'\"",
        f'git add x && git commit -m "{MIXED_SUBJECT}" && git push',
    ],
)
def test_other_commit_shapes_get_the_note(command: str) -> None:
    assert '"stop the label smear"' in _context(_run(_shell_payload(command)))


def test_a_commit_message_file_resolves_against_the_payload_working_directory(
    tmp_path: Path,
) -> None:
    (tmp_path / "message.txt").write_text(f"{MIXED_SUBJECT}\n\nbody\n", encoding="utf-8")
    note = _context(_run(_shell_payload("git commit -F message.txt", str(tmp_path))))
    assert '"always publish drawn icons"' in note


def test_a_commit_message_file_named_by_a_long_option_gets_the_note(tmp_path: Path) -> None:
    (tmp_path / "message.txt").write_text(f"{MIXED_SUBJECT}\n", encoding="utf-8")
    note = _context(_run(_shell_payload("git commit --file=message.txt", str(tmp_path))))
    assert '"put Tips on the tray"' in note


def test_the_first_message_is_the_subject_and_later_ones_are_body_paragraphs() -> None:
    command = f'git commit -m "fix(x): one behaviour" -m "{MIXED_SUBJECT}"'
    _assert_silent(_run(_shell_payload(command)))


@pytest.mark.parametrize("subject", ALL_SINGLE_BEHAVIOUR_SUBJECTS)
def test_a_single_behaviour_commit_subject_is_silent(subject: str) -> None:
    _assert_silent(_run(_shell_payload(f'git commit -m "{subject}"')))


@pytest.mark.parametrize(
    "command",
    [
        "git commit --amend",
        "git commit -F -",
        "git commit -F missing-file.txt",
        f"git commit -m '{MIXED_SUBJECT}",
        f'echo "{MIXED_SUBJECT}"',
        "git status",
        "gh pr view 12",
        "gh pr create --fill",
        "",
    ],
)
def test_a_command_with_no_readable_several_piece_message_is_silent(command: str) -> None:
    _assert_silent(_run(_shell_payload(command)))


def test_the_mixed_pull_request_title_gets_a_note_from_gh(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text("## What this does\nOne.\n", encoding="utf-8")
    command = f'gh pr create --title "{MIXED_TITLE}" --body-file body.md'
    note = _context(_run(_shell_payload(command, str(tmp_path))))
    assert "this pull request" in note
    assert '"draw a plain home label"' in note
    assert "`gh pr create --base <previous-branch>`" in note


def test_the_pull_request_script_create_call_gets_a_note(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text("## What this does\nOne.\n", encoding="utf-8")
    command = (
        f"python ~/.agents/skills/pull-request/scripts/pull_request.py create --repo a/b "
        f'--base main --head h --title "{MIXED_TITLE}" --body-file body.md'
    )
    assert '"put Tips on the tray"' in _context(_run(_shell_payload(command, str(tmp_path))))


def test_a_body_with_three_proof_pairs_gets_a_note_even_with_a_single_title(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text(THREE_PAIR_BODY, encoding="utf-8")
    command = 'gh pr create --title "fix(convert): publish icons" --body-file body.md'
    note = _context(_run(_shell_payload(command, str(tmp_path))))
    assert "3 without/with proof pairs under Proof in practice" in note


def test_the_mcp_create_call_with_the_mixed_title_and_three_pairs_gets_a_note() -> None:
    note = _context(_run(_mcp_payload(MIXED_TITLE, THREE_PAIR_BODY)))
    assert '"always publish"' in note
    assert "3 without/with proof pairs" in note


def test_six_bold_led_topics_are_named_up_to_the_cap() -> None:
    note = _context(_run(_mcp_payload("fix(convert): publish icons", SIX_TOPIC_BODY)))
    assert '"Topic 0"' in note
    assert '"Topic 5"' in note


def test_one_topic_and_one_proof_pair_stay_silent() -> None:
    _assert_silent(_run(_mcp_payload("fix(convert): publish icons", ONE_PAIR_BODY)))


@pytest.mark.parametrize("subject", ALL_SINGLE_BEHAVIOUR_SUBJECTS)
def test_a_single_behaviour_pull_request_title_is_silent(subject: str) -> None:
    _assert_silent(_run(_mcp_payload(subject, ONE_PAIR_BODY)))


def test_an_unreadable_body_file_leaves_the_title_signal_alone(tmp_path: Path) -> None:
    command = f'gh pr create --title "{MIXED_TITLE}" --body-file missing.md'
    assert '"put Tips on the tray"' in _context(_run(_shell_payload(command, str(tmp_path))))


def test_an_unreadable_body_file_with_a_single_title_is_silent(tmp_path: Path) -> None:
    command = 'gh pr create --title "fix(convert): publish icons" --body-file missing.md'
    _assert_silent(_run(_shell_payload(command, str(tmp_path))))


def test_a_note_over_the_piece_cap_counts_the_rest() -> None:
    all_lines = ["## What this does"] + [
        f"- **Topic {each_number}.** text" for each_number in range(9)
    ]
    note = _context(_run(_mcp_payload("fix(x): publish icons", "\n".join(all_lines))))
    assert "and 3 more" in note


@pytest.mark.parametrize(
    "stdin_text",
    [
        "",
        "not json",
        "[1, 2]",
        "null",
        '{"tool_name": "Bash"}',
        '{"tool_name": "Bash", "tool_input": "git commit"}',
        '{"tool_name": "Bash", "tool_input": {"command": 7}}',
        '{"tool_name": 7, "tool_input": {"command": "git commit -m x"}}',
        '{"tool_name": "mcp__github__create_pull_request", "tool_input": {"title": 7, "body": []}}',
        '{"tool_name": "Read", "tool_input": {"file_path": "a"}}',
        '{"tool_name": "Bash", "tool_input": {"command": "git commit -m \\"unterminated"}}',
        "﻿{broken",
    ],
)
def test_a_malformed_or_unrelated_payload_is_silent(stdin_text: str) -> None:
    _assert_silent(_run(stdin_text))


def test_the_script_has_no_path_that_names_a_refusal() -> None:
    all_source_texts = [
        SCRIPT_PATH.read_text(encoding="utf-8"),
        (SCRIPT_PATH.parent / "piece_clauses.py").read_text(encoding="utf-8"),
        (
            SCRIPT_PATH.parent.parent / "hooks_constants" / "pieces_per_level_note_constants.py"
        ).read_text(encoding="utf-8"),
    ]
    for each_source in all_source_texts:
        all_code_lines = [
            each_line
            for each_line in each_source.splitlines()
            if not each_line.lstrip().startswith(('"', "#", "-", "Your", "::"))
        ]
        code_text = "\n".join(all_code_lines)
        assert "permissionDecision" not in code_text
        assert "PERMISSION_DECISION" not in code_text
        assert '"deny"' not in code_text
        assert '"block"' not in code_text
        assert "sys.exit(2" not in code_text


def test_the_hook_is_registered_on_the_commit_and_pull_request_tools_as_a_pre_tool_use_note() -> (
    None
):
    all_registrations = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
    all_matching_groups = [
        each_group
        for each_group in all_registrations["hooks"]["PreToolUse"]
        if any(
            "pieces_per_level_note.py" in each_hook.get("command", "") for each_hook in each_group["hooks"]
        )
    ]
    assert len(all_matching_groups) == 1
    each_group = all_matching_groups[0]
    assert each_group["matcher"] == "Bash|PowerShell|mcp__.*__create_pull_request"
    assert [each_hook["type"] for each_hook in each_group["hooks"]] == ["command"]


def test_title_pieces_come_first_and_the_body_topics_are_not_listed_twice() -> None:
    body = "\n".join(
        ["## What this does", "- **Always publish.** a", "- **Home label.** b", "", THREE_PAIR_BODY]
    )
    note = _context(_run(_mcp_payload(MIXED_TITLE, body)))
    assert '"always publish"' in note
    assert '"Home label"' not in note
    assert note.index('"draw a plain home label"') < note.index("3 without/with proof pairs")


def test_a_heredoc_message_that_holds_a_double_quote_still_gets_the_note() -> None:
    command = (
        "git commit -m \"$(cat <<'EOF'\n"
        + MIXED_SUBJECT
        + "\n\nHe said \"stop\" and left.\nEOF\n)\""
    )
    assert '"stop the label smear"' in _context(_run(_shell_payload(command)))


def test_a_heredoc_message_with_a_single_behaviour_subject_is_silent() -> None:
    command = "git commit -m \"$(cat <<'EOF'\nfix(x): handle empty input\n\nHe said \"stop\".\nEOF\n)\""
    _assert_silent(_run(_shell_payload(command)))


HOSTILE_BULLET_LINE = "- **Topic** text here\n"
ALL_HOSTILE_COMMANDS = {
    "repeated commit words": "git commit " * 1000,
    "repeated commit words at the cap": "git commit " * (MAXIMUM_COMMAND_CHARACTERS // 11),
    "repeated heredoc starts": "git commit -m \"$(cat <<'EOF'\n" * 300,
    "message over the cap": 'git commit -m "' + "a" * 200_000 + '"',
    "bullet body over the cap": 'gh pr create --title t --body "'
    + HOSTILE_BULLET_LINE * 9_000
    + '"',
    "mixed subject padded past the cap": f'git commit -m "{MIXED_SUBJECT}"'
    + " " * MAXIMUM_COMMAND_CHARACTERS,
}


def _decide_seconds(command: str) -> tuple[object, float]:
    all_fields = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": ""}
    started_at = time.perf_counter()
    output = pieces_per_level_note.decide_hook_output(all_fields)
    return output, time.perf_counter() - started_at


@pytest.mark.parametrize("command_name", list(ALL_HOSTILE_COMMANDS))
def test_a_hostile_command_gets_no_note_within_the_time_bound(command_name: str) -> None:
    output, elapsed_seconds = _decide_seconds(ALL_HOSTILE_COMMANDS[command_name])
    assert output is None
    assert elapsed_seconds < HOSTILE_INPUT_SECONDS_BOUND


@pytest.mark.parametrize(
    "command_name", ["repeated commit words", "message over the cap", "bullet body over the cap"]
)
def test_a_hostile_command_exits_zero_and_silent_inside_the_hook_timeout(
    command_name: str,
) -> None:
    started_at = time.perf_counter()
    completed = _run(_shell_payload(ALL_HOSTILE_COMMANDS[command_name]))
    elapsed_seconds = time.perf_counter() - started_at
    _assert_silent(completed)
    assert elapsed_seconds < HOSTILE_SUBPROCESS_SECONDS_BOUND


def test_a_command_just_under_the_cap_still_gets_the_note() -> None:
    command = f'git commit -m "{MIXED_SUBJECT}"'
    command = command + " " * (MAXIMUM_COMMAND_CHARACTERS - len(command))
    output, _ = _decide_seconds(command)
    assert "stop the label smear" in json.dumps(output)
