"""File a user's correction as one labeled GitHub issue, or list the open ones.

The repository and label come from a private config file, so nothing
identifying lives in this package::

    ~/.claude/correction-capture.json
    {"repository": "owner/name", "label": "correction"}

    python correction_filing.py file --text "use shorter replies"
    Filed: https://github.com/owner/name/issues/12
    python correction_filing.py file --text "use shorter replies"
    Already filed: https://github.com/owner/name/issues/12
    python correction_filing.py file <<'CORRECTION'
    use shorter replies
    CORRECTION
    Already filed: https://github.com/owner/name/issues/12
    python correction_filing.py list
    #12 Correction: use shorter replies https://github.com/...

The issue quotes only the correction text, with tokens and email addresses
masked. A hidden dedupe marker in the body, and a local ledger of filed keys
beside the config file, keep a replayed correction from filing twice. CLAUDE_CORRECTION_CAPTURE_PATH names another config file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from correction_filing_constants.config.constants import (
    ALL_REDACTION_PATTERNS,
    ALL_SOURCES,
    BODY_FIELD_TEMPLATE,
    CLAUDE_DIRECTORY_NAME,
    CONFIG_ENCODING,
    CONFIG_FILE_NAME,
    CONFIG_LABEL_KEY,
    CONFIG_PATH_ENV_VAR,
    CONFIG_REPOSITORY_KEY,
    CREATED_URL_JQ_FILTER,
    DEDUPE_KEY_LENGTH,
    DEDUPE_MARKER_PATTERN,
    DEDUPE_MARKER_TEMPLATE,
    DEFAULT_SOURCE,
    DUPLICATE_MESSAGE_TEMPLATE,
    EMPTY_TEXT_MESSAGE,
    FAILURE_EXIT_CODE,
    FILED_MESSAGE_TEMPLATE,
    GH_EXECUTABLE,
    LABEL_FIELD_TEMPLATE,
    LINE_SEPARATOR,
    ISSUE_BODY_TEMPLATE,
    ISSUES_CREATE_PATH_TEMPLATE,
    ISSUES_LIST_JQ_FILTER,
    ISSUES_LIST_PATH_TEMPLATE,
    LEDGER_FILE_NAME,
    LEDGER_KEY_TEMPLATE,
    ISSUE_TITLE_PREFIX,
    ISSUE_TITLE_TEXT_LENGTH,
    LIST_LINE_TEMPLATE,
    MISSING_CONFIG_MESSAGE_TEMPLATE,
    NO_OPEN_CORRECTIONS_MESSAGE,
    REDACTION_PLACEHOLDER,
    SUCCESS_EXIT_CODE,
    TITLE_FIELD_TEMPLATE,
    UTF8_ENCODING,
    WORD_SEPARATOR,
)


@dataclass(frozen=True)
class FilingTarget:
    """The repository and label a correction files into."""

    repository: str
    label: str


class FilingConfigMissing(ValueError):
    """Stop the run when the private config file is absent or incomplete."""


def _config_path() -> Path:
    """Return the config path from the environment, or the default under ~/.claude."""
    configured_path = os.environ.get(CONFIG_PATH_ENV_VAR, "")
    if configured_path:
        return Path(configured_path)
    return Path.home() / CLAUDE_DIRECTORY_NAME / CONFIG_FILE_NAME


def load_filing_target(from_path: Path) -> FilingTarget:
    """Read the repository and label from the config file.

    Args:
        from_path: the private config file.

    Returns:
        The repository and label to file into.

    Raises:
        FilingConfigMissing: the file is absent, unreadable, or lacks a key.
    """
    missing_message = MISSING_CONFIG_MESSAGE_TEMPLATE.format(path=from_path)
    try:
        parsed_config = json.loads(from_path.read_text(encoding=CONFIG_ENCODING))
    except (OSError, ValueError) as error:
        raise FilingConfigMissing(missing_message) from error
    if not isinstance(parsed_config, dict):
        raise FilingConfigMissing(missing_message)
    repository = parsed_config.get(CONFIG_REPOSITORY_KEY, "")
    label = parsed_config.get(CONFIG_LABEL_KEY, "")
    if not isinstance(repository, str) or not isinstance(label, str):
        raise FilingConfigMissing(missing_message)
    if not repository or not label:
        raise FilingConfigMissing(missing_message)
    return FilingTarget(repository=repository, label=label)


def _redact_sensitive_text(correction_text: str) -> str:
    """Mask tokens, keys, and email addresses in the correction text."""
    redacted_text = correction_text
    for each_pattern in ALL_REDACTION_PATTERNS:
        redacted_text = re.sub(each_pattern, REDACTION_PLACEHOLDER, redacted_text)
    return redacted_text


def _dedupe_key_for(correction_text: str, supplied_key: str) -> str:
    """Return a hex key that names this correction across replays."""
    key_source = supplied_key or WORD_SEPARATOR.join(correction_text.split())
    full_digest = hashlib.sha256(key_source.encode(UTF8_ENCODING)).hexdigest()
    return full_digest[:DEDUPE_KEY_LENGTH]


def issue_title_for(correction_text: str) -> str:
    """Return a one-line issue title cut from the correction text.

    Args:
        correction_text: the redacted correction.

    Returns:
        The prefix and the first characters of the text on one line.
    """
    single_line_text = WORD_SEPARATOR.join(correction_text.split())
    return ISSUE_TITLE_PREFIX + single_line_text[:ISSUE_TITLE_TEXT_LENGTH]


def issue_body_for(correction_text: str, source: str, dedupe_key: str) -> str:
    """Return the issue body with the quoted correction, its source, and the marker.

    Args:
        correction_text: the redacted correction.
        source: where the correction came from.
        dedupe_key: the hex key the marker carries.

    Returns:
        The markdown issue body.
    """
    quoted_text = LINE_SEPARATOR.join(
        "> " + each_line for each_line in correction_text.splitlines()
    )
    return ISSUE_BODY_TEMPLATE.format(
        source=source,
        quoted_text=quoted_text,
        dedupe_marker=DEDUPE_MARKER_TEMPLATE.format(key=dedupe_key),
    )


def _run_gh(all_arguments: list[str]) -> str:
    completed_process = subprocess.run(
        [GH_EXECUTABLE, *all_arguments],
        capture_output=True,
        text=True,
        encoding=UTF8_ENCODING,
        check=True,
    )
    return completed_process.stdout


def _list_labeled_issues(target: FilingTarget, state: str) -> list[dict[str, object]]:
    """Return the issues carrying the label, with number, title, url, and body."""
    issues_path = ISSUES_LIST_PATH_TEMPLATE.format(
        repository=target.repository, label=quote(target.label), state=state
    )
    issue_lines = _run_gh(["api", "--paginate", issues_path, "--jq", ISSUES_LIST_JQ_FILTER])
    return [json.loads(each_line) for each_line in issue_lines.splitlines() if each_line.strip()]


def _ledger_path() -> Path:
    return _config_path().with_name(LEDGER_FILE_NAME)


def _read_ledger() -> dict[str, str]:
    try:
        parsed_ledger = json.loads(_ledger_path().read_text(encoding=CONFIG_ENCODING))
    except (OSError, ValueError):
        return {}
    return parsed_ledger if isinstance(parsed_ledger, dict) else {}


def _ledger_key_for(target: FilingTarget, dedupe_key: str) -> str:
    return LEDGER_KEY_TEMPLATE.format(repository=target.repository, dedupe_key=dedupe_key)


def _record_in_ledger(target: FilingTarget, dedupe_key: str, issue_url: str) -> None:
    url_by_ledger_key = _read_ledger()
    url_by_ledger_key[_ledger_key_for(target, dedupe_key)] = issue_url
    _ledger_path().write_text(json.dumps(url_by_ledger_key), encoding=CONFIG_ENCODING)


def _find_filed_issue_url(target: FilingTarget, dedupe_key: str) -> str:
    """Return the url of an issue already carrying this dedupe key, or empty."""
    ledger_url = _read_ledger().get(_ledger_key_for(target, dedupe_key), "")
    if ledger_url:
        return ledger_url
    for each_issue in _list_labeled_issues(target, "all"):
        each_match = re.search(DEDUPE_MARKER_PATTERN, str(each_issue.get("body", "")))
        if each_match and each_match.group(1) == dedupe_key:
            return str(each_issue.get("url", ""))
    return ""


def _file_correction(
    target: FilingTarget, correction_text: str, source: str, supplied_key: str
) -> str:
    """File the correction once and return the message to print."""
    redacted_text = _redact_sensitive_text(correction_text.strip())
    dedupe_key = _dedupe_key_for(redacted_text, supplied_key)
    existing_url = _find_filed_issue_url(target, dedupe_key)
    if existing_url:
        return DUPLICATE_MESSAGE_TEMPLATE.format(url=existing_url)
    created_url = _run_gh(
        [
            "api",
            "--method",
            "POST",
            ISSUES_CREATE_PATH_TEMPLATE.format(repository=target.repository),
            "-f",
            TITLE_FIELD_TEMPLATE.format(value=issue_title_for(redacted_text)),
            "-f",
            BODY_FIELD_TEMPLATE.format(value=issue_body_for(redacted_text, source, dedupe_key)),
            "-f",
            LABEL_FIELD_TEMPLATE.format(value=target.label),
            "--jq",
            CREATED_URL_JQ_FILTER,
        ]
    ).strip()
    _record_in_ledger(target, dedupe_key, created_url)
    return FILED_MESSAGE_TEMPLATE.format(url=created_url)


def _open_corrections_listing(target: FilingTarget) -> str:
    """Return one line per open labeled issue, or a no-open line."""
    all_open_issues = _list_labeled_issues(target, "open")
    if not all_open_issues:
        return NO_OPEN_CORRECTIONS_MESSAGE
    return "".join(
        LIST_LINE_TEMPLATE.format(
            number=each_issue["number"],
            title=each_issue["title"],
            url=each_issue["url"],
        )
        for each_issue in all_open_issues
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="File or list user corrections.")
    all_subcommands = parser.add_subparsers(dest="command", required=True)
    file_parser = all_subcommands.add_parser("file", help="File one correction.")
    file_parser.add_argument("--text", default=None)
    file_parser.add_argument("--source", choices=ALL_SOURCES, default=DEFAULT_SOURCE)
    file_parser.add_argument("--dedupe-key", default="")
    all_subcommands.add_parser("list", help="List the open corrections.")
    return parser


def _run_command(target: FilingTarget, parsed_arguments: argparse.Namespace) -> int:
    if parsed_arguments.command == "list":
        sys.stdout.write(_open_corrections_listing(target))
        return SUCCESS_EXIT_CODE
    correction_text = (
        sys.stdin.read() if parsed_arguments.text is None else parsed_arguments.text
    )
    if not correction_text.strip():
        sys.stderr.write(EMPTY_TEXT_MESSAGE)
        return FAILURE_EXIT_CODE
    sys.stdout.write(
        _file_correction(
            target, correction_text, parsed_arguments.source, parsed_arguments.dedupe_key
        )
    )
    return SUCCESS_EXIT_CODE


def main(all_arguments: list[str]) -> int:
    """Run the file or list command.

    Args:
        all_arguments: the command-line arguments after the script name.

    Returns:
        The process exit code.
    """
    parsed_arguments = _build_parser().parse_args(all_arguments)
    try:
        target = load_filing_target(_config_path())
    except FilingConfigMissing as error:
        sys.stderr.write(str(error))
        return FAILURE_EXIT_CODE
    try:
        return _run_command(target, parsed_arguments)
    except subprocess.CalledProcessError as error:
        sys.stderr.write(error.stderr or str(error))
        return FAILURE_EXIT_CODE

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
