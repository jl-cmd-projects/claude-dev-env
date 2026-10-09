"""Ledger of non-breaking findings awaiting a follow-up fix, one file each.

A gate that finds a breaking defect stops the commit, the push, or the tool
call. A gate that finds a non-breaking smell records the finding here and lets
the work proceed. Each finding is its own JSON file under
``.claude/followups/``, named by a hash of the finding, so parallel branches
that record different findings never edit the same file. ``cde followup``
reads the ledger and briefs the agent that fixes the recorded smells in their
own pull request.

Every write is fail-safe. A ledger that cannot be created or written to leaves
the calling gate's decision unchanged, so recording a finding never becomes a
new way for a gate to fail.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import NamedTuple

_hooks_directory = str(Path(__file__).resolve().parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

from hooks_constants.followup_ledger_constants import (
    ABSENT_ORIGIN_COMMIT,
    ALL_FOLLOWUP_DIRECTORY_SEGMENTS,
    CHECK_ID_KEY,
    FILE_PATH_KEY,
    FINDING_FILE_NAME_HASH_LENGTH,
    FINDING_FILE_PATTERN,
    FINDING_FILE_SUFFIX,
    GIT_COMMON_DIRECTORY_FILE_NAME,
    GIT_DIRECTORY_FILE_PREFIX,
    GIT_DIRECTORY_NAME,
    GIT_HEAD_FILE_NAME,
    GIT_PACKED_REFERENCES_COMMENT_PREFIX,
    GIT_PACKED_REFERENCES_FILE_NAME,
    GIT_PACKED_REFERENCES_PEELED_PREFIX,
    GIT_REFERENCE_PREFIX,
    LEDGER_CREATE_MODE,
    LEDGER_ENCODING,
    LEDGER_IGNORE_FILE_NAME,
    LEDGER_IGNORE_TEXT,
    LEDGER_JSON_INDENT,
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


def followup_directory(repository_root: Path) -> Path:
    """Return the directory that holds one repository's recorded findings.

    Args:
        repository_root: The repository whose ledger to address.

    Returns:
        The absolute path of that repository's follow-up directory.
    """
    return repository_root.joinpath(*ALL_FOLLOWUP_DIRECTORY_SEGMENTS)


def finding_path(repository_root: Path, finding: FollowupFinding) -> Path:
    """Return the file one finding is recorded in.

    The file name is a hash of the finding's tracking key, so the same finding
    always maps to the same file and two different findings never share one.

    Args:
        repository_root: The repository whose ledger holds the finding.
        finding: The finding to locate.

    Returns:
        The absolute path of the finding's file.
    """
    key_text = json.dumps(list(finding.tracking_key()), ensure_ascii=True)
    key_digest = hashlib.sha256(key_text.encode(LEDGER_ENCODING)).hexdigest()
    file_name = key_digest[:FINDING_FILE_NAME_HASH_LENGTH] + FINDING_FILE_SUFFIX
    return followup_directory(repository_root) / file_name


def record_followup_finding(repository_root: Path, finding: FollowupFinding) -> None:
    """Write one finding to its own file in the repository's ledger, once.

    The file is created exclusively, so a finding already on disk keeps the
    record that first raised it, and a gate that runs on every commit records
    a standing smell a single time. Two writers recording different findings
    write different files, so parallel branches never edit a shared file. The
    first write in a directory with no ``.gitignore`` adds one matching every
    file, so the ledger stays out of ``git status`` in any repository that
    does not commit its own. Every filesystem error is swallowed, so a ledger
    failure leaves the caller's gate decision unchanged.

    Args:
        repository_root: The repository whose ledger receives the finding.
        finding: The non-breaking finding to record.
    """
    record_path = finding_path(repository_root, finding)
    record_text = json.dumps(_record_fields(finding), indent=LEDGER_JSON_INDENT)
    try:
        record_path.parent.mkdir(parents=True, exist_ok=True)
        ignore_path = record_path.parent / LEDGER_IGNORE_FILE_NAME
        if not ignore_path.exists():
            ignore_path.write_text(LEDGER_IGNORE_TEXT, encoding=LEDGER_ENCODING)
        with record_path.open(LEDGER_CREATE_MODE, encoding=LEDGER_ENCODING) as record_file:
            record_file.write(record_text + "\n")
    except OSError:
        return


def _record_fields(finding: FollowupFinding) -> dict[str, str]:
    return {
        RULE_ID_KEY: finding.rule_id,
        FILE_PATH_KEY: finding.file_path,
        MESSAGE_KEY: finding.message,
        CHECK_ID_KEY: finding.check_id or finding.rule_id,
        SEVERITY_KEY: finding.severity,
        ORIGIN_COMMIT_KEY: finding.origin_commit,
    }


def all_recorded_findings(repository_root: Path) -> tuple[FollowupFinding, ...]:
    """Return every finding the repository's ledger holds, ordered by check.

    An absent directory reads as empty, and a file that does not parse into a
    complete record is skipped, so one damaged file never hides the findings
    around it.

    Args:
        repository_root: The repository whose ledger to read.

    Returns:
        The recorded findings, sorted by check identifier, path, and message.
    """
    all_findings = [
        each_finding
        for _each_path, each_finding in all_finding_files(repository_root)
    ]
    return tuple(sorted(all_findings, key=FollowupFinding.tracking_key))


def all_record_paths(directory: Path) -> list[Path]:
    """Return every finding file in one ledger directory, sorted by name.

    Args:
        directory: The follow-up directory to list.

    Returns:
        The finding file paths, or an empty list when none can be listed.
    """
    try:
        return sorted(directory.glob(FINDING_FILE_PATTERN))
    except OSError:
        return []


def all_finding_files(repository_root: Path) -> list[tuple[Path, FollowupFinding]]:
    """Return each readable finding file with the finding it holds.

    Args:
        repository_root: The repository whose ledger to read.

    Returns:
        Path and finding pairs, sorted by file name.
    """
    all_pairs: list[tuple[Path, FollowupFinding]] = []
    for each_path in all_record_paths(followup_directory(repository_root)):
        try:
            record_text = each_path.read_text(encoding=LEDGER_ENCODING)
        except (OSError, UnicodeError):
            continue
        each_finding = finding_from_text(record_text)
        if each_finding is not None:
            all_pairs.append((each_path, each_finding))
    return all_pairs


def finding_from_text(record_text: str) -> FollowupFinding | None:
    """Parse one JSON record into a finding.

    Args:
        record_text: One finding file's text, or one legacy ledger line.

    Returns:
        The parsed finding, or None when the text carries no complete record.
    """
    try:
        parsed_record = json.loads(record_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed_record, dict):
        return None
    rule_id = parsed_record.get(RULE_ID_KEY)
    file_path = parsed_record.get(FILE_PATH_KEY)
    message = parsed_record.get(MESSAGE_KEY)
    if not all(isinstance(each, str) for each in (rule_id, file_path, message)):
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
        all_record_fields: The mapping one record parsed into.
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
