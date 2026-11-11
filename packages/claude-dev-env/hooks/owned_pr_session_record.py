"""Session record of the owned pull requests an agent opened.

The owned pull request review-loop hook writes each pull request it reports
into one JSON file per session in the system temp folder. The owned pull
request Stop gate reads the same file back::

    owned-pr-loop-<session id>.json
    [{"owner": "acme", "repository": "widgets", "number": "42",
      "url": "https://github.com/acme/widgets/pull/42"}]

Both Claude Code and Codex send ``session_id`` to PostToolUse and Stop hooks,
so the file links the two hooks on either host.

The Stop gate keeps its own file of the head it last blocked on for each
pull request, so it blocks once per head::

    owned-pr-stop-blocks-<session id>.json
    {"https://github.com/acme/widgets/pull/42": "<head sha>"}
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from atomic_file_writer import write_text_atomically
from hooks_constants.atomic_file_writer_constants import ATOMIC_WRITE_TEMPORARY_SUFFIX
from hooks_constants.owned_pr_review_loop_constants import (
    ALL_PULL_REQUEST_FIELD_NAMES,
    NAME_DIGEST_TEXT_ENCODING,
    SESSION_RECORD_FILE_TEMPLATE,
    SESSION_RECORD_TEMPORARY_PREFIX,
    STOP_BLOCK_RECORD_FILE_TEMPLATE,
    STOP_BLOCK_RECORD_TEMPORARY_PREFIX,
)
from hooks_constants.session_file_id import session_file_id

__all__ = [
    "session_record_path",
    "all_recorded_pull_requests",
    "record_pull_request",
    "stop_block_record_path",
    "all_blocked_heads",
    "record_blocked_heads",
]


def session_record_path(session_id: object) -> Path:
    """Return the record file path for one session.

    Args:
        session_id: The ``session_id`` field of the hook payload.
    """
    file_name = SESSION_RECORD_FILE_TEMPLATE.format(session_file_id=session_file_id(session_id))
    return Path(tempfile.gettempdir()) / file_name


def _is_session_id(session_id: object) -> bool:
    return isinstance(session_id, str) and bool(session_id)


def _is_pull_request_entry(entry: object) -> bool:
    return isinstance(entry, dict) and all(
        isinstance(entry.get(each_field), str) for each_field in ALL_PULL_REQUEST_FIELD_NAMES
    )


def all_recorded_pull_requests(session_id: object) -> list[dict[str, str]]:
    """Return the pull requests recorded for the session, oldest first.

    A payload with no session id, or a missing, unreadable, or malformed
    file, reads as an empty record.

    Args:
        session_id: The ``session_id`` field of the hook payload.
    """
    if not _is_session_id(session_id):
        return []
    try:
        record_text = session_record_path(session_id).read_text(encoding=NAME_DIGEST_TEXT_ENCODING)
        all_entries = json.loads(record_text)
    except (OSError, ValueError):
        return []
    if not isinstance(all_entries, list):
        return []
    return [each_entry for each_entry in all_entries if _is_pull_request_entry(each_entry)]


def record_pull_request(session_id: object, all_pull_request_fields: dict[str, str]) -> None:
    """Add one pull request to the session record, once per url.

    A payload with no session id records nothing. A write that fails leaves
    the record as it was, so the PostToolUse hook still adds its context.

    Args:
        session_id: The ``session_id`` field of the hook payload.
        all_pull_request_fields: The owner, repository, number, and url fields.
    """
    if not _is_session_id(session_id):
        return
    all_entries = all_recorded_pull_requests(session_id)
    if any(each_entry["url"] == all_pull_request_fields["url"] for each_entry in all_entries):
        return
    new_entry = {
        each_field: all_pull_request_fields[each_field]
        for each_field in ALL_PULL_REQUEST_FIELD_NAMES
    }
    try:
        write_text_atomically(
            session_record_path(session_id),
            json.dumps([*all_entries, new_entry]),
            NAME_DIGEST_TEXT_ENCODING,
            SESSION_RECORD_TEMPORARY_PREFIX,
            ATOMIC_WRITE_TEMPORARY_SUFFIX,
            False,
        )
    except (OSError, UnicodeError):
        return


def stop_block_record_path(session_id: object) -> Path:
    """Return the file that maps each pull request url to the head the Stop gate last blocked on.

    Args:
        session_id: The ``session_id`` field of the hook payload.
    """
    file_name = STOP_BLOCK_RECORD_FILE_TEMPLATE.format(session_file_id=session_file_id(session_id))
    return Path(tempfile.gettempdir()) / file_name


def all_blocked_heads(session_id: object) -> dict[str, str]:
    """Return the head sha the Stop gate last blocked on, keyed by pull request url.

    A payload with no session id, or a missing, unreadable, or malformed
    file, reads as no blocks.

    Args:
        session_id: The ``session_id`` field of the hook payload.
    """
    if not _is_session_id(session_id):
        return {}
    try:
        record_text = stop_block_record_path(session_id).read_text(encoding=NAME_DIGEST_TEXT_ENCODING)
        all_heads_by_url = json.loads(record_text)
    except (OSError, ValueError):
        return {}
    if not isinstance(all_heads_by_url, dict):
        return {}
    return {
        each_url: each_head
        for each_url, each_head in all_heads_by_url.items()
        if isinstance(each_url, str) and isinstance(each_head, str)
    }


def record_blocked_heads(session_id: object, all_heads_by_url: dict[str, str]) -> None:
    """Record the head sha each pull request was blocked on, keeping the other entries.

    A payload with no session id records nothing. A write that fails leaves
    the record as it was, so the gate blocks again on the next stop.

    Args:
        session_id: The ``session_id`` field of the hook payload.
        all_heads_by_url: The head sha to record for each pull request url.
    """
    if not _is_session_id(session_id):
        return
    try:
        write_text_atomically(
            stop_block_record_path(session_id),
            json.dumps({**all_blocked_heads(session_id), **all_heads_by_url}),
            NAME_DIGEST_TEXT_ENCODING,
            STOP_BLOCK_RECORD_TEMPORARY_PREFIX,
            ATOMIC_WRITE_TEMPORARY_SUFFIX,
            False,
        )
    except (OSError, UnicodeError):
        return
