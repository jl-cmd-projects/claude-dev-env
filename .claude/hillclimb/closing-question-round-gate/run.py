"""Run each labelled transcript through the closing question round gate and grade it.

::

    python3 run.py
    python3 run.py --hook /path/to/another_gate.py

Each case in ``cases.json`` holds a synthetic transcript, the fields it adds to
the Stop payload, the environment it sets, and the decision it expects. The
runner writes the transcript to a temporary folder and starts the hook as its
own process, the way Claude Code does: the payload on stdin, and the case's
environment on top of an interactive session's.

The grader reads the exit code and stdout::

    exit 2, stdout {"decision": "block", ...}  -> hold
    exit 0, empty stdout                       -> allow
    anything else                              -> unreadable

The run prints one row per case and ``passed N/M`` last. It exits with code 1
when a case misses.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from closing_round_eval_support.config.constants import (
    ALL_BASE_PAYLOAD_FIELDS,
    ALL_HOME_ENVIRONMENT_VARIABLES,
    ALLOW_DECISION,
    ALLOW_EXIT_CODE,
    CASE_ENVIRONMENT_KEY,
    CASE_EXPECTED_KEY,
    CASE_ID_KEY,
    CASE_PAYLOAD_KEY,
    CASE_TRANSCRIPT_KEY,
    CASES_FILE,
    HOLD_DECISION,
    HOLD_EXIT_CODE,
    HOME_DIRECTORY_NAME,
    HOOK_FILE,
    HOOK_TIMEOUT_SECONDS,
    INTERACTIVE_SESSION_ATTENDED_TEXT,
    MISSED_EXIT_CODE,
    MISSED_ROW_LABEL,
    PASSED_EXIT_CODE,
    PASSED_ROW_LABEL,
    RECORD_SEPARATOR,
    ROW_TEMPLATE,
    SESSION_ATTENDED_ENVIRONMENT_VARIABLE,
    STOP_BLOCK_DECISION,
    STOP_DECISION_KEY,
    SUMMARY_TEMPLATE,
    TRANSCRIPT_FILE_NAME,
    TRANSCRIPT_PATH_KEY,
    UNREADABLE_DECISION,
    UTF8_ENCODING,
)

logger = logging.getLogger(__name__)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hook", type=Path, default=HOOK_FILE, help="The gate script to grade."
    )
    return parser.parse_args()


def stop_payload(
    all_case_fields: dict[str, object], case_directory: Path
) -> dict[str, object]:
    """Return the Stop payload for a case, after writing its transcript.

    A case whose transcript is null gets a path to a file that does not exist.

    Args:
        all_case_fields: One case from the cases file.
        case_directory: The temporary folder that holds the case's transcript.

    Returns:
        The payload the hook reads from stdin.
    """
    transcript_path = case_directory / TRANSCRIPT_FILE_NAME
    all_records = all_case_fields.get(CASE_TRANSCRIPT_KEY)
    if isinstance(all_records, list):
        transcript_path.write_text(
            RECORD_SEPARATOR.join(
                json.dumps(each_record) for each_record in all_records
            ),
            encoding=UTF8_ENCODING,
        )
    all_extra_fields = all_case_fields.get(CASE_PAYLOAD_KEY)
    return {
        **ALL_BASE_PAYLOAD_FIELDS,
        TRANSCRIPT_PATH_KEY: str(transcript_path),
        **(all_extra_fields if isinstance(all_extra_fields, dict) else {}),
    }


def case_environment(
    all_case_fields: dict[str, object], case_directory: Path
) -> dict[str, str]:
    """Return the environment the hook runs in for a case.

    The base is an interactive session with its home inside the case folder.
    The case's own variables go on top.

    Args:
        all_case_fields: One case from the cases file.
        case_directory: The temporary folder that holds the case's home.

    Returns:
        The environment for the hook process.
    """
    home_directory = case_directory / HOME_DIRECTORY_NAME
    home_directory.mkdir(exist_ok=True)
    all_case_variables = all_case_fields.get(CASE_ENVIRONMENT_KEY)
    return {
        **os.environ,
        **dict.fromkeys(ALL_HOME_ENVIRONMENT_VARIABLES, str(home_directory)),
        SESSION_ATTENDED_ENVIRONMENT_VARIABLE: INTERACTIVE_SESSION_ATTENDED_TEXT,
        **(all_case_variables if isinstance(all_case_variables, dict) else {}),
    }


def graded_decision(exit_code: int, stdout_text: str) -> str:
    """Return hold, allow, or unreadable for one hook run.

    ::

        2, '{"decision": "block", "reason": "..."}'  -> hold
        0, ''                                         -> allow
        0, '{"decision": "block"}'                    -> unreadable
        1, ''                                         -> unreadable

    Args:
        exit_code: The exit code of the hook process.
        stdout_text: What the hook process wrote to stdout.

    Returns:
        The graded decision.
    """
    if exit_code == ALLOW_EXIT_CODE and not stdout_text.strip():
        return ALLOW_DECISION
    if exit_code != HOLD_EXIT_CODE:
        return UNREADABLE_DECISION
    try:
        stop_decision = json.loads(stdout_text)
    except ValueError:
        return UNREADABLE_DECISION
    is_block = (
        isinstance(stop_decision, dict)
        and stop_decision.get(STOP_DECISION_KEY) == STOP_BLOCK_DECISION
    )
    return HOLD_DECISION if is_block else UNREADABLE_DECISION


def case_decision(all_case_fields: dict[str, object], hook_path: Path) -> str:
    """Start the hook on one case as its own process and grade the run.

    Args:
        all_case_fields: One case from the cases file.
        hook_path: The gate script to run.

    Returns:
        The graded decision.
    """
    with tempfile.TemporaryDirectory() as case_directory_name:
        case_directory = Path(case_directory_name)
        hook_run = subprocess.run(
            [sys.executable, str(hook_path)],
            input=json.dumps(stop_payload(all_case_fields, case_directory)),
            capture_output=True,
            text=True,
            env=case_environment(all_case_fields, case_directory),
            timeout=HOOK_TIMEOUT_SECONDS,
            check=False,
        )
    return graded_decision(hook_run.returncode, hook_run.stdout)


def graded_rows(
    all_cases: list[dict[str, object]], hook_path: Path
) -> list[tuple[bool, str]]:
    """Run every case and return its row.

    Args:
        all_cases: The cases, in the order of the cases file.
        hook_path: The gate script to run.

    Returns:
        One (passed, row text) pair per case, in the same order.
    """
    all_rows: list[tuple[bool, str]] = []
    for each_case in all_cases:
        decision = case_decision(each_case, hook_path)
        has_passed = decision == each_case[CASE_EXPECTED_KEY]
        row_text = ROW_TEMPLATE.format(
            label=PASSED_ROW_LABEL if has_passed else MISSED_ROW_LABEL,
            case_id=each_case[CASE_ID_KEY],
            expected=each_case[CASE_EXPECTED_KEY],
            decision=decision,
        )
        all_rows.append((has_passed, row_text))
    return all_rows


def main() -> int:
    """Run every case, print one row per case, and print the score last.

    Returns:
        Process exit status, zero when every case passes and one when a case misses.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    arguments = _parse_arguments()
    all_cases = json.loads(CASES_FILE.read_text(encoding=UTF8_ENCODING))
    all_rows = graded_rows(all_cases, arguments.hook)
    for _, each_row_text in all_rows:
        logger.info("%s", each_row_text)
    passed_count = sum(has_passed for has_passed, _ in all_rows)
    logger.info(
        "%s",
        SUMMARY_TEMPLATE.format(passed_count=passed_count, case_count=len(all_rows)),
    )
    return PASSED_EXIT_CODE if passed_count == len(all_rows) else MISSED_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
