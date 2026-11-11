"""Behavior tests for the commit and pull request words reader."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

advisory_directory = str(Path(__file__).resolve().parent)
if advisory_directory not in sys.path:
    sys.path.insert(0, advisory_directory)

import commit_and_pull_request_words

SUBJECT = "fix(x): publish icons, draw the label"


def test_the_first_message_is_the_subject() -> None:
    command = f'git commit -m "{SUBJECT}" -m "body paragraph"'
    assert commit_and_pull_request_words.commit_subjects(command, "") == [SUBJECT]


@pytest.mark.parametrize(
    "command",
    [
        f'git commit -am "{SUBJECT}"',
        f'git commit --message="{SUBJECT}"',
        f"git -C repo commit -m '{SUBJECT}'",
        f"pwsh -Command \"git commit -m '{SUBJECT}'\"",
        f'git add . && git commit -m "{SUBJECT}" && git push',
    ],
)
def test_each_message_option_shape_gives_the_subject(command: str) -> None:
    assert SUBJECT in commit_and_pull_request_words.commit_subjects(command, "")


def test_a_heredoc_message_with_a_double_quote_gives_its_subject() -> None:
    command = f'git commit -m "$(cat <<\'EOF\'\n{SUBJECT}\n\nHe said "stop".\nEOF\n)"'
    assert SUBJECT in commit_and_pull_request_words.commit_subjects(command, "")


def test_a_message_file_resolves_against_the_working_directory(tmp_path: Path) -> None:
    (tmp_path / "message.txt").write_text(f"\n{SUBJECT}\n\nbody\n", encoding="utf-8")
    command = "git commit -F message.txt"
    assert commit_and_pull_request_words.commit_subjects(command, str(tmp_path)) == [SUBJECT]


@pytest.mark.parametrize(
    "command",
    [
        "git commit --amend",
        "git commit -F -",
        "git commit -F absent.txt",
        "git status",
        "git commit -m 'open",
    ],
)
def test_a_command_with_no_readable_message_gives_no_subject(command: str) -> None:
    assert commit_and_pull_request_words.commit_subjects(command, "") == []


def test_a_gh_create_call_gives_its_title_and_body_file(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text("## What this does\nOne.\n", encoding="utf-8")
    command = 'gh pr create --title "fix: a, b" --body-file body.md'
    assert commit_and_pull_request_words.pull_request_words(command, str(tmp_path)) == [
        ("fix: a, b", "## What this does\nOne.\n")
    ]


def test_the_pull_request_script_create_call_gives_its_title_and_inline_body() -> None:
    command = "python pull_request.py create --repo a/b --title=t --body inline"
    assert commit_and_pull_request_words.pull_request_words(command, "") == [("t", "inline")]


def test_a_missing_body_file_gives_a_title_and_no_body(tmp_path: Path) -> None:
    command = "gh pr create --title t --body-file absent.md"
    assert commit_and_pull_request_words.pull_request_words(command, str(tmp_path)) == [("t", None)]


@pytest.mark.parametrize(
    "command", ["gh pr view 3", "gh pr edit 3 --title t", "git commit -m x", ""]
)
def test_a_command_that_creates_no_pull_request_gives_no_words(command: str) -> None:
    assert commit_and_pull_request_words.pull_request_words(command, "") == []
