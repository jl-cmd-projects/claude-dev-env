"""Grade a variant's saved traces again with the current judge and grader.

::

    python3 rejudge.py --variant baseline --direct

A judge or label change needs no new sessions. This reads each row in
``<variant>/results.jsonl`` from its newest run digest, sends its saved trace and the case's current
labels to the judge, and writes the regraded rows to
``<variant>/rejudged.jsonl``. The sessions themselves stay as they ran.
"""

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

flow_directory = Path(__file__).resolve().parent
sys.path[:0] = [
    str(each_root)
    for each_root in (
        flow_directory,
        flow_directory.parent / "features-start-with-an-eval",
        flow_directory.parent / "rules-index",
    )
    if str(each_root) not in sys.path
]

from rules_eval_support import judge as rules_judge
from rules_eval_support.judge import run_judge
from scope_eval_support.config.constants import (
    CASES_FILE,
    DEFAULT_PARALLEL,
    FLOW_ROOT,
    PRIOR_REPLY_FIELD,
    REJUDGED_FILE_NAME,
    RESULTS_FILE_NAME,
    TRACES_DIRECTORY_NAME,
)
from scope_eval_support.grading import grade_session, judge_text
from session_eval_support.config.constants import RUN_DIGEST_FIELD

logger = logging.getLogger(__name__)


def _regraded_row(
    row_by_field: dict[str, object],
    case_by_field: dict[str, str],
    variant_directory: Path,
    is_direct: bool,
) -> dict[str, object] | None:
    trace_name = f"{row_by_field['prompt_id']}_rep{row_by_field['rep']}.json"
    all_turns = json.loads(
        (variant_directory / TRACES_DIRECTORY_NAME / trace_name).read_text(
            encoding="utf-8"
        )
    )
    meta_by_field = dict(row_by_field["meta"])
    judged_case = {
        **case_by_field,
        PRIOR_REPLY_FIELD: meta_by_field.get(PRIOR_REPLY_FIELD, ""),
    }
    transcript = rules_judge._transcript_within_limit(all_turns)
    verdict, _ = run_judge(judge_text(judged_case, transcript), is_direct)
    if verdict is None:
        return None
    meta_by_field["judge_verdict"] = verdict
    return {
        **row_by_field,
        "grade": grade_session(meta_by_field["questions"], verdict),
        "meta": meta_by_field,
    }


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL)
    parser.add_argument("--direct", action="store_true")
    return parser.parse_args()


def _read_rows(variant_directory: Path) -> list[dict[str, object]]:
    all_rows = [
        json.loads(each_line)
        for each_line in (variant_directory / RESULTS_FILE_NAME)
        .read_text(encoding="utf-8")
        .splitlines()
        if each_line.strip()
    ]
    if not all_rows:
        return []
    newest_digest = all_rows[-1]["meta"][RUN_DIGEST_FIELD]
    return [
        each_row
        for each_row in all_rows
        if each_row["meta"][RUN_DIGEST_FIELD] == newest_digest
    ]


def _regrade_all(
    all_rows: list[dict[str, object]],
    variant_directory: Path,
    arguments: argparse.Namespace,
) -> list[dict[str, object] | None]:
    case_by_id = {
        each_case["id"]: each_case
        for each_case in json.loads(CASES_FILE.read_text(encoding="utf-8"))
    }
    with ThreadPoolExecutor(max_workers=arguments.parallel) as executor:
        return list(
            executor.map(
                lambda each_row: _regraded_row(
                    each_row,
                    case_by_id[each_row["prompt_id"]],
                    variant_directory,
                    arguments.direct,
                ),
                all_rows,
            )
        )


def main() -> int:
    """Regrade every saved row of one variant and print the pass counts.

    Returns:
        Process exit status, zero once every row is regraded.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    arguments = _parse_arguments()
    variant_directory = FLOW_ROOT / arguments.variant
    all_outcomes = _regrade_all(
        _read_rows(variant_directory), variant_directory, arguments
    )
    all_regraded = [each_row for each_row in all_outcomes if each_row is not None]
    (variant_directory / REJUDGED_FILE_NAME).write_text(
        "".join(json.dumps(each_row) + "\n" for each_row in all_regraded),
        encoding="utf-8",
    )
    passed = sum(each_row["grade"]["correct"] for each_row in all_regraded)
    logger.info(
        "%s regraded: %d/%d correct, %d judge failures left out",
        arguments.variant,
        passed,
        len(all_regraded),
        len(all_outcomes) - len(all_regraded),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
