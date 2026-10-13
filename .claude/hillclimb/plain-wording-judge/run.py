"""Score the plain-wording prompt hook against Jon's held-out marks.

::

    python3 run.py --output baseline/results.jsonl --command-prefix "<broker run ... -->"

Each held-out line goes through ``claude -p`` on Haiku with the shipped hook
prompt. One row per case lands in the output file, and the log reports fails
caught and passes flagged.
"""

import argparse
import json
import logging
import shlex
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

flow_directory = Path(__file__).resolve().parent
if str(flow_directory) not in sys.path:
    sys.path.insert(0, str(flow_directory))

from wording_eval_support.config.constants import (
    CALL_TIMEOUT_SECONDS,
    CASES_PATH,
    DEFAULT_WORKER_COUNT,
    HELD_OUT_SPLIT,
    HOOKS_CONFIG_PATH,
    JUDGE_MODEL,
    ROW_SEPARATOR,
)
from wording_eval_support.grading import fill_prompt, find_judge_prompt, parse_verdict, tally

logger = logging.getLogger(__name__)


def _judge(prompt: str, line_text: str, all_prefix_words: list[str]) -> bool | None:
    completed = subprocess.run(
        [*all_prefix_words, "claude", "-p", "--model", JUDGE_MODEL, fill_prompt(prompt, line_text)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=CALL_TIMEOUT_SECONDS,
        check=False,
    )
    return parse_verdict(completed.stdout)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKER_COUNT)
    parser.add_argument("--command-prefix", type=shlex.split, default=[])
    return parser.parse_args()


def main() -> int:
    """Run the held-out cases and log the tally.

    Returns:
        Zero once every case is scored.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    arguments = _parse_arguments()
    prompt = find_judge_prompt(json.loads(HOOKS_CONFIG_PATH.read_text(encoding="utf-8")))
    all_cases = [each_case for each_case in json.loads(CASES_PATH.read_text(encoding="utf-8")) if each_case["split"] == HELD_OUT_SPLIT]
    with ThreadPoolExecutor(max_workers=arguments.workers) as executor:
        all_flags = list(executor.map(lambda each_case: _judge(prompt, each_case["text"], arguments.command_prefix), all_cases))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    all_rows = [json.dumps({**each_case, "flagged": each_flag}) for each_case, each_flag in zip(all_cases, all_flags)]
    arguments.output.write_text(ROW_SEPARATOR.join(all_rows) + ROW_SEPARATOR, encoding="utf-8")
    run_tally = tally(all_cases, all_flags)
    logger.info("fails caught: %d of %d", run_tally.fails_caught, run_tally.fail_count)
    logger.info("passes flagged: %d of %d", run_tally.passes_flagged, run_tally.pass_count)
    logger.info("unreadable verdicts: %d", run_tally.unreadable_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
