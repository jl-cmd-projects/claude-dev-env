"""Run the closing-reply judge on every eval case and score the calls against the bars.

::

    python3 run.py --model haiku --effort medium --runs 3
    python3 run.py --score
    python3 run.py --cases <rows.jsonl> --out <folder> --runs 3 --score-bars main

Each call is the call the open tasks Stop gate makes, through
``judge_eval_support.calls``. One row per call lands in
``<out>/results.jsonl``, tagged with a digest of the hook source, the cases
file, the model and the effort. A rerun skips every (case, run) already stored
with status ``ok`` or ``shape`` under the same digest.

The error rule was fixed before the first call::

    status ok     the answer is the verdict shape      scored
    status shape  the result is prose, a bad shape, or a span outside the reply
                  scored as not held, and counted against the shape bar
    status error  timeout, start failure, exit code other than 0, stdout that is
                  not JSON, or is_error    not scored; a rerun retries it
    an error still there after --attempts tries is scored as not held
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from judge_eval_support import calls, scoring
from judge_eval_support.config.constants import (
    ALL_BAR_CHOICES,
    CALL_LOG_FILE_NAME,
    CASES_FILE,
    DEFAULT_ATTEMPTS,
    DEFAULT_EFFORT,
    DEFAULT_MODEL,
    DEFAULT_OUT_DIRECTORY,
    DEFAULT_RUNS,
    DEFAULT_WORKERS,
    EVAL_BARS,
    MISSED_PREFIX,
    NO_CLAUDE_MESSAGE,
    PASSED_PREFIX,
)
from hooks_constants.closing_reply_judge_constants import (
    CLAUDE_EXECUTABLE_NAME,
    JUDGE_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


def parsed_arguments() -> argparse.Namespace:
    """Return the command-line options.

    Returns:
        The cases file, out folder, model, effort, runs, workers, attempts, timeout and score options.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, default=CASES_FILE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIRECTORY)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default=DEFAULT_EFFORT)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--timeout", type=float, default=JUDGE_TIMEOUT_SECONDS)
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--score-bars", choices=ALL_BAR_CHOICES, default=EVAL_BARS)
    return parser.parse_args()


def make_pending_calls(arguments: argparse.Namespace) -> None:
    """Make every call the call log does not hold yet under this run's digest.

    Args:
        arguments: The command-line options.
    """
    claude_path = shutil.which(CLAUDE_EXECUTABLE_NAME)
    if claude_path is None:
        sys.exit(NO_CLAUDE_MESSAGE)
    digest = calls.run_digest(arguments.cases, arguments.model, arguments.effort)
    arguments.out.mkdir(parents=True, exist_ok=True)
    call_log_path = arguments.out / CALL_LOG_FILE_NAME
    all_calls = calls.pending_calls(
        calls.read_cases(arguments.cases),
        calls.read_call_rows(call_log_path),
        digest,
        arguments.runs,
        arguments.attempts,
    )
    logger.info("digest %s: %d calls to make", digest, len(all_calls))
    call_settings = {
        "claude_path": claude_path,
        "model": arguments.model,
        "effort": arguments.effort,
        "timeout_seconds": arguments.timeout,
        "digest": digest,
    }
    calls.run_calls(all_calls, call_settings, call_log_path, arguments.workers)


def score_lines(arguments: argparse.Namespace) -> tuple[list[str], bool]:
    """Return the score lines for this run's digest and whether every bar passed.

    Args:
        arguments: The command-line options.

    Returns:
        The digest line, the per-set table, the totals and one line per bar, and whether each bar passed.
    """
    digest = calls.run_digest(arguments.cases, arguments.model, arguments.effort)
    scored = scoring.score(
        calls.read_cases(arguments.cases),
        calls.read_call_rows(arguments.out / CALL_LOG_FILE_NAME),
        digest,
        arguments.runs,
    )
    all_bars = scoring.bar_lines(scored, arguments.runs, arguments.score_bars)
    all_lines = [f"digest {digest}", *scoring.summary_lines(scored, arguments.runs)]
    all_lines += [(PASSED_PREFIX if each_passed else MISSED_PREFIX) + each_line for each_line, each_passed in all_bars]
    return all_lines, all(each_passed for _, each_passed in all_bars)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    arguments = parsed_arguments()
    if not arguments.score:
        make_pending_calls(arguments)
    all_lines, is_every_bar_met = score_lines(arguments)
    for each_line in all_lines:
        logger.info("%s", each_line)
    sys.exit(0 if is_every_bar_met else 1)


if __name__ == "__main__":
    main()
