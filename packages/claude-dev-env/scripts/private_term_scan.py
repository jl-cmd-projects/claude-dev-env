"""Fail a GitHub event whose text or commits name a private organization.

The workflow ``private-terms.yml`` runs this on pull request, issue, comment,
review, and release events. Each finding names where the text sits and its
line number, never the name itself, so the public log stays clean::

    pull request body: Line 4 names a private organization. ...
    commit 3f2a9c1b77de identity: Line 1 names a private organization. ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from dev_env_scripts_constants.private_term_constants import (
    ALL_COMMIT_IDENTITY_ACCEPTED_ADDRESS_DIGESTS,
    ALL_COMMIT_IDENTITY_ACCEPTED_DIGESTS,
    ALL_EVENT_TEXT_FIELDS,
    ALL_PRIVATE_TERM_DIGESTS,
    ANGLE_BRACKET_ADDRESS_PATTERN,
    ATTRIBUTION_MARKER_FIELD,
    ATTRIBUTION_MARKER_LOGIN_GROUP,
    ATTRIBUTION_MARKER_OBJECT_KEY,
    COMMIT_FIELD_SEPARATOR,
    COMMIT_FIELD_SPLIT_LIMIT,
    COMMIT_IDENTITY_PART,
    COMMIT_LABEL_TEMPLATE,
    COMMIT_LOG_FORMAT,
    COMMIT_MESSAGE_PART,
    COMMIT_RECORD_SEPARATOR,
    FINDING_LINE_TEMPLATE,
    GITHUB_NOREPLY_ADDRESS_PATTERN,
    LEADING_ATTRIBUTION_MARKER_PATTERN,
    LEADING_BLANK_LINES_GROUP,
    MASKED_ADDRESS,
    PRIVATE_TERM_MESSAGE_TEMPLATE,
    PRIVATE_TERM_TEXT_ENCODING,
    PULL_REQUEST_ISSUE_LINK_FIELD,
    PULL_REQUEST_ISSUE_OBJECT_KEY,
    PULL_REQUEST_OPENER_FIELD,
    PULL_REQUEST_OPENER_HANDLE_FIELD,
    SHORT_SHA_LENGTH,
    PrivateTermDigest,
)
from private_terms import private_term_line_numbers


def _findings_for(
    label: str,
    text: str,
    all_term_digests: frozenset[PrivateTermDigest],
) -> list[str]:
    return [
        FINDING_LINE_TEMPLATE.format(
            label=label,
            message=PRIVATE_TERM_MESSAGE_TEMPLATE.format(line_number=each_line_number),
        )
        for each_line_number in private_term_line_numbers(
            text, all_term_digests
        )
    ]


def _blank_author_attribution_marker(
    body: str, all_pull_request_fields: dict[str, object]
) -> str:
    marker_match = re.match(LEADING_ATTRIBUTION_MARKER_PATTERN, body)
    if marker_match is None:
        return body
    author = all_pull_request_fields.get(PULL_REQUEST_OPENER_FIELD)
    author_login = (
        author.get(PULL_REQUEST_OPENER_HANDLE_FIELD) if isinstance(author, dict) else None
    )
    marker_login = marker_match.group(ATTRIBUTION_MARKER_LOGIN_GROUP)
    if not isinstance(author_login, str) or marker_login.lower() != author_login.lower():
        return body
    return marker_match.expand(LEADING_BLANK_LINES_GROUP) + body[marker_match.end() :]


def _is_pull_request_body(
    object_key: str, field: str, all_event_object_fields: dict[str, object]
) -> bool:
    if field != ATTRIBUTION_MARKER_FIELD:
        return False
    if object_key == ATTRIBUTION_MARKER_OBJECT_KEY:
        return True
    return (
        object_key == PULL_REQUEST_ISSUE_OBJECT_KEY
        and PULL_REQUEST_ISSUE_LINK_FIELD in all_event_object_fields
    )


def scan_event(event_path: Path) -> list[str]:
    """Return findings for the texts a GitHub event payload carries.

    Args:
        event_path: Path of the event JSON the runner writes.

    Returns:
        One finding per line that names a private organization. The first
        non-blank line of a pull request body is left out of the scan when
        it is the whole platform attribution marker and its login matches
        the pull request author's ``user.login``, ignoring case, since that
        login is already public as the author::

            <!-- claude-projects-attribution: {"github_login":"pat"} -->

        A comment event on a pull request carries that body as
        ``issue.body``, with a ``pull_request`` key on the issue, so the
        same rule applies there with ``issue.user.login`` as the author.
        A plain issue body is scanned in full.

        The line keeps its place, so later line numbers do not move. A marker
        whose login is not the author, the same login on any other line, in
        any other field, or beside other text on that line still fails.
    """
    event = json.loads(event_path.read_text(encoding=PRIVATE_TERM_TEXT_ENCODING))
    all_findings: list[str] = []
    for each_object_key, each_field, each_label in ALL_EVENT_TEXT_FIELDS:
        event_object = event.get(each_object_key)
        if not isinstance(event_object, dict):
            continue
        text = event_object.get(each_field)
        if not isinstance(text, str):
            continue
        if _is_pull_request_body(each_object_key, each_field, event_object):
            text = _blank_author_attribution_marker(text, event_object)
        all_findings.extend(_findings_for(each_label, text, ALL_PRIVATE_TERM_DIGESTS))
    return all_findings


def _mask_accepted_address(address_match: re.Match[str]) -> str:
    address = address_match.group(1)
    if address.isascii():
        address_digest = hashlib.sha256(
            address.lower().encode(PRIVATE_TERM_TEXT_ENCODING)
        ).hexdigest()
        if address_digest in ALL_COMMIT_IDENTITY_ACCEPTED_ADDRESS_DIGESTS:
            return MASKED_ADDRESS
    return address_match.group(0)


def _identity_text_to_scan(identity: str) -> str:
    return re.sub(
        ANGLE_BRACKET_ADDRESS_PATTERN,
        _mask_accepted_address,
        re.sub(GITHUB_NOREPLY_ADDRESS_PATTERN, MASKED_ADDRESS, identity, flags=re.IGNORECASE),
    )


def _commit_findings(record: str) -> list[str]:
    full_sha, identity, message = record.split(
        COMMIT_FIELD_SEPARATOR, COMMIT_FIELD_SPLIT_LIMIT
    )
    short_sha = full_sha[:SHORT_SHA_LENGTH]
    return [
        *_findings_for(
            COMMIT_LABEL_TEMPLATE.format(short_sha=short_sha, part=COMMIT_IDENTITY_PART),
            _identity_text_to_scan(identity),
            ALL_PRIVATE_TERM_DIGESTS - ALL_COMMIT_IDENTITY_ACCEPTED_DIGESTS,
        ),
        *_findings_for(
            COMMIT_LABEL_TEMPLATE.format(short_sha=short_sha, part=COMMIT_MESSAGE_PART),
            message,
            ALL_PRIVATE_TERM_DIGESTS,
        ),
    ]


def scan_commits(repository_root: Path, commit_range: str) -> list[str]:
    """Return findings for commit messages and identities in a range, oldest first.

    Args:
        repository_root: Git checkout holding the range.
        commit_range: A ``base..head`` revision range.

    Returns:
        One finding per commit identity or message line that names a private
        organization. An identity address ending in users.noreply.github.com
        is left out of the scan, since GitHub builds it from the account handle.
        An identity address whose lower-case spelling matches an accepted
        address digest is left out the same way, so the shared agent account
        passes while another address at the same organization still fails.
        The owner's own handle passes in an identity and still fails in a
        message.
    """
    log_text = subprocess.run(
        ["git", "-C", str(repository_root), "log", "--reverse", COMMIT_LOG_FORMAT, commit_range],
        check=True,
        capture_output=True,
        encoding=PRIVATE_TERM_TEXT_ENCODING,
    ).stdout
    return [
        each_finding
        for each_record in log_text.split(COMMIT_RECORD_SEPARATOR)
        if each_record.strip()
        for each_finding in _commit_findings(each_record.strip())
    ]


def main(all_arguments: Sequence[str]) -> int:
    """Print every finding and return 1 when any text names a private organization.

    Args:
        all_arguments: Command-line arguments after the script name.

    Returns:
        0 for a clean event, 1 when any finding printed.
    """
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--event-path", type=Path, required=True)
    parser.add_argument("--commit-range")
    arguments = parser.parse_args(list(all_arguments))
    all_findings = scan_event(arguments.event_path)
    if arguments.commit_range:
        all_findings.extend(scan_commits(Path.cwd(), arguments.commit_range))
    for each_finding in all_findings:
        print(each_finding)
    return 1 if all_findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
