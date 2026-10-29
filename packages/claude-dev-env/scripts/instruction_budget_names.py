"""Find the lines of an instruction file that name a person.

A name is matched as a whole word against stored digests, so the name itself
never appears in the repository.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

from dev_env_scripts_constants.followup_constants import (
    INSTRUCTION_PERSONAL_NAME_RULE_ID,
)
from dev_env_scripts_constants.instruction_budget_constants import (
    ALL_PERSONAL_NAME_DIGESTS,
    LINE_NUMBER_SEPARATOR,
    PERSONAL_NAME_FINDING_MESSAGE_TEMPLATE,
    PERSONAL_NAME_TOKEN_PATTERN,
    TEXT_ENCODING,
)
from dev_env_scripts_constants.private_term_constants import PrivateTermDigest
from instruction_budget_files import InstructionFinding, read_instruction_text


def _is_personal_name(token: str, all_digests: frozenset[PrivateTermDigest]) -> bool:
    normalized_token = token.lower()
    token_digest = PrivateTermDigest(
        length=len(normalized_token),
        sha256=hashlib.sha256(normalized_token.encode(TEXT_ENCODING)).hexdigest(),
    )
    return token_digest in all_digests


def personal_name_line_numbers(
    text: str, all_digests: frozenset[PrivateTermDigest] = ALL_PERSONAL_NAME_DIGESTS
) -> tuple[int, ...]:
    """Return the one-based lines that name a person, matched as whole words.

    Args:
        text: Text to scan.
        all_digests: Digests of the lowercase words to find.

    Returns:
        Each line number once, in order. A word that is only part of a longer
        word, such as "json", does not match.
    """
    all_line_numbers: list[int] = []
    for each_line_number, each_line in enumerate(text.splitlines(), start=1):
        if any(
            _is_personal_name(each_token, all_digests)
            for each_token in PERSONAL_NAME_TOKEN_PATTERN.findall(each_line)
        ):
            all_line_numbers.append(each_line_number)
    return tuple(all_line_numbers)


def _personal_name_finding(
    repository_root: Path, file_path: Path, all_line_numbers: tuple[int, ...]
) -> InstructionFinding:
    return InstructionFinding(
        rule_id=INSTRUCTION_PERSONAL_NAME_RULE_ID,
        file_path=file_path.relative_to(repository_root).as_posix(),
        message=PERSONAL_NAME_FINDING_MESSAGE_TEMPLATE.format(
            lines=LINE_NUMBER_SEPARATOR.join(
                str(each_line) for each_line in all_line_numbers
            )
        ),
    )


def personal_name_findings(
    repository_root: Path,
    all_scoped_files: Iterable[Path],
    all_digests: frozenset[PrivateTermDigest] = ALL_PERSONAL_NAME_DIGESTS,
) -> list[InstructionFinding]:
    """Report each scoped instruction file that names a person.

    Args:
        repository_root: Resolved repository root.
        all_scoped_files: Instruction files to check.
        all_digests: Digests of the lowercase words to find.

    Returns:
        One finding per file with at least one named line.
    """
    all_findings: list[InstructionFinding] = []
    for each_path in all_scoped_files:
        all_line_numbers = personal_name_line_numbers(
            read_instruction_text(each_path), all_digests
        )
        if all_line_numbers:
            all_findings.append(
                _personal_name_finding(repository_root, each_path, all_line_numbers)
            )
    return all_findings
