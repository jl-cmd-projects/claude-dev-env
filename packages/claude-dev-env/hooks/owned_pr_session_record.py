"""Session record of the owned pull requests an agent opened.

The owned pull request review-loop hook writes each pull request it reports
into one JSON file per session in the system temp folder. The owned pull
request Stop gate reads the same file back::

    owned-pr-loop-<session id>.json
    [{"owner": "acme", "repository": "widgets", "number": "42",
      "url": "https://github.com/acme/widgets/pull/42"}]

Both Claude Code and Codex send ``session_id`` to PostToolUse and Stop hooks,
so the file links the two hooks on either host.
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
)
from hooks_constants.session_file_id import session_file_id

__all__ = ["session_record_path", "all_recorded_pull_requests", "record_pull_request"]


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
