"""Bounded Codex capture and stored-output replay."""

import argparse
import json
import subprocess
import time
from pathlib import Path

from review_eval_support.config.constants import (
    ALL_CODEX_ARGUMENTS,
    ALL_REPLY_SCHEMA,
    ERROR_TAIL_LENGTH,
    LATENCY_DECIMALS,
    WORKSPACE_SUFFIX,
)
from review_eval_support.grading import (
    EvaluationItemBlocked,
    digest,
    grade,
    prompt,
    validate_trace,
)


def _attempt_header(each_case: dict, settings: argparse.Namespace, recipe: str) -> dict:
    return {
        "id": each_case["id"],
        "group": each_case["group"],
        "split": each_case["split"],
        "mode": "fresh_recipe_with_fixture",
        "model_requested": settings.model,
        "effort": settings.effort,
        "input_sha256": digest(each_case["input"].encode()),
        "recipe_sha256": digest(recipe.encode()),
    }


def _prepare_command(
    each_case: dict, settings: argparse.Namespace, record_root: Path
) -> tuple[list[str], Path]:
    working_directory = record_root.resolve() / (each_case["id"] + WORKSPACE_SUFFIX)
    working_directory.mkdir()
    schema_path = working_directory / "schema.json"
    reply_path = working_directory / "reply.json"
    schema_path.write_text(json.dumps(ALL_REPLY_SCHEMA), encoding="utf-8")
    all_command = [
        settings.codex,
        *ALL_CODEX_ARGUMENTS,
        "--cd",
        str(working_directory),
        "--model",
        settings.model,
        "-c",
        f'model_reasoning_effort="{settings.effort}"',
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(reply_path),
        "--json",
        "-",
    ]
    return all_command, reply_path


def _score_capture(
    each_case: dict, completed_call: subprocess.CompletedProcess[str], reply_path: Path
) -> dict:
    if completed_call.returncode:
        return {
            "status": "infra_error",
            "failure": "provider_or_launcher",
            "detail": completed_call.stderr[-ERROR_TAIL_LENGTH:],
        }
    all_events = [
        json.loads(each_line)
        for each_line in completed_call.stdout.splitlines()
        if each_line.strip().startswith("{")
    ]
    reply_by_key = json.loads(reply_path.read_text(encoding="utf-8"))
    try:
        validate_trace(all_events, reply_by_key)
    except EvaluationItemBlocked as error:
        return {"status": "infra_error", "failure": str(error)}
    return {
        "status": "scored",
        "response": reply_by_key,
        "grade": grade(each_case, reply_by_key),
        "usage": [
            each_event.get("usage")
            for each_event in all_events
            if each_event.get("usage")
        ],
    }


def _capture(
    each_case: dict, settings: argparse.Namespace, record_root: Path, recipe: str
) -> dict:
    all_command, reply_path = _prepare_command(each_case, settings, record_root)
    prompt_text = prompt(each_case, recipe)
    (record_root / f"{each_case['id']}.prompt.txt").write_text(
        prompt_text, encoding="utf-8"
    )
    completed_call = subprocess.run(
        all_command,
        input=prompt_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=settings.timeout,
        check=False,
    )
    (record_root / f"{each_case['id']}.trace.jsonl").write_text(
        completed_call.stdout, encoding="utf-8"
    )
    (record_root / f"{each_case['id']}.stderr.txt").write_text(
        completed_call.stderr, encoding="utf-8"
    )
    return {
        "exit_code": completed_call.returncode,
        **_score_capture(each_case, completed_call, reply_path),
    }


def execute(
    each_case: dict, settings: argparse.Namespace, record_root: Path, recipe: str
) -> dict:
    """Capture one model attempt under its wall-clock ceiling.

    Args:
        each_case: Contract and diff with hidden labels.
        settings: Model, effort, executable and timeout.
        record_root: New run directory.
        recipe: Review recipe text.

    Returns:
        Captured attempt with status and scoring evidence.
    """
    each_attempt = _attempt_header(each_case, settings, recipe)
    started = time.monotonic()
    try:
        each_attempt.update(_capture(each_case, settings, record_root, recipe))
    except subprocess.TimeoutExpired:
        each_attempt.update(status="infra_error", failure="timeout")
    except (ValueError, OSError) as error:
        each_attempt.update(
            status="output_error", failure="schema_or_capture", detail=str(error)
        )
    each_attempt["latency_seconds"] = round(
        time.monotonic() - started, LATENCY_DECIMALS
    )
    return each_attempt


def replay(each_case: dict, reply_by_case_id: dict) -> dict:
    """Score one stored output with no model call.

    Args:
        each_case: Controller labels.
        reply_by_case_id: Captured replies by case ID.

    Returns:
        Stored-output attempt record.
    """
    each_attempt = {
        "id": each_case["id"],
        "split": each_case["split"],
        "mode": "stored_replay",
    }
    try:
        each_attempt.update(
            status="scored", grade=grade(each_case, reply_by_case_id[each_case["id"]])
        )
    except (KeyError, EvaluationItemBlocked) as error:
        each_attempt.update(status="output_error", failure=str(error))
    return each_attempt
