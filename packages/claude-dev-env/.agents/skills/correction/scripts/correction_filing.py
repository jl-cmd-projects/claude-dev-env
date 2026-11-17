"""Post a user's correction as a `correction` issue on the corrected repository, or list them.

The issue goes to the GitHub repository of the checkout the corrected work
lives in: ``--checkout``, else the working directory. A worktree resolves to
its repository through its ``origin`` remote::

    python correction_filing.py file --checkout . <<'BRIEF'
    Correction: stop opening a pull request after a correction
    ...
    BRIEF
    Filed: https://github.com/owner/name/issues/12
    python correction_filing.py file --checkout . <<'BRIEF'
    (the same brief again)
    BRIEF
    Already filed: https://github.com/owner/name/issues/12
    python correction_filing.py list --checkout .
    #12 Correction: stop opening a pull request after a correction https://github.com/...

When the checkout has no GitHub origin, or the repository is unreachable or has
issues turned off, the script files on the correction inbox that
``~/.claude/correction-capture.json`` names (``{"repository": "owner/name"}``,
or the file CLAUDE_CORRECTION_CAPTURE_PATH names) and says why on the result
line. With no usable inbox it files nothing and exits 1 with every reason.

Before each post the script masks tokens and email addresses, and in a public
repository also machine paths, local account names, and links to other GitHub
repositories. It runs the managed ``scripts/durable_post_lint.py`` (under
CLAUDE_CONFIG_DIR, else ``~/.claude``) on the body and posts only on a clean
result. It creates the ``correction`` label when the repository lacks it.
``--preamble-file`` puts sections a repository's own issue rules require above
the correction.

A hidden marker keys the issue on the brief's ``Correction:`` line (or
``--dedupe-key``), and another on the whole text. The same text again prints
``Already filed``. A new text for the same correction comments a repeat on the
open issue, or files a new issue that links the closed one. A local ledger
beside the config file covers the minute after filing, when the labeled-issue
listing can miss a new issue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from correction_filing_constants.config.constants import (
    ACCOUNT_NAME_PATTERN_TEMPLATE,
    ACCOUNT_NAME_MINIMUM_LENGTH,
    ALL_ACCOUNT_NAME_ENV_VARS,
    ALL_GH_COMMAND_PARTS,
    ALL_POST_LINT_PATH_PARTS,
    ALL_PUBLIC_REDACTION_PATTERNS,
    ALL_REDACTION_PATTERNS,
    ALL_SOURCES,
    BODY_FIELD_TEMPLATE,
    CLAUDE_DIRECTORY_NAME,
    CONFIG_ENCODING,
    CONFIG_FILE_NAME,
    CONFIG_PATH_ENV_VAR,
    CONFIG_REPOSITORY_KEY,
    CORRECTION_LABEL,
    CORRECTION_LINE_PATTERN,
    CREATED_URL_JQ_FILTER,
    DEDUPE_KEY_LENGTH,
    DEDUPE_MARKER_PATTERN,
    DEDUPE_MARKER_TEMPLATE,
    DEFAULT_SOURCE,
    DUPLICATE_MESSAGE_TEMPLATE,
    EMPTY_TEXT_MESSAGE,
    FAILURE_EXIT_CODE,
    FALLBACK_NOTE_TEMPLATE,
    FILED_MESSAGE_TEMPLATE,
    FILED_REPEAT_MESSAGE_TEMPLATE,
    GIT_EXECUTABLE,
    GITHUB_ORIGIN_PATTERN,
    GITHUB_URL_PATTERN,
    ISSUE_BODY_TEMPLATE,
    ISSUE_COMMENTS_PATH_TEMPLATE,
    ISSUE_TITLE_PREFIX,
    ISSUE_TITLE_TEXT_LENGTH,
    ISSUES_CREATE_PATH_TEMPLATE,
    ISSUES_LIST_JQ_FILTER,
    ISSUES_LIST_PATH_TEMPLATE,
    LABEL_COLOR,
    LABEL_CREATE_PATH_TEMPLATE,
    LABEL_DESCRIPTION,
    LABEL_FIELD_TEMPLATE,
    LABEL_PATH_TEMPLATE,
    LEDGER_FILE_NAME,
    LEDGER_KEY_TEMPLATE,
    LINE_SEPARATOR,
    LIST_FALLBACK_LINE_TEMPLATE,
    LIST_LINE_TEMPLATE,
    MANAGED_ROOT_ENV_VAR,
    NO_OPEN_CORRECTIONS_MESSAGE,
    NO_TARGET_MESSAGE_TEMPLATE,
    OCCURRENCE_MARKER_TEMPLATE,
    PREAMBLE_SEPARATOR,
    ORIGIN_REMOTE_NAME,
    POST_LINT_ACTION_COMMENT,
    POST_LINT_ACTION_CREATE,
    POST_LINT_BODY_FILE_NAME,
    POST_LINT_MISSING_MESSAGE_TEMPLATE,
    POST_LINT_REFUSED_MESSAGE_TEMPLATE,
    REASON_ISSUES_OFF_TEMPLATE,
    REASON_NO_ORIGIN_TEMPLATE,
    REASON_NOT_GITHUB_TEMPLATE,
    REASON_SEPARATOR,
    REASON_UNREACHABLE_TEMPLATE,
    REDACTION_PLACEHOLDER,
    REPEAT_COMMENT_TEMPLATE,
    REPEAT_LINE_TEMPLATE,
    REPEAT_MARKED_MESSAGE_TEMPLATE,
    REPOSITORY_PROBE_JQ_FILTER,
    REPOSITORY_PROBE_PATH_TEMPLATE,
    STATE_ALL,
    STATE_OPEN,
    SUCCESS_EXIT_CODE,
    TITLE_FIELD_TEMPLATE,
    UTF8_ENCODING,
    WORD_SEPARATOR,
)


@dataclass(frozen=True)
class FilingTarget:
    """The repository a correction files into, and why it is not the corrected one."""

    repository: str
    is_public: bool
    all_fallback_reasons: tuple[str, ...]

    def fallback_note(self) -> str:
        """Name the fallback for the printed line.

        Returns:
            The fallback note, or empty on the corrected repository.
        """
        if not self.all_fallback_reasons:
            return ""
        return FALLBACK_NOTE_TEMPLATE.format(
            reasons=REASON_SEPARATOR.join(self.all_fallback_reasons), inbox=self.repository
        )


@dataclass(frozen=True)
class FiledIssue:
    """One labeled issue as the listing returns it."""

    number: int
    title: str
    url: str
    body: str
    state: str


class FilingRunFatal(ValueError):
    """Stop the run with a message that says why nothing was filed."""


class RepositoryUnusable(ValueError):
    """Name why one candidate repository cannot take the correction."""


def _config_path() -> Path:
    """Return the config path from the environment, or the default under ~/.claude."""
    configured_path = os.environ.get(CONFIG_PATH_ENV_VAR, "")
    if configured_path:
        return Path(configured_path)
    return Path.home() / CLAUDE_DIRECTORY_NAME / CONFIG_FILE_NAME


def _inbox_repository(from_path: Path) -> str:
    """Return the fallback inbox repository from the config file, or empty."""
    try:
        parsed_config = json.loads(from_path.read_text(encoding=CONFIG_ENCODING))
    except (OSError, ValueError):
        return ""
    if not isinstance(parsed_config, dict):
        return ""
    repository = parsed_config.get(CONFIG_REPOSITORY_KEY, "")
    return repository if isinstance(repository, str) else ""


def _run_gh(all_arguments: list[str]) -> str:
    completed_process = subprocess.run(
        [*ALL_GH_COMMAND_PARTS, *all_arguments],
        capture_output=True,
        text=True,
        encoding=UTF8_ENCODING,
        check=True,
    )
    return completed_process.stdout


def github_repository_from_origin(origin_url: str) -> str:
    """Return ``owner/name`` for a GitHub remote URL, or empty for another host.

    Args:
        origin_url: an https, ssh, or scp-style remote URL.

    Returns:
        The repository slug, or an empty string.
    """
    origin_match = re.match(GITHUB_ORIGIN_PATTERN, origin_url.strip())
    if origin_match is None:
        return ""
    return f"{origin_match.group(1)}/{origin_match.group(2)}"


def _checkout_repository(checkout: Path) -> str:
    """Return the GitHub repository of a checkout or worktree through its origin remote."""
    try:
        origin_url = subprocess.run(
            [GIT_EXECUTABLE, "-C", str(checkout), "remote", "get-url", ORIGIN_REMOTE_NAME],
            capture_output=True,
            text=True,
            encoding=UTF8_ENCODING,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise RepositoryUnusable(REASON_NO_ORIGIN_TEMPLATE.format(checkout=checkout)) from error
    repository = github_repository_from_origin(origin_url)
    if not repository:
        raise RepositoryUnusable(REASON_NOT_GITHUB_TEMPLATE.format(origin_url=origin_url))
    return repository


def _postable_target(repository: str, all_earlier_reasons: tuple[str, ...]) -> FilingTarget:
    """Return the target when the repository is reachable and takes issues."""
    try:
        repository_probe_json = _run_gh(
            [
                "api",
                REPOSITORY_PROBE_PATH_TEMPLATE.format(repository=repository),
                "--jq",
                REPOSITORY_PROBE_JQ_FILTER,
            ]
        )
    except subprocess.CalledProcessError as error:
        all_detail_lines = (error.stderr or str(error)).strip().splitlines() or [str(error)]
        raise RepositoryUnusable(
            REASON_UNREACHABLE_TEMPLATE.format(repository=repository, detail=all_detail_lines[0])
        ) from error
    except OSError as error:
        raise RepositoryUnusable(
            REASON_UNREACHABLE_TEMPLATE.format(repository=repository, detail=error)
        ) from error
    repository_facts = json.loads(repository_probe_json)
    if not repository_facts.get("has_issues"):
        raise RepositoryUnusable(REASON_ISSUES_OFF_TEMPLATE.format(repository=repository))
    return FilingTarget(
        repository=repository,
        is_public=not repository_facts.get("private"),
        all_fallback_reasons=all_earlier_reasons,
    )


def _resolve_filing_target(checkout: Path, config_path: Path) -> FilingTarget:
    """Pick the corrected checkout's repository, else the config file's inbox.

    Args:
        checkout: the checkout or worktree the corrected work lives in.
        config_path: the private config file naming the fallback inbox.

    Returns:
        The target, with the reasons each skipped repository gave.

    Raises:
        FilingRunFatal: no candidate repository can take the correction.
    """
    all_reasons: list[str] = []
    try:
        return _postable_target(_checkout_repository(checkout), ())
    except RepositoryUnusable as error:
        all_reasons.append(str(error))
    inbox_repository = _inbox_repository(config_path)
    if inbox_repository:
        try:
            return _postable_target(inbox_repository, tuple(all_reasons))
        except RepositoryUnusable as error:
            all_reasons.append(str(error))
    raise FilingRunFatal(
        NO_TARGET_MESSAGE_TEMPLATE.format(
            reasons=REASON_SEPARATOR.join(all_reasons), config_path=config_path
        )
    )


def _local_account_names() -> set[str]:
    all_names = {os.environ.get(each_name, "") for each_name in ALL_ACCOUNT_NAME_ENV_VARS}
    all_names.add(Path.home().name)
    return {each_name for each_name in all_names if len(each_name) >= ACCOUNT_NAME_MINIMUM_LENGTH}


def _redact_for(text: str, target: FilingTarget) -> str:
    """Mask secrets and email addresses, and in a public repository personal detail too.

    Args:
        text: the correction text or a preamble.
        target: the repository the text posts to.

    Returns:
        The text, each masked span now the placeholder.
    """
    redacted_text = text
    for each_pattern in ALL_REDACTION_PATTERNS:
        redacted_text = re.sub(each_pattern, REDACTION_PLACEHOLDER, redacted_text)
    if not target.is_public:
        return redacted_text
    for each_pattern in ALL_PUBLIC_REDACTION_PATTERNS:
        redacted_text = re.sub(each_pattern, REDACTION_PLACEHOLDER, redacted_text)
    redacted_text = re.sub(
        GITHUB_URL_PATTERN,
        lambda url_match: url_match.group(0)
        if url_match.group(1).lower() == target.repository.lower()
        else REDACTION_PLACEHOLDER,
        redacted_text,
    )
    for each_name in _local_account_names():
        redacted_text = re.sub(
            ACCOUNT_NAME_PATTERN_TEMPLATE.format(name=re.escape(each_name)),
            REDACTION_PLACEHOLDER,
            redacted_text,
            flags=re.IGNORECASE,
        )
    return redacted_text


def _correction_line(correction_text: str) -> str:
    line_match = re.search(CORRECTION_LINE_PATTERN, correction_text, flags=re.MULTILINE)
    return line_match.group(1) if line_match else correction_text


def _key_for(key_source: str) -> str:
    collapsed_source = WORD_SEPARATOR.join(key_source.split())
    return hashlib.sha256(collapsed_source.encode(UTF8_ENCODING)).hexdigest()[:DEDUPE_KEY_LENGTH]


def issue_title_for(correction_text: str) -> str:
    """Return a one-line issue title cut from the brief's Correction line, or the text.

    Args:
        correction_text: the redacted brief or raw correction.

    Returns:
        The prefix and the first characters of the correction on one line.
    """
    single_line_text = WORD_SEPARATOR.join(_correction_line(correction_text).split())
    return ISSUE_TITLE_PREFIX + single_line_text[:ISSUE_TITLE_TEXT_LENGTH]


def _quoted(correction_text: str) -> str:
    return LINE_SEPARATOR.join("> " + each_line for each_line in correction_text.splitlines())


def _list_labeled_issues(repository: str, state: str) -> list[FiledIssue]:
    issues_path = ISSUES_LIST_PATH_TEMPLATE.format(
        repository=repository, label=quote(CORRECTION_LABEL), state=state
    )
    issue_lines = _run_gh(["api", "--paginate", issues_path, "--jq", ISSUES_LIST_JQ_FILTER])
    all_issues = []
    for each_line in issue_lines.splitlines():
        if not each_line.strip():
            continue
        each_issue = json.loads(each_line)
        all_issues.append(
            FiledIssue(
                number=int(each_issue["number"]),
                title=str(each_issue.get("title") or ""),
                url=str(each_issue["url"]),
                body=str(each_issue.get("body") or ""),
                state=str(each_issue.get("state") or STATE_OPEN),
            )
        )
    return all_issues


def _ensure_label(repository: str) -> None:
    try:
        _run_gh(
            ["api", LABEL_PATH_TEMPLATE.format(repository=repository, label=quote(CORRECTION_LABEL))]
        )
    except subprocess.CalledProcessError:
        _run_gh(
            [
                "api",
                "--method",
                "POST",
                LABEL_CREATE_PATH_TEMPLATE.format(repository=repository),
                "-f",
                f"name={CORRECTION_LABEL}",
                "-f",
                f"color={LABEL_COLOR}",
                "-f",
                f"description={LABEL_DESCRIPTION}",
            ]
        )


def _post_lint_path() -> Path:
    managed_root = os.environ.get(MANAGED_ROOT_ENV_VAR, "") or str(
        Path.home() / CLAUDE_DIRECTORY_NAME
    )
    return Path(managed_root).joinpath(*ALL_POST_LINT_PATH_PARTS)


def _lint_post(action: str, body: str, repository: str) -> None:
    """Run the managed durable post lint on the body, and stop on any finding."""
    lint_path = _post_lint_path()
    if not lint_path.is_file():
        raise FilingRunFatal(POST_LINT_MISSING_MESSAGE_TEMPLATE.format(path=lint_path))
    with tempfile.TemporaryDirectory() as body_directory:
        body_path = Path(body_directory) / POST_LINT_BODY_FILE_NAME
        body_path.write_text(body, encoding=UTF8_ENCODING)
        body_check_process = subprocess.run(
            [
                sys.executable,
                str(lint_path),
                "--action",
                action,
                "--body-file",
                str(body_path),
                "--repository",
                repository,
            ],
            capture_output=True,
            text=True,
            encoding=UTF8_ENCODING,
        )
    if body_check_process.returncode != SUCCESS_EXIT_CODE:
        raise FilingRunFatal(
            POST_LINT_REFUSED_MESSAGE_TEMPLATE.format(
                findings=body_check_process.stderr, repository=repository
            )
        )


def _ledger_path() -> Path:
    return _config_path().with_name(LEDGER_FILE_NAME)


def _read_ledger() -> dict[str, str]:
    try:
        parsed_ledger = json.loads(_ledger_path().read_text(encoding=CONFIG_ENCODING))
    except (OSError, ValueError):
        return {}
    return parsed_ledger if isinstance(parsed_ledger, dict) else {}


def _ledger_key_for(repository: str, occurrence_key: str) -> str:
    return LEDGER_KEY_TEMPLATE.format(repository=repository, dedupe_key=occurrence_key)


def _record_in_ledger(repository: str, occurrence_key: str, posted_url: str) -> None:
    url_by_ledger_key = _read_ledger()
    url_by_ledger_key[_ledger_key_for(repository, occurrence_key)] = posted_url
    _ledger_path().parent.mkdir(parents=True, exist_ok=True)
    _ledger_path().write_text(json.dumps(url_by_ledger_key), encoding=CONFIG_ENCODING)


def _earlier_issue(repository: str, correction_key: str) -> FiledIssue | None:
    """Return the open issue for this correction, else the newest closed one, else None."""
    all_matches = [
        each_issue
        for each_issue in _list_labeled_issues(repository, STATE_ALL)
        if (each_match := re.search(DEDUPE_MARKER_PATTERN, each_issue.body))
        and each_match.group(1) == correction_key
    ]
    if not all_matches:
        return None
    all_open_matches = [each_issue for each_issue in all_matches if each_issue.state == STATE_OPEN]
    return max(all_open_matches or all_matches, key=lambda each_issue: each_issue.number)


def _create_issue(target: FilingTarget, title: str, body: str) -> str:
    _lint_post(POST_LINT_ACTION_CREATE, body, target.repository)
    _ensure_label(target.repository)
    return _run_gh(
        [
            "api",
            "--method",
            "POST",
            ISSUES_CREATE_PATH_TEMPLATE.format(repository=target.repository),
            "-f",
            TITLE_FIELD_TEMPLATE.format(value=title),
            "-f",
            BODY_FIELD_TEMPLATE.format(value=body),
            "-f",
            LABEL_FIELD_TEMPLATE.format(value=CORRECTION_LABEL),
            "--jq",
            CREATED_URL_JQ_FILTER,
        ]
    ).strip()


def _comment_repeat(target: FilingTarget, earlier: FiledIssue, body: str) -> str:
    _lint_post(POST_LINT_ACTION_COMMENT, body, target.repository)
    return _run_gh(
        [
            "api",
            "--method",
            "POST",
            ISSUE_COMMENTS_PATH_TEMPLATE.format(repository=target.repository, number=earlier.number),
            "-f",
            BODY_FIELD_TEMPLATE.format(value=body),
            "--jq",
            CREATED_URL_JQ_FILTER,
        ]
    ).strip()


def _file_correction(
    target: FilingTarget, correction_text: str, source: str, supplied_key: str, preamble: str
) -> str:
    """File the correction once on the target and return the result line.

    Args:
        target: the repository and its visibility.
        correction_text: the brief, or a raw correction.
        source: where the correction came from.
        supplied_key: a caller's message id, or empty.
        preamble: sections the repository's issue rules require, or empty.

    Returns:
        The Filed, Repeat marked, or Already filed line, with any fallback note.
    """
    redacted_text = _redact_for(correction_text.strip(), target)
    correction_key = _key_for(supplied_key or _correction_line(redacted_text))
    occurrence_key = _key_for(
        supplied_key + LINE_SEPARATOR + redacted_text if supplied_key else redacted_text
    )
    note = target.fallback_note()
    ledger_url = _read_ledger().get(_ledger_key_for(target.repository, occurrence_key), "")
    if ledger_url:
        return DUPLICATE_MESSAGE_TEMPLATE.format(url=ledger_url, note=note)
    earlier = _earlier_issue(target.repository, correction_key)
    if earlier is not None and occurrence_key in earlier.body:
        return DUPLICATE_MESSAGE_TEMPLATE.format(url=earlier.url, note=note)
    occurrence_marker = OCCURRENCE_MARKER_TEMPLATE.format(key=occurrence_key)
    if earlier is not None and earlier.state == STATE_OPEN:
        comment_url = _comment_repeat(
            target,
            earlier,
            REPEAT_COMMENT_TEMPLATE.format(
                source=source,
                quoted_text=_quoted(redacted_text),
                occurrence_marker=occurrence_marker,
            ),
        )
        _record_in_ledger(target.repository, occurrence_key, earlier.url)
        return REPEAT_MARKED_MESSAGE_TEMPLATE.format(
            issue_url=earlier.url, comment_url=comment_url, note=note
        )
    redacted_preamble = _redact_for(preamble.strip(), target)
    body = ISSUE_BODY_TEMPLATE.format(
        preamble=redacted_preamble + PREAMBLE_SEPARATOR if redacted_preamble else "",
        source=source,
        repeat_line=REPEAT_LINE_TEMPLATE.format(earlier_url=earlier.url) if earlier else "",
        quoted_text=_quoted(redacted_text),
        dedupe_marker=DEDUPE_MARKER_TEMPLATE.format(key=correction_key),
        occurrence_marker=occurrence_marker,
    )
    created_url = _create_issue(target, issue_title_for(redacted_text), body)
    _record_in_ledger(target.repository, occurrence_key, created_url)
    if earlier is not None:
        return FILED_REPEAT_MESSAGE_TEMPLATE.format(
            url=created_url, earlier_url=earlier.url, note=note
        )
    return FILED_MESSAGE_TEMPLATE.format(url=created_url, note=note)


def _open_corrections_listing(target: FilingTarget) -> str:
    """Return one line per open correction issue, or a no-open line, and any fallback line."""
    listing = "".join(
        LIST_LINE_TEMPLATE.format(
            number=each_issue.number, title=each_issue.title, url=each_issue.url
        )
        for each_issue in _list_labeled_issues(target.repository, STATE_OPEN)
    ) or NO_OPEN_CORRECTIONS_MESSAGE
    if target.all_fallback_reasons:
        listing += LIST_FALLBACK_LINE_TEMPLATE.format(
            inbox=target.repository, reasons=REASON_SEPARATOR.join(target.all_fallback_reasons)
        )
    return listing


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Post or list user corrections.")
    all_subcommands = parser.add_subparsers(dest="command", required=True)
    file_parser = all_subcommands.add_parser("file", help="Post one correction.")
    file_parser.add_argument("--checkout", type=Path, default=Path.cwd())
    file_parser.add_argument("--text", default=None)
    file_parser.add_argument("--source", choices=ALL_SOURCES, default=DEFAULT_SOURCE)
    file_parser.add_argument("--dedupe-key", default="")
    file_parser.add_argument("--preamble-file", type=Path, default=None)
    list_parser = all_subcommands.add_parser("list", help="List the open corrections.")
    list_parser.add_argument("--checkout", type=Path, default=Path.cwd())
    return parser


def _run_command(parsed_arguments: argparse.Namespace) -> int:
    if parsed_arguments.command == "list":
        target = _resolve_filing_target(parsed_arguments.checkout, _config_path())
        sys.stdout.write(_open_corrections_listing(target))
        return SUCCESS_EXIT_CODE
    correction_text = (
        sys.stdin.buffer.read().decode(UTF8_ENCODING)
        if parsed_arguments.text is None
        else parsed_arguments.text
    )
    if not correction_text.strip():
        sys.stderr.write(EMPTY_TEXT_MESSAGE)
        return FAILURE_EXIT_CODE
    preamble = (
        parsed_arguments.preamble_file.read_text(encoding=UTF8_ENCODING)
        if parsed_arguments.preamble_file is not None
        else ""
    )
    target = _resolve_filing_target(parsed_arguments.checkout, _config_path())
    sys.stdout.write(
        _file_correction(
            target,
            correction_text,
            parsed_arguments.source,
            parsed_arguments.dedupe_key,
            preamble,
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
        return _run_command(parsed_arguments)
    except FilingRunFatal as error:
        sys.stderr.write(str(error))
        return FAILURE_EXIT_CODE
    except subprocess.CalledProcessError as error:
        sys.stderr.write(error.stderr or str(error))
        return FAILURE_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
