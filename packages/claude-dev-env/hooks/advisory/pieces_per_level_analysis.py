"""Find the pieces a commit or pull request create names, and build the context note.

This module holds the analysis only: ``decide_hook_output`` maps a PreToolUse
payload to the note, or to None. ``pieces_per_level_note.py`` runs it in a child
process under a wall-clock deadline. The signals, all from the author's own
words:

- A conventional subject or title whose description joins two or more
  verb-led clauses with commas, semicolons, or "and".
- A pull request body whose "Proof in practice" section holds more than one
  without/with pair.
- A pull request body whose "What this does" section holds more than one
  bold-led topic bullet.

A single behaviour with a compound object or an alternative stays silent, and
so does a message or body the analysis cannot read. A command longer than
``MAXIMUM_COMMAND_CHARACTERS`` gets no note, and a message or body file is read
only when it is a regular file, and only up to ``MAXIMUM_FILE_BYTES`` bytes. A
title, a body, and a line of a body are read only up to their character caps.
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
advisory_directory = str(Path(__file__).resolve().parent)
if advisory_directory not in sys.path:
    sys.path.insert(0, advisory_directory)

import commit_and_pull_request_words
import piece_clauses
from hooks_constants.followup_pr_dedupe_constants import CREATE_PULL_REQUEST_TOOL_SUFFIX
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
)
from hooks_constants.pieces_per_level_note_constants import (
    ADDITIONAL_CONTEXT_KEY,
    ALL_NEXT_COMMAND_BY_KIND,
    ALL_QUICK_SCAN_WORDS,
    BODY_INPUT_KEY,
    COMMAND_INPUT_KEY,
    COMMIT_KIND,
    MAXIMUM_COMMAND_CHARACTERS,
    MAXIMUM_NAMED_PIECES,
    MINIMUM_PROOF_PAIR_COUNT,
    MORE_PIECES_TEMPLATE,
    NOTE_TEMPLATE,
    PIECE_SEPARATOR,
    PRE_TOOL_USE_EVENT_NAME,
    PROOF_PAIRS_PIECE_TEMPLATE,
    PULL_REQUEST_KIND,
    QUOTED_PIECE_TEMPLATE,
    TITLE_INPUT_KEY,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    WORKING_DIRECTORY_KEY,
)
from hooks_constants.pre_tool_use_context_runner import run_context_hook
from hooks_constants.pr_lifecycle_skill_gate_constants import SHELL_TOOL_NAMES


def _capped(all_pieces: list[str]) -> list[str]:
    if len(all_pieces) <= MAXIMUM_NAMED_PIECES:
        return all_pieces
    all_hidden_count = len(all_pieces) - MAXIMUM_NAMED_PIECES
    return [*all_pieces[:MAXIMUM_NAMED_PIECES], MORE_PIECES_TEMPLATE.format(count=all_hidden_count)]


def _quoted(all_pieces: list[str]) -> list[str]:
    return [QUOTED_PIECE_TEMPLATE.format(piece=each_piece) for each_piece in all_pieces]


def commit_pieces(command: str, working_directory: str) -> list[str]:
    """Return the quoted pieces the first several-piece commit subject names, else an empty list.

    Args:
        command: The shell command text the agent ran.
        working_directory: The folder a relative ``-F`` path resolves against.
    """
    for each_subject in commit_and_pull_request_words.commit_subjects(command, working_directory):
        all_pieces = piece_clauses.subject_pieces(each_subject)
        if all_pieces:
            return _capped(_quoted(all_pieces))
    return []


def pull_request_pieces(title: str | None, body: str | None) -> list[str]:
    """Return what a pull request's title and body name as several pieces, else an empty list.

    The title's verb-led clauses come first, or the body's bold-led topics
    when the title names one piece. A body with more than one without/with
    proof pair adds that count.

    Args:
        title: The pull request title, or None.
        body: The pull request body, or None.
    """
    all_title_pieces = _quoted(piece_clauses.subject_pieces(title or ""))
    all_topics = piece_clauses.topic_bullets(body) if body else []
    all_topic_pieces = _quoted(all_topics) if len(all_topics) >= MINIMUM_PROOF_PAIR_COUNT else []
    pair_count = piece_clauses.proof_pair_count(body) if body else 0
    all_pair_pieces = (
        [PROOF_PAIRS_PIECE_TEMPLATE.format(count=pair_count)]
        if pair_count >= MINIMUM_PROOF_PAIR_COUNT
        else []
    )
    return [*_capped(all_title_pieces or all_topic_pieces), *all_pair_pieces]


def _note_output(kind: str, all_pieces: list[str]) -> dict[str, object]:
    note_text = NOTE_TEMPLATE.format(
        kind=kind,
        pieces=PIECE_SEPARATOR.join(all_pieces),
        next_command=ALL_NEXT_COMMAND_BY_KIND[kind],
    )
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: PRE_TOOL_USE_EVENT_NAME,
            ADDITIONAL_CONTEXT_KEY: note_text,
        }
    }


def _is_scannable_command(command: object) -> bool:
    return (
        isinstance(command, str)
        and len(command) <= MAXIMUM_COMMAND_CHARACTERS
        and any(each_word in command for each_word in ALL_QUICK_SCAN_WORDS)
    )


def _shell_note(command: object, working_directory: str) -> dict[str, object] | None:
    if not isinstance(command, str) or not _is_scannable_command(command):
        return None
    all_commit_pieces = commit_pieces(command, working_directory)
    if all_commit_pieces:
        return _note_output(COMMIT_KIND, all_commit_pieces)
    for each_title, each_body in commit_and_pull_request_words.pull_request_words(
        command, working_directory
    ):
        all_pieces = pull_request_pieces(each_title, each_body)
        if all_pieces:
            return _note_output(PULL_REQUEST_KIND, all_pieces)
    return None


def _text_field(all_fields: dict[str, object], field_name: str) -> str | None:
    field_text = all_fields.get(field_name)
    return field_text if isinstance(field_text, str) else None


def decide_hook_output(all_hook_fields: dict[str, object]) -> dict[str, object] | None:
    """Return the note as additionalContext output, or None to stay quiet.

    Args:
        all_hook_fields: The parsed PreToolUse payload.

    Returns:
        The ``hookSpecificOutput`` object with the note, or None when the call
        is no commit or pull request create, or its words name one piece.
        The output never carries a permission decision.
    """
    all_tool_input = all_hook_fields.get(TOOL_INPUT_KEY)
    tool_name = all_hook_fields.get(TOOL_NAME_KEY)
    if not isinstance(all_tool_input, dict) or not isinstance(tool_name, str):
        return None
    working_directory = all_hook_fields.get(WORKING_DIRECTORY_KEY)
    if tool_name in SHELL_TOOL_NAMES:
        return _shell_note(
            all_tool_input.get(COMMAND_INPUT_KEY),
            working_directory if isinstance(working_directory, str) else "",
        )
    if not tool_name.endswith(CREATE_PULL_REQUEST_TOOL_SUFFIX):
        return None
    all_pieces = pull_request_pieces(
        _text_field(all_tool_input, TITLE_INPUT_KEY), _text_field(all_tool_input, BODY_INPUT_KEY)
    )
    return _note_output(PULL_REQUEST_KIND, all_pieces) if all_pieces else None


def main() -> int:
    """Read the PreToolUse payload and print the note when the words name several pieces.

    Returns:
        0 in every case; the note travels in the JSON output.
    """
    return run_context_hook(decide_hook_output)
