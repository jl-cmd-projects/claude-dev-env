"""Append-only ledger of non-breaking findings awaiting a follow-up fix.

A gate that finds a breaking defect stops the commit, the push, or the tool
call. A gate that finds a non-breaking smell records the finding here and lets
the work proceed. ``cde followup`` reads the ledger and briefs the agent that
fixes the recorded smells in their own pull request.

Every write is fail-safe. A ledger that cannot be created or appended to leaves
the calling gate's decision unchanged, so recording a finding never becomes a
new way for a gate to fail.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

_hooks_directory = str(Path(__file__).resolve().parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

from hooks_constants.followup_ledger_constants import (
    ABSENT_ORIGIN_COMMIT,
    ALL_FOLLOWUP_LEDGER_PATH_SEGMENTS,
    CHECK_ID_KEY,
    FILE_PATH_KEY,
    GIT_COMMON_DIRECTORY_FILE_NAME,
    GIT_DIRECTORY_FILE_PREFIX,
    GIT_DIRECTORY_NAME,
    GIT_HEAD_FILE_NAME,
    GIT_PACKED_REFERENCES_COMMENT_PREFIX,
    GIT_PACKED_REFERENCES_FILE_NAME,
    GIT_PACKED_REFERENCES_PEELED_PREFIX,
    GIT_REFERENCE_PREFIX,
    LEDGER_APPEND_MODE,
    LEDGER_ENCODING,
    LEDGER_IGNORE_FILE_NAME,
    LEDGER_IGNORE_TEXT,
    MESSAGE_KEY,
    ORIGIN_COMMIT_KEY,
    RULE_ID_KEY,
    SEVERITY_KEY,
    SEVERITY_SMELL,
)


class FollowupFinding(NamedTuple):
    """One non-breaking finding a later pull request resolves.

    Attributes:
        rule_id: Identifier of the rule that raised the finding.
        file_path: Repository-relative path the finding names.
        message: The text a reader acts on.
        check_id: Identifier of the single check behind the finding. An empty
            value reads back as the rule identifier.
        severity: The class the gate put the finding in.
        origin_commit: The revision checked out when the finding was recorded,
            which groups a follow-up pull request by the change that raised it.
    """

    rule_id: str
    file_path: str
    message: str
    check_id: str = ""
    severity: str = SEVERITY_SMELL
    origin_commit: str = ABSENT_ORIGIN_COMMIT

    def tracking_key(self) -> tuple[str, str, str]:
        """Return the fields that make this finding the same one over time.

        The origin commit stays out of the key, so a smell seen again under a
        later revision keeps the revision that first raised it.

        Returns:
            The check identifier, path, and message.
        """
        return (self.check_id or self.rule_id, self.file_path, self.message)


def deduplicated_lines(all_lines: Sequence[str]) -> list[str]:
    """Return the lines with every exact repeat removed.

    The first occurrence of each line keeps its place, so the ledger keeps its
    record order after a ``merge=union`` merge writes both sides' lines.

    Args:
        all_lines: The ledger lines, in file order.

    Returns:
        The lines in file order, each exact line once.
    """
    return list(dict.fromkeys(all_lines))


def deduplicate_ledger(repository_root: Path) -> int:
    """Rewrite the repository's ledger without exact repeated lines.

    An absent or unreadable ledger, and a ledger that cannot be rewritten, are
    left as they are, so a ledger failure never becomes a gate failure.

    Args:
        repository_root: The repository whose ledger to clean.

    Returns:
        How many lines the rewrite removed.
    """
    ledger_path = followup_ledger_path(repository_root)
    try:
        all_ledger_lines = ledger_path.read_text(encoding=LEDGER_ENCODING).splitlines()
    except (OSError, UnicodeError):
        return 0
    all_unique_lines = deduplicated_lines(all_ledger_lines)
    removed_line_count = len(all_ledger_lines) - len(all_unique_lines)
    if not removed_line_count:
        return 0
    try:
        ledger_path.write_text(
            "".join(each_line + "\n" for each_line in all_unique_lines),
            encoding=LEDGER_ENCODING,
        )
    except OSError:
        return 0
    return removed_line_count


def followup_ledger_path(repository_root: Path) -> Path:
    """Return the ledger path for one repository.

    Args:
        repository_root: The repository whose ledger to address.

    Returns:
        The absolute path of that repository's follow-up ledger.
    """
    return repository_root.joinpath(*ALL_FOLLOWUP_LEDGER_PATH_SEGMENTS)


def record_followup_finding(repository_root: Path, finding: FollowupFinding) -> None:
    """Append one finding to the repository's ledger, once.

    The ledger first loses every exact repeated line, so lines a
    ``merge=union`` merge wrote twice leave on the next write. A finding
    already present in the ledger is left alone, so a gate that runs on every
    commit records a standing smell a single time. The ledger
    directory carries a ``.gitignore`` matching every file in it, so the
    ledger stays out of ``git status`` in any repository. Every filesystem
    error is swallowed, so a ledger failure leaves the caller's gate decision
    unchanged.

    Args:
        repository_root: The repository whose ledger receives the finding.
        finding: The non-breaking finding to record.
    """
    deduplicate_ledger(repository_root)
    all_recorded_keys = {
        each_finding.tracking_key()
        for each_finding in all_recorded_findings(repository_root)
    }
    if finding.tracking_key() in all_recorded_keys:
        return

    ledger_path = followup_ledger_path(repository_root)
    record_text = json.dumps(
        {
            RULE_ID_KEY: finding.rule_id,
            FILE_PATH_KEY: finding.file_path,
            MESSAGE_KEY: finding.message,
            CHECK_ID_KEY: finding.check_id or finding.rule_id,
            SEVERITY_KEY: finding.severity,
            ORIGIN_COMMIT_KEY: finding.origin_commit,
        }
    )
    try:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ignore_path = ledger_path.parent / LEDGER_IGNORE_FILE_NAME
        if not ignore_path.exists():
            ignore_path.write_text(LEDGER_IGNORE_TEXT, encoding=LEDGER_ENCODING)
        with ledger_path.open(LEDGER_APPEND_MODE, encoding=LEDGER_ENCODING) as ledger_file:
            ledger_file.write(record_text + "\n")
    except OSError:
        return


def all_recorded_findings(repository_root: Path) -> tuple[FollowupFinding, ...]:
    """Return every finding the repository's ledger holds, in record order.

    An absent or unreadable ledger reads as empty, and a line that does not
    parse into a complete record is skipped, so one damaged line never hides
    the findings around it.

    Args:
        repository_root: The repository whose ledger to read.

    Returns:
        The recorded findings, in the order they were appended.
    """
    ledger_path = followup_ledger_path(repository_root)
    try:
        ledger_text = ledger_path.read_text(encoding=LEDGER_ENCODING)
    except (OSError, UnicodeError):
        return ()

    all_findings: list[FollowupFinding] = []
    for each_line in ledger_text.splitlines():
        each_finding = _finding_from_line(each_line)
        if each_finding is not None:
            all_findings.append(each_finding)
    return tuple(all_findings)


def _finding_from_line(ledger_line: str) -> FollowupFinding | None:
    """Parse one ledger line into a finding.

    Args:
        ledger_line: One line of the ledger file.

    Returns:
        The parsed finding, or None when the line carries no complete record.
    """
    stripped_line = ledger_line.strip()
    if not stripped_line:
        return None
    try:
        parsed_record = json.loads(stripped_line)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed_record, dict):
        return None
    rule_id = parsed_record.get(RULE_ID_KEY)
    file_path = parsed_record.get(FILE_PATH_KEY)
    message = parsed_record.get(MESSAGE_KEY)
    if not isinstance(rule_id, str) or not isinstance(file_path, str):
        return None
    if not isinstance(message, str):
        return None
    return FollowupFinding(
        rule_id,
        file_path,
        message,
        _text_field(parsed_record, CHECK_ID_KEY, rule_id),
        _text_field(parsed_record, SEVERITY_KEY, SEVERITY_SMELL),
        _text_field(parsed_record, ORIGIN_COMMIT_KEY, ABSENT_ORIGIN_COMMIT),
    )


def _text_field(
    all_record_fields: dict[str, object], field_key: str, fallback: str
) -> str:
    """Read one text field of a ledger record.

    Args:
        all_record_fields: The mapping one ledger line parsed into.
        field_key: The key to read.
        fallback: The value a record written before this field carried it takes.

    Returns:
        The field's text, or the fallback.
    """
    field_value = all_record_fields.get(field_key)
    if isinstance(field_value, str) and field_value:
        return field_value
    return fallback


def head_commit(repository_root: Path) -> str:
    """Return the revision one repository has checked out.

    ::

        .git/HEAD holding "ref: refs/heads/main" -> the sha in refs/heads/main
        .git/HEAD holding a sha                  -> that sha
        .git file holding "gitdir: <path>"       -> the same reads in <path>,
                                                    branches from its commondir
        branch only in packed-refs               -> the sha packed-refs lists
        no .git entry                            -> ""

    The revision comes from the files git writes rather than from a git
    process, so recording a finding starts no subprocess.

    Args:
        repository_root: The repository whose revision to read.

    Returns:
        The checked-out revision, or an empty string when none can be read.
    """
    git_directory = _git_directory(repository_root)
    head_text = _file_text(git_directory / GIT_HEAD_FILE_NAME)
    if head_text is None:
        return ABSENT_ORIGIN_COMMIT
    if not head_text.startswith(GIT_REFERENCE_PREFIX):
        return head_text
    reference_name = head_text[len(GIT_REFERENCE_PREFIX) :]
    for each_reference_directory in (git_directory, _common_directory(git_directory)):
        loose_commit = _file_text(each_reference_directory / reference_name)
        if loose_commit:
            return loose_commit
    return _packed_reference_commit(_common_directory(git_directory), reference_name)


def _git_directory(repository_root: Path) -> Path:
    """Locate the git directory, following a linked worktree's .git file.

    Args:
        repository_root: The repository whose git directory to locate.

    Returns:
        The directory git keeps HEAD in for this checkout.
    """
    git_entry = repository_root / GIT_DIRECTORY_NAME
    if not git_entry.is_file():
        return git_entry
    entry_text = _file_text(git_entry) or ""
    if not entry_text.startswith(GIT_DIRECTORY_FILE_PREFIX):
        return git_entry
    return repository_root / entry_text[len(GIT_DIRECTORY_FILE_PREFIX) :]


def _common_directory(git_directory: Path) -> Path:
    """Locate the directory holding the branches shared by every worktree.

    Args:
        git_directory: The checkout's own git directory.

    Returns:
        The commondir target, or git_directory itself when none is named.
    """
    common_text = _file_text(git_directory / GIT_COMMON_DIRECTORY_FILE_NAME)
    if not common_text:
        return git_directory
    return git_directory / common_text


def _packed_reference_commit(common_directory: Path, reference_name: str) -> str:
    """Find one reference's sha in packed-refs.

    Args:
        common_directory: The git directory holding packed-refs.
        reference_name: The full reference name, such as refs/heads/main.

    Returns:
        The packed sha, or an empty string when packed-refs lacks the reference.
    """
    packed_text = _file_text(common_directory / GIT_PACKED_REFERENCES_FILE_NAME) or ""
    for each_line in packed_text.splitlines():
        if each_line.startswith(
            (GIT_PACKED_REFERENCES_COMMENT_PREFIX, GIT_PACKED_REFERENCES_PEELED_PREFIX)
        ):
            continue
        commit_and_name = each_line.split(maxsplit=1)
        if len(commit_and_name) == 2 and commit_and_name[1] == reference_name:
            return commit_and_name[0]
    return ABSENT_ORIGIN_COMMIT


def _file_text(file_path: Path) -> str | None:
    """Read one small git file into stripped text.

    Args:
        file_path: The file to read.

    Returns:
        The stripped text, or None when the file cannot be read.
    """
    try:
        return file_path.read_text(encoding=LEDGER_ENCODING).strip()
    except (OSError, UnicodeError):
        return None
