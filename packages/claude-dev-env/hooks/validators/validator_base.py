"""Base classes for validators.

Provides shared dataclasses used across all validator modules, the one
read and the one parse each of those modules shares for a given file, and
the command-line runner a validator module's ``main`` can call.
"""

import ast
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config.validator_base_constants import SOURCE_CACHE_ENTRIES, SOURCE_ENCODING


@dataclass(frozen=True)
class Violation:
    """Represents a validation violation."""

    file: str
    line: int
    message: str

    def __str__(self) -> str:
        """Format as file:line: message."""
        return f"{self.file}:{self.line}: {self.message}"


@dataclass(frozen=True)
class ValidatorResult:
    """Result from running a validator."""

    name: str
    checks: str
    passed: bool
    output: str
    skipped: bool = False


@lru_cache(maxsize=SOURCE_CACHE_ENTRIES)
def _source_text_for_stat(
    file_path_text: str, modified_nanoseconds: int, size_in_bytes: int
) -> str:
    """Read one file, keyed on the stat that identifies this version of it."""
    return Path(file_path_text).read_text(encoding=SOURCE_ENCODING)


def source_text(file_path: Path) -> str:
    """Return the file's text, reading it once however many checks ask.

    Every check the save-path gate runs reads the same file. The gate hands
    each of them one freshly written target, so the read is repeated work.
    The cache key carries the modification time and size, so an edited file
    is read again.

    That key has one blind spot: a rewrite that leaves the size unchanged
    inside a single modification-time tick is served from the cache. A hook
    process handles one payload, so it cannot happen there; a long CLI pass
    over many files is where a reader needs to know.

    Raises whatever ``read_text`` raises, so a caller's own error handling
    is unchanged.

    Args:
        file_path: The file to read.

    Returns:
        The file's decoded text.
    """
    file_status = file_path.stat()
    return _source_text_for_stat(
        str(file_path), file_status.st_mtime_ns, file_status.st_size
    )


@lru_cache(maxsize=SOURCE_CACHE_ENTRIES)
def syntax_tree(source: str) -> ast.Module:
    """Return the parsed tree for source, parsing it once however many checks ask.

    No check mutates the tree; each one walks it. So one parse serves all of
    them, and the tree is shared rather than copied.

    Raises ``SyntaxError`` exactly as ``ast.parse`` does, so a caller's own
    error handling is unchanged.

    Args:
        source: The file's text.

    Returns:
        The parsed module.
    """
    return ast.parse(source)


def run_file_validator_cli(
    validate_file: Callable[[Path], list[Violation]],
    all_arguments: Sequence[str] | None = None,
) -> int:
    """Validate each file named on the command line and print its violations.

    ``python -m validators.todo_checks a.py b.py`` prints one line per
    violation and exits 1 when any file has one.

    Args:
        validate_file: The module's per-file check.
        all_arguments: The command-line arguments, program name first.
            Defaults to ``sys.argv``.

    Returns:
        1 with no file named or any violation found, else 0.
    """
    all_file_arguments = list(sys.argv if all_arguments is None else all_arguments)[1:]
    if not all_file_arguments:
        return 1
    all_violations: list[Violation] = []
    for each_file_argument in all_file_arguments:
        all_violations.extend(validate_file(Path(each_file_argument)))
    for each_violation in all_violations:
        sys.stdout.write(f"{each_violation}\n")
    return 1 if all_violations else 0
