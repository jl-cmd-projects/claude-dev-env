#!/usr/bin/env python3
"""Inventory every file an agent loads from one checkout, then print a cleanup list.

::

    python context_audit.py <repo-root> --rows rows.jsonl
    # Context audit: my-repo
    412 loaded files. Startup loads 96 lines, about 1830 tokens, from 9 files.
    ## Carries depth over cap
    | AGENTS.md | instructions | session-start | 64 | 20 | 1210 |

Each JSON row names a path, kind, loader, trigger, size, and depth mode.
Hook text is read from saved files; the script runs no hook command.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from context_audit_constants.config import constants
from context_inventory import audit_checkout
from context_report import format_report
from context_sources import ContextRow


def write_rows(all_rows: list[ContextRow], into: Path) -> None:
    """Write one JSON object per row to *into*.

    Args:
        all_rows: Inventory rows.
        into: The JSON Lines file to write.
    """
    with into.open("w", encoding=constants.TEXT_ENCODING) as rows_file:
        for each_row in all_rows:
            rows_file.write(json.dumps(asdict(each_row)) + constants.LINE_BREAK)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path, help="the repository checkout to audit")
    parser.add_argument("--rows", type=Path, help="write every row as JSON Lines here")
    parser.add_argument(
        "--rules-dir",
        type=Path,
        help="tracked folder installed as the user rules folder",
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        help="tracked folder installed as the user skills folder",
    )
    parser.add_argument(
        "--session-start-text",
        type=Path,
        action="append",
        default=[],
        help="saved text a SessionStart hook prints; repeat for each hook",
    )
    return parser.parse_args()


def _input_error(parsed: argparse.Namespace) -> str | None:
    if not (parsed.root / constants.GIT_FOLDER_NAME).exists():
        return constants.ERROR_NOT_A_CHECKOUT_TEMPLATE.format(path=parsed.root)
    for each_hook_text_file in parsed.session_start_text:
        if not each_hook_text_file.is_file():
            return constants.ERROR_MISSING_FILE_TEMPLATE.format(
                path=each_hook_text_file
            )
    return None


def _resolve_under(root: Path, maybe_folder: Path | None) -> Path | None:
    return (root / maybe_folder).resolve() if maybe_folder else None


def main() -> int:
    """Run the audit and print the report.

    Returns:
        The process exit code.
    """
    parsed = _parse_arguments()
    error_message = _input_error(parsed)
    if error_message:
        print(error_message, file=sys.stderr)
        return constants.EXIT_CODE_INPUT_ERROR
    root = parsed.root.resolve()
    all_rows = audit_checkout(
        root,
        _resolve_under(root, parsed.rules_dir),
        _resolve_under(root, parsed.skills_dir),
        tuple(parsed.session_start_text),
    )
    report = format_report(root.name, all_rows)
    if parsed.rows:
        write_rows(all_rows, parsed.rows)
        rows_line = constants.REPORT_ROWS_WRITTEN_TEMPLATE.format(path=parsed.rows)
        report += constants.LINE_BREAK + rows_line + constants.LINE_BREAK
    print(report, end="")
    return constants.EXIT_CODE_AUDITED


if __name__ == "__main__":
    sys.exit(main())
