"""Make the judge call the open tasks Stop gate makes, once per eval case and run, and keep one row per call.

::

    case {"id": "twins/INC1", "prompt": "...", "reply": "... will be waiting when you return."}
      -> row {"id": "twins/INC1", "run": 0, "status": "ok", "flags": [true, false], "wall_s": 7.1, ...}

The prompt comes from ``judge_prompt``, the flags from ``judge_command`` with
the model and effort swapped in, the environment from ``child_environment``,
and the working folder is a new empty one. The answer goes through
``parsed_verdict`` and ``gated_verdict``, so the row scores the shipped code.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from judge_eval_support.config.constants import (
    ALL_DIGEST_SOURCES,
    ALL_SCORED_STATUSES,
    ANSWER_COST_KEY,
    ANSWER_IS_ERROR_KEY,
    ANSWER_MODEL_USAGE_KEY,
    ANSWER_RESULT_KEY,
    BLOCKING_DIRECTORY,
    DECODE_ERRORS,
    DIGEST_LENGTH,
    EFFORT_FLAG,
    EXIT_CODE_ERROR_TEMPLATE,
    HOOKS_DIRECTORY,
    IS_ERROR_ERROR,
    JSON_LIST_SUFFIX,
    MODEL_FLAG,
    NOT_JSON_ERROR,
    SECONDS_DECIMALS,
    START_FAILURE_ERROR,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_SHAPE,
    TEXT_ENCODING,
    TIMEOUT_ERROR,
)

for each_import_root in (HOOKS_DIRECTORY, BLOCKING_DIRECTORY):
    if str(each_import_root) not in sys.path:
        sys.path.append(str(each_import_root))

import closing_reply_judge


def read_cases(cases_path: Path) -> list[dict]:
    """Return the case rows of a ``.json`` list or a ``.jsonl`` file.

    Args:
        cases_path: The cases file.

    Returns:
        Each case row, with its id, label, prompt and reply.
    """
    text = cases_path.read_text(encoding=TEXT_ENCODING)
    if cases_path.suffix == JSON_LIST_SUFFIX:
        return json.loads(text)
    return [
        json.loads(each_line) for each_line in text.splitlines() if each_line.strip()
    ]


def read_call_rows(call_log_path: Path) -> list[dict]:
    """Return the stored call rows of a call log.

    Args:
        call_log_path: The ``results.jsonl`` file the runner appends to.

    Returns:
        Each stored row, or an empty list when the file does not exist.
    """
    if not call_log_path.exists():
        return []
    all_lines = call_log_path.read_text(encoding=TEXT_ENCODING).splitlines()
    return [json.loads(each_line) for each_line in all_lines if each_line.strip()]


def run_digest(cases_path: Path, model: str, effort: str) -> str:
    """Return a short digest of the hook source, the cases file, the model and the effort.

    Args:
        cases_path: The cases file.
        model: The judge model.
        effort: The judge effort.

    Returns:
        The first 16 hex digits of the SHA-256 digest.
    """
    digest = hashlib.sha256()
    for each_path in (*ALL_DIGEST_SOURCES, cases_path):
        digest.update(each_path.read_bytes())
    digest.update(f"{model}|{effort}".encode())
    return digest.hexdigest()[:DIGEST_LENGTH]


def call_command(claude_path: str, model: str, effort: str) -> list[str]:
    """Return the shipped judge command with its model and effort swapped for the given ones.

    Args:
        claude_path: The ``claude`` executable.
        model: The model to run.
        effort: The effort to run at.

    Returns:
        The command line.
    """
    command = closing_reply_judge.judge_command(claude_path)
    command[command.index(MODEL_FLAG) + 1] = model
    command[command.index(EFFORT_FLAG) + 1] = effort
    return command


def _error_row(reason: str, started: float) -> dict:
    return {
        "status": STATUS_ERROR,
        "error": reason,
        "wall_s": round(time.monotonic() - started, SECONDS_DECIMALS),
    }


def _completed_child(
    claude_path: str, model: str, effort: str, judge_prompt: str, timeout_seconds: float
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as empty_folder:
        return subprocess.run(
            call_command(claude_path, model, effort),
            check=False,
            capture_output=True,
            text=True,
            encoding=TEXT_ENCODING,
            errors=DECODE_ERRORS,
            timeout=timeout_seconds,
            cwd=empty_folder,
            env=closing_reply_judge.child_environment(),
            input=judge_prompt,
        )


def _answer(stdout_text: str) -> dict | str:
    try:
        answer = json.loads(stdout_text)
    except ValueError:
        return NOT_JSON_ERROR
    if not isinstance(answer, dict) or not isinstance(
        answer.get(ANSWER_RESULT_KEY), str
    ):
        return NOT_JSON_ERROR
    if answer.get(ANSWER_IS_ERROR_KEY) is True:
        return IS_ERROR_ERROR
    return answer


def _verdict_row(case: dict, answer: dict, wall_seconds: float) -> dict:
    has_question_tool_call = bool(case.get("question_tool"))
    row = {
        "wall_s": wall_seconds,
        "cost_usd": answer.get(ANSWER_COST_KEY),
        "models": sorted(answer.get(ANSWER_MODEL_USAGE_KEY) or {}),
        "result": answer[ANSWER_RESULT_KEY],
    }
    verdict = closing_reply_judge.parsed_verdict(
        answer[ANSWER_RESULT_KEY], case["reply"]
    )
    if verdict is None:
        return {**row, "status": STATUS_SHAPE, "flags": [False, False]}
    gated = closing_reply_judge.gated_verdict(
        verdict, case["prompt"], has_question_tool_call
    )
    return {
        **row,
        "status": STATUS_OK,
        "flags": [bool(gated.promise_span), bool(gated.list_span)],
        "promise_span": gated.promise_span,
        "list_span": gated.list_span,
    }


def judge_case(
    case: dict, claude_path: str, model: str, effort: str, timeout_seconds: float
) -> dict:
    """Run one judge call on a case and return its row.

    ::

        a verdict the parser accepts   -> status ok, the gated flags and spans
        prose, or a span not in reply  -> status shape, flags [false, false]
        timeout, exit code, is_error   -> status error, with the reason

    Args:
        case: The case row.
        claude_path: The ``claude`` executable.
        model: The model to run.
        effort: The effort to run at.
        timeout_seconds: How long the child may run.

    Returns:
        The row: status, flags, spans, wall time, cost and served models.
    """
    judge_prompt = closing_reply_judge.judge_prompt(
        case["prompt"], case["reply"], bool(case.get("question_tool"))
    )
    started = time.monotonic()
    try:
        completed_process = _completed_child(
            claude_path, model, effort, judge_prompt, timeout_seconds
        )
    except subprocess.TimeoutExpired:
        return _error_row(TIMEOUT_ERROR, started)
    except OSError:
        return _error_row(START_FAILURE_ERROR, started)
    if completed_process.returncode != 0:
        return _error_row(
            EXIT_CODE_ERROR_TEMPLATE.format(exit_code=completed_process.returncode),
            started,
        )
    answer = _answer(completed_process.stdout)
    if isinstance(answer, str):
        return _error_row(answer, started)
    return _verdict_row(
        case, answer, round(time.monotonic() - started, SECONDS_DECIMALS)
    )


def _stored_counts(all_stored_rows: list[dict], digest: str) -> tuple[set, dict]:
    all_scored_keys: set[tuple[str, int]] = set()
    error_counts: dict[tuple[str, int], int] = defaultdict(int)
    for each_row in all_stored_rows:
        if each_row.get("digest") != digest:
            continue
        key = (each_row["id"], each_row["run"])
        if each_row["status"] in ALL_SCORED_STATUSES:
            all_scored_keys.add(key)
        else:
            error_counts[key] += 1
    return all_scored_keys, error_counts


def pending_calls(
    all_cases: list[dict],
    all_stored_rows: list[dict],
    digest: str,
    runs: int,
    attempts: int,
) -> list[tuple[dict, int]]:
    """Return each (case, run) still to call under the digest.

    Args:
        all_cases: The case rows.
        all_stored_rows: The rows already in the call log.
        digest: The digest of this run's hook source, cases, model and effort.
        runs: How many runs each case gets.
        attempts: How many error rows a (case, run) may hold before it is scored as not held.

    Returns:
        Each (case, run) with no scored row and fewer error rows than ``attempts``.
    """
    all_scored_keys, error_counts = _stored_counts(all_stored_rows, digest)
    return [
        (each_case, each_run)
        for each_run in range(runs)
        for each_case in all_cases
        if (each_case["id"], each_run) not in all_scored_keys
        and error_counts[(each_case["id"], each_run)] < attempts
    ]


def run_calls(
    all_calls: list[tuple[dict, int]],
    call_settings: dict,
    call_log_path: Path,
    workers: int,
) -> None:
    """Make each call on a thread pool and append one row per call to the call log.

    Args:
        all_calls: Each (case, run) to call.
        call_settings: The ``claude_path``, ``model``, ``effort``, ``timeout_seconds`` and ``digest``.
        call_log_path: The ``results.jsonl`` file to append to.
        workers: How many calls run at once.
    """
    write_lock = threading.Lock()

    def _make_call(all_case_and_run: tuple[dict, int]) -> None:
        case, run_index = all_case_and_run
        row = judge_case(
            case,
            call_settings["claude_path"],
            call_settings["model"],
            call_settings["effort"],
            call_settings["timeout_seconds"],
        )
        row = {
            "id": case["id"],
            "run": run_index,
            "digest": call_settings["digest"],
            **row,
        }
        with write_lock, call_log_path.open("a", encoding=TEXT_ENCODING) as call_log:
            call_log.write(json.dumps(row, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(_make_call, all_calls))
