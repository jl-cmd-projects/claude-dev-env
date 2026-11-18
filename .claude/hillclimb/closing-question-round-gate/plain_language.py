"""Grade the footers agents write under a gate's hold reason for plain words a person can read.

::

    python3 plain_language.py --hook <gate.py> --label branch
    python3 plain_language.py --hook <main checkout>/.../closing_question_round_gate.py --label main

Each sample starts from one session in two scenarios: two tasks in progress
and one queued, with 14 background jobs or with none. The agent's first
reply ends with ``Open items: none.``. The gate under test runs on that
reply the way Claude Code runs it. When it holds, a headless ``claude -p``
writer gets the raw session state, full of ids and tool words, the reply,
and the hold reason, and writes the reply again. The gate runs again, up to
two holds. The final reply is graded::

    footer written   the reply ends with an In progress footer
    scan             no id, short form, worker word, or tool word in the footer
    judge            a calibrated headless judge passes every footer line

A sample passes the plain-language criterion when all three hold. With no
footer, the reply's last paragraph is scanned and judged in its place. Every
headless run goes through the account broker with the user's settings left
out, so no hook of the grading session acts on the writer or the judge. One
JSON file per sample lands in ``--out``, and the run prints one row per
sample and a summary line per hook.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from closing_round_eval_support.config.constants import (
    HOOK_FILE,
    HOOK_TIMEOUT_SECONDS,
)
from closing_round_eval_support.config.plain_language_constants import (
    BACKGROUND_LINE,
    BLOCKING_DIRECTORY,
    BROKER_PRODUCT,
    BROKER_REPORT_SUFFIX,
    BROKER_SCRIPT,
    RUN_DIRECTORY_PREFIX,
    DEFAULT_SAMPLE_COUNT,
    DEFAULT_WORKER_COUNT,
    FIRST_REPLY,
    FOOTER_LINE_SEPARATOR,
    JUDGE_ERROR_TEXT_LIMIT,
    LOGGED_TEXT_LIMIT,
    SAMPLE_JSON_INDENT,
    HEADLESS_TIMEOUT_SECONDS,
    HOLD_PROMPT_TEMPLATE,
    JSON_OBJECT_PATTERN,
    JUDGE_EFFORT,
    JUDGE_MODEL,
    JUDGE_PROMPT_TEMPLATE,
    MAXIMUM_HOLD_ROUNDS,
    MISSED_ROW_LABEL,
    NO_BACKGROUND_LINE,
    PARAGRAPH_SPLIT_PATTERN,
    PASSED_ROW_LABEL,
    RAW_STATE_PROMPT,
    ROW_TEMPLATE,
    SAMPLE_FILE_TEMPLATE,
    ALL_SCAN_RULES,
    ALL_SCENARIO_BACKGROUNDS,
    SETTING_SOURCES,
    SUMMARY_TEMPLATE,
    ALL_TASK_ENTRIES,
    TYPED_PROMPT,
    UTF8_ENCODING,
    WRITE_AGAIN_PROMPT,
    WRITER_EFFORT,
    WRITER_MODEL,
)
from run import case_environment, stop_payload, write_task_store

if str(BLOCKING_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BLOCKING_DIRECTORY))

from closing_question_round_footer import split_footer

logger = logging.getLogger(__name__)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hook",
        type=Path,
        default=HOOK_FILE,
        help="The gate script whose reason the writers read.",
    )
    parser.add_argument(
        "--label", default="branch", help="The name for this gate in rows and files."
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=DEFAULT_SAMPLE_COUNT,
        help="Writer runs per scenario.",
    )
    parser.add_argument(
        "--workers", type=int, default=DEFAULT_WORKER_COUNT, help="Samples run at once."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="The folder for one JSON file per sample; a new private temp folder by default.",
    )
    return parser.parse_args()


def scan_hits(footer_text: str) -> list[list[str]]:
    """Return each id, short form, worker word, or tool word the footer holds, once, as [rule, phrase].

    ::

        "I am fixing the list reader in pull request 8801."  -> []
        "Agent a12 pushed 4f3c2e1 to PR 8801."               -> commit hash, coded id, short form, ...

    Args:
        footer_text: The footer lines, or the last paragraph when no footer was written.

    Returns:
        One [rule name, phrase] pair per phrase found.
    """
    all_seen_phrases: set[str] = set()
    all_hits: list[list[str]] = []
    for each_rule_name, each_pattern in ALL_SCAN_RULES:
        for each_match in each_pattern.finditer(footer_text):
            each_phrase = each_match.group(0)
            if each_phrase.lower() in all_seen_phrases:
                continue
            all_seen_phrases.add(each_phrase.lower())
            all_hits.append([each_rule_name, each_phrase])
    return all_hits


def scenario_case(scenario: str, closing_reply: str) -> dict[str, object]:
    """Return the gate case for a scenario.

    The case holds the typed prompt, one work call, the reply, the tasks, and the background jobs.

    Args:
        scenario: The scenario name, a key of the background table.
        closing_reply: The reply the case ends with.

    Returns:
        The case fields the gate runner reads.
    """
    return {
        "id": scenario,
        "tasks": ALL_TASK_ENTRIES,
        "payload": {"background_tasks": ALL_SCENARIO_BACKGROUNDS[scenario]},
        "transcript": [
            {
                "type": "user",
                "turnOrigin": "human",
                "promptSource": "typed",
                "message": {"role": "user", "content": TYPED_PROMPT},
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_b1",
                            "name": "Bash",
                            "input": {"command": "gh pr checks 8801"},
                        }
                    ],
                },
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_b1",
                            "content": "lint pass",
                        }
                    ],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": closing_reply}],
                },
            },
        ],
    }


def gate_reason(hook_path: Path, all_case_fields: dict[str, object]) -> str | None:
    """Run the gate on a case as its own process and return its hold reason.

    None when the gate allows, times out, or prints no JSON object; the last two log a warning.

    Args:
        hook_path: The gate script to run.
        all_case_fields: The case, with its transcript, tasks, and payload fields.

    Returns:
        The hold reason, or None.
    """
    with tempfile.TemporaryDirectory() as case_directory_name:
        case_directory = Path(case_directory_name)
        write_task_store(all_case_fields, case_directory)
        payload = stop_payload(all_case_fields, case_directory)
        try:
            hook_run = subprocess.run(
                [sys.executable, str(hook_path)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                env=case_environment(all_case_fields, case_directory),
                timeout=HOOK_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("gate timed out: %s", hook_path)
            return None
    if not hook_run.stdout.strip():
        return None
    try:
        return str(json.loads(hook_run.stdout).get("reason", ""))
    except (ValueError, AttributeError):
        logger.warning("gate printed no JSON object: %s", hook_run.stdout[:LOGGED_TEXT_LIMIT])
        return None


def headless_text(prompt_text: str, model: str, effort: str, report_path: Path) -> str:
    """Return the text a headless ``claude -p`` run prints, started through the account broker.

    A run that times out returns empty text, and a run that times out or exits non-zero logs a
    warning.

    Args:
        prompt_text: The prompt for the run.
        model: The model the run uses.
        effort: The effort the run uses.
        report_path: Where the broker writes its report.

    Returns:
        The printed text, stripped.
    """
    with tempfile.TemporaryDirectory() as work_directory_name:
        try:
            completed_run = subprocess.run(
                [
                    sys.executable,
                    str(BROKER_SCRIPT),
                    "run",
                    "--product",
                    BROKER_PRODUCT,
                    "--report",
                    str(report_path),
                    "--",
                    "claude",
                    "-p",
                    prompt_text,
                    "--model",
                    model,
                    "--effort",
                    effort,
                    "--setting-sources",
                    SETTING_SOURCES,
                ],
                cwd=work_directory_name,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=HEADLESS_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("headless run timed out: %s", report_path)
            return ""
    if completed_run.returncode != 0:
        logger.warning(
            "headless run exited %s: %s: %s",
            completed_run.returncode,
            report_path,
            completed_run.stderr.strip()[-LOGGED_TEXT_LIMIT:],
        )
    return completed_run.stdout.strip()


def closing_block(closing_reply: str) -> tuple[bool, str]:
    """Return whether the reply ends with a footer, and the text to grade.

    Args:
        closing_reply: The final reply of a sample.

    Returns:
        True and the footer items, one per line, or False and the reply's last paragraph.
    """
    all_footer_lines = split_footer(closing_reply).footer_items
    if all_footer_lines is not None:
        return True, FOOTER_LINE_SEPARATOR.join(all_footer_lines)
    all_paragraphs = [
        each.strip()
        for each in PARAGRAPH_SPLIT_PATTERN.split(closing_reply.strip())
        if each.strip()
    ]
    return False, all_paragraphs[-1] if all_paragraphs else ""


def judged_lines(block_text: str, report_path: Path) -> dict[str, object]:
    """Return the calibrated judge's verdict on a footer.

    Args:
        block_text: The footer lines, or the last paragraph when no footer was written.
        report_path: Where the broker writes the judge run's report.

    Returns:
        The judge's JSON object, or an error record when its answer holds none.
    """
    judge_answer = headless_text(
        JUDGE_PROMPT_TEMPLATE.format(footer=block_text),
        JUDGE_MODEL,
        JUDGE_EFFORT,
        report_path,
    )
    json_match = JSON_OBJECT_PATTERN.search(judge_answer)
    if json_match is None:
        return {"error": judge_answer[-JUDGE_ERROR_TEXT_LIMIT:]}
    try:
        all_verdict_fields = json.loads(json_match.group(0))
    except ValueError:
        return {"error": judge_answer[-JUDGE_ERROR_TEXT_LIMIT:]}
    return (
        all_verdict_fields
        if isinstance(all_verdict_fields, dict)
        else {"error": judge_answer[-JUDGE_ERROR_TEXT_LIMIT:]}
    )


def _judge_passes(all_verdict_fields: dict[str, object]) -> tuple[bool, str]:
    all_lines = all_verdict_fields.get("lines")
    if not isinstance(all_lines, list) or not all_lines:
        return False, "error"
    passed_count = sum(
        bool(each_line.get("pass"))
        and not each_line.get("jargon")
        and not each_line.get("too_long")
        for each_line in all_lines
        if isinstance(each_line, dict)
    )
    return passed_count == len(all_lines), f"{passed_count}/{len(all_lines)}"


def graded_sample(hook_path: Path, scenario: str, sample_path: Path) -> dict[str, object]:
    """Run one writer chain under the gate and grade its final reply.

    Args:
        hook_path: The gate script whose hold reasons the writer reads.
        scenario: A key of the scenario table.
        sample_path: The JSON file this sample is written to; broker reports go beside it.

    Returns:
        The sample record: every reply, every reason, the closing block, and the grades.
    """
    background_line = BACKGROUND_LINE if ALL_SCENARIO_BACKGROUNDS[scenario] else NO_BACKGROUND_LINE
    closing_reply = FIRST_REPLY
    all_replies = [closing_reply]
    all_reasons: list[str] = []
    for each_round in range(MAXIMUM_HOLD_ROUNDS):
        reason = gate_reason(hook_path, scenario_case(scenario, closing_reply))
        if reason is None:
            break
        all_reasons.append(reason)
        writer_prompt = (
            RAW_STATE_PROMPT.format(background_line=background_line, first_reply=closing_reply)
            + HOLD_PROMPT_TEMPLATE.format(reason=reason)
            + WRITE_AGAIN_PROMPT
        )
        report_path = sample_path.with_suffix(f".writer{each_round}{BROKER_REPORT_SUFFIX}")
        closing_reply = (
            headless_text(writer_prompt, WRITER_MODEL, WRITER_EFFORT, report_path) or closing_reply
        )
        all_replies.append(closing_reply)
    final_reason = gate_reason(hook_path, scenario_case(scenario, closing_reply))
    has_footer, block_text = closing_block(closing_reply)
    all_hits = scan_hits(block_text)
    verdict = judged_lines(block_text, sample_path.with_suffix(f".judge{BROKER_REPORT_SUFFIX}"))
    is_judge_pass, judge_lines = _judge_passes(verdict)
    return {
        "scenario": scenario,
        "replies": all_replies,
        "reasons": all_reasons,
        "final_reply_held": final_reason is not None,
        "has_footer": has_footer,
        "block": block_text,
        "scan_hits": all_hits,
        "judge": verdict,
        "judge_lines": judge_lines,
        "passed": has_footer and not all_hits and is_judge_pass,
    }


def main() -> int:
    """Run every sample for one gate, write one file per sample, and print the rows and the summary.

    Returns:
        Zero once every sample is graded.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    arguments = _parse_arguments()
    if arguments.out is None:
        arguments.out = Path(tempfile.mkdtemp(prefix=RUN_DIRECTORY_PREFIX))
    arguments.out.mkdir(parents=True, exist_ok=True)
    logger.info("samples in %s", arguments.out)
    all_jobs = [
        (each_scenario, each_sample)
        for each_scenario in ALL_SCENARIO_BACKGROUNDS
        for each_sample in range(1, arguments.samples + 1)
    ]

    def run_job(all_job_parts: tuple[str, int]) -> tuple[str, int, dict[str, object]]:
        """Grade one sample and write its record.

        Args:
            all_job_parts: The scenario name and the sample number.

        Returns:
            The scenario name, the sample number, and the sample record.
        """
        scenario, sample = all_job_parts
        sample_path = arguments.out / SAMPLE_FILE_TEMPLATE.format(
            hook_label=arguments.label, scenario=scenario, sample=sample
        )
        sample_record = graded_sample(arguments.hook, scenario, sample_path)
        sample_path.write_text(
            json.dumps(sample_record, indent=SAMPLE_JSON_INDENT), encoding=UTF8_ENCODING
        )
        return scenario, sample, sample_record

    with ThreadPoolExecutor(max_workers=arguments.workers) as executor:
        all_graded_samples = list(executor.map(run_job, all_jobs))
    for each_scenario, each_sample, each_record in all_graded_samples:
        logger.info(
            "%s",
            ROW_TEMPLATE.format(
                label=PASSED_ROW_LABEL if each_record["passed"] else MISSED_ROW_LABEL,
                hook_label=arguments.label,
                scenario=each_scenario,
                sample=each_sample,
                has_footer=each_record["has_footer"],
                scan_count=len(each_record["scan_hits"]),
                judge_lines=each_record["judge_lines"],
                hold_count=len(each_record["reasons"]),
                is_final_held=each_record["final_reply_held"],
            ),
        )
    logger.info(
        "%s",
        SUMMARY_TEMPLATE.format(
            hook_label=arguments.label,
            passed_count=sum(
                bool(each_record["passed"])
                for _scenario, _sample, each_record in all_graded_samples
            ),
            footer_count=sum(
                bool(each_record["has_footer"])
                for _scenario, _sample, each_record in all_graded_samples
            ),
            sample_count=len(all_graded_samples),
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
