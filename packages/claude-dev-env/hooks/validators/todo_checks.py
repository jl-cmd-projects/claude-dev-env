"""TODO/FIXME tracking validator.

Implements check 36: TODO without issue reference.
"""

import re
import sys
from pathlib import Path
from typing import List

from .validator_base import Violation, run_file_validator_cli, source_text


TODO_PATTERN = re.compile(r"#\s*(TODO|FIXME)\b(?!.*#\d+)", re.IGNORECASE)


def check_untracked_todos(source: str, filename: str) -> List[Violation]:
    violations: List[Violation] = []
    lines = source.splitlines()

    for line_num, line in enumerate(lines, start=1):
        if TODO_PATTERN.search(line):
            violations.append(
                Violation(
                    filename,
                    line_num,
                    "TODO/FIXME marker found - remove it from source code and track the work outside the file",
                )
            )

    return violations


def validate_file(file_path: Path) -> List[Violation]:
    filename = str(file_path)
    try:
        source = source_text(file_path)
    except Exception as error:
        return [Violation(filename, 0, f"Error reading file: {error}")]

    return check_untracked_todos(source, filename)


def main() -> int:
    return run_file_validator_cli(validate_file)


if __name__ == "__main__":
    sys.exit(main())
