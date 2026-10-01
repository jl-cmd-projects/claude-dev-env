"""Evaluate the review recipe and preserve model evidence."""

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

suite_directory = str(Path(__file__).resolve().parent)
if suite_directory not in sys.path:
    sys.path.insert(0, suite_directory)

from review_eval_support.config.constants import (
    ALL_MODES,
    ALL_REVISION_COMMAND,
    ALL_SPLITS,
    CASE_SECONDS,
    DEFAULT_BATCH_SECONDS,
    DEFAULT_CASE_LIMIT,
    JSON_INDENT,
    MAX_BATCH_SECONDS,
    MAX_CASE_SECONDS,
    MAX_CASES,
    METADATA_SECONDS,
    NEWLINE,
    SUITE_ROOT,
)
from review_eval_support.execution import execute, replay
from review_eval_support.grading import (
    EvaluationRunFatal,
    cases,
    digest,
    grade,
    summarize,
    verify_witness,
)

logger = logging.getLogger(__name__)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=ALL_MODES)
    parser.add_argument("--output", type=Path, default=Path("review-eval-results"))
    parser.add_argument("--responses", type=Path)
    parser.add_argument("--split", choices=ALL_SPLITS, default="development")
    parser.add_argument("--limit", type=int, default=DEFAULT_CASE_LIMIT)
    parser.add_argument("--timeout", type=int, default=CASE_SECONDS)
    parser.add_argument("--max-seconds", type=int, default=DEFAULT_BATCH_SECONDS)
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--effort", default="low")
    parser.add_argument("--codex", default="codex")
    return parser.parse_args()


def _validate_controls(each_case: dict) -> None:
    good_reply = {
        "findings": [
            {**each_finding, "failure_scenario": "controller-authored calibration"}
            for each_finding in each_case["expected"]
        ]
    }
    bad_reply = (
        {"findings": []}
        if each_case["expected"]
        else {
            "findings": [
                {"line": 1, "category": "removed-guard", "failure_scenario": "invented"}
            ]
        }
    )
    if not grade(each_case, good_reply)["pass"] or grade(each_case, bad_reply)["pass"]:
        raise EvaluationRunFatal("grader control failed")


def _validate_settings(settings: argparse.Namespace) -> None:
    if (
        not 1 <= settings.limit <= MAX_CASES
        or not 1 <= settings.timeout <= MAX_CASE_SECONDS
        or not 1 <= settings.max_seconds <= MAX_BATCH_SECONDS
    ):
        raise EvaluationRunFatal("invalid case count or runtime ceiling")
    if settings.output.exists():
        raise EvaluationRunFatal("output must be a new directory")
    if settings.mode == "replay" and not settings.responses:
        raise EvaluationRunFatal("replay requires --responses")


def _fresh_attempt(
    each_case: dict, settings: argparse.Namespace, recipe: str, deadline: float
) -> dict:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return {
            "id": each_case["id"],
            "split": each_case["split"],
            "mode": "fresh_recipe_with_fixture",
            "status": "infra_error",
            "failure": "batch_timeout",
        }
    case_settings = argparse.Namespace(**vars(settings))
    case_settings.timeout = min(settings.timeout, remaining)
    return execute(each_case, case_settings, settings.output, recipe)


def _run_cases(
    all_cases: list[dict], settings: argparse.Namespace, recipe: str
) -> list[dict]:
    reply_by_case_id = (
        json.loads(settings.responses.read_text(encoding="utf-8"))
        if settings.mode == "replay"
        else {}
    )
    all_attempts = []
    deadline = time.monotonic() + settings.max_seconds
    for each_case in all_cases:
        each_attempt = (
            _fresh_attempt(each_case, settings, recipe, deadline)
            if settings.mode == "live"
            else replay(each_case, reply_by_case_id)
        )
        all_attempts.append(each_attempt)
        with (settings.output / "results.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(each_attempt) + NEWLINE)
        if settings.mode == "live" and each_attempt["status"] == "infra_error":
            break
    return all_attempts


def _environment(settings: argparse.Namespace) -> dict:
    revision_call = subprocess.run(
        ALL_REVISION_COMMAND,
        cwd=SUITE_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=METADATA_SECONDS,
    )
    environment_by_key = {
        "python": sys.version,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "cost_usd": None,
        "source_revision": revision_call.stdout.strip(),
    }
    if settings.mode == "live":
        version_call = subprocess.run(
            [settings.codex, "--version"],
            capture_output=True,
            text=True,
            timeout=METADATA_SECONDS,
            check=False,
        )
        environment_by_key["codex_cli"] = version_call.stdout.strip()
    return environment_by_key


def _write_report(
    all_attempts: list[dict], settings: argparse.Namespace, recipe: str
) -> None:
    summary_by_key = {
        "mode": settings.mode,
        "dataset_sha256": digest((SUITE_ROOT / "cases.json").read_bytes()),
        "runner_sha256": digest(Path(__file__).read_bytes()),
        "recipe_sha256": digest(recipe.encode()),
        "summary": summarize(all_attempts),
        "by_split": {
            each_split: summarize(
                [
                    each_attempt
                    for each_attempt in all_attempts
                    if each_attempt["split"] == each_split
                ]
            )
            for each_split in {each_attempt["split"] for each_attempt in all_attempts}
        },
        "environment": _environment(settings),
    }
    report_text = json.dumps(summary_by_key, indent=JSON_INDENT)
    (settings.output / "summary.json").write_text(
        report_text + NEWLINE, encoding="utf-8"
    )
    logger.info("%s", report_text)


def evaluation_exit_code(all_attempts: list[dict]) -> int:
    """Return failure when an attempt is missing, invalid or incorrect.

    Args:
        all_attempts: Attempt records to assess.

    Returns:
        Zero for passing attempts and one for any failure.
    """
    return (
        0
        if all_attempts
        and all(
            each_attempt["status"] == "scored" and each_attempt["grade"]["pass"]
            for each_attempt in all_attempts
        )
        else 1
    )


def _validate_all_controls(all_cases: list[dict]) -> None:
    for each_case in all_cases:
        _validate_controls(each_case)
    logger.info(
        "witnesses=%s good_controls=%s bad_controls=%s model_calls=0",
        len(all_cases),
        len(all_cases),
        len(all_cases),
    )


def main() -> int:
    """Run controller validation or a bounded evaluation.

    Returns:
        Process exit status.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = _parse_arguments()
    all_cases = cases()
    for each_case in all_cases:
        verify_witness(each_case)
    if settings.mode == "validate":
        _validate_all_controls(all_cases)
        return 0
    _validate_settings(settings)
    recipe = (
        SUITE_ROOT.parents[2] / "e-code-review" / "reference" / "low.md"
    ).read_text(encoding="utf-8")
    all_selected = [
        each_case
        for each_case in all_cases
        if settings.split == "all" or each_case["split"] == settings.split
    ][: settings.limit]
    settings.output.mkdir(parents=True)
    all_attempts = _run_cases(all_selected, settings, recipe)
    _write_report(all_attempts, settings, recipe)
    return evaluation_exit_code(all_attempts)


if __name__ == "__main__":
    raise SystemExit(main())
