"""Deterministic review labels, witnesses and trace integrity checks."""

import hashlib
import json
import math
import subprocess
import sys

from review_eval_support.config.constants import (
    ALL_ALLOWED_TRACE_BLOCKS,
    ALL_CATEGORIES,
    ALL_COUNT_FIELDS,
    ALL_FINDING_FIELDS,
    ALL_WITNESS_STATES,
    CATEGORY_SEPARATOR,
    MAX_FINDINGS,
    NEWLINE,
    PROMPT_FORMAT,
    PROMPT_SCENARIO,
    PROMPT_START,
    SUITE_ROOT,
    WILSON_CENTER_FACTOR,
    WILSON_POWER,
    WILSON_VARIANCE_FACTOR,
    WILSON_Z,
    WITNESS_CALL,
    WITNESS_END,
    WITNESS_SECONDS,
    WITNESS_START,
)


class EvaluationRunFatal(ValueError):
    """Invalid controller evidence stops the evaluation."""


class EvaluationItemBlocked(ValueError):
    """An invalid model reply prevents scoring this attempt."""


def digest(payload_bytes: bytes) -> str:
    """Hash the exact captured bytes.

    Args:
        payload_bytes: Captured evidence bytes.

    Returns:
        Hexadecimal SHA-256 digest.
    """
    return hashlib.sha256(payload_bytes).hexdigest()


def cases() -> list[dict]:
    """Load cases with unique identifiers and disjoint group splits.

    Raises:
        EvaluationRunFatal: Case identity or split is inconsistent.

    Returns:
        Validated case records.
    """
    all_cases = json.loads((SUITE_ROOT / "cases.json").read_text(encoding="utf-8"))
    all_identifiers = [each_case["id"] for each_case in all_cases]
    if len(all_identifiers) != len(set(all_identifiers)):
        raise EvaluationRunFatal("duplicate case ID")
    split_by_group = {}
    for each_case in all_cases:
        split_by_group.setdefault(each_case["group"], set()).add(each_case["split"])
    if any(len(each_split) != 1 for each_split in split_by_group.values()):
        raise EvaluationRunFatal("related case group crosses split")
    return all_cases


def _witness_code(each_case: dict, all_prefixes: tuple[str, str]) -> str:
    return NEWLINE.join(
        each_line[1:]
        for each_line in each_case["input"].splitlines()
        if each_line.startswith(all_prefixes)
    )


def _witness_observed(each_case: dict, all_prefixes: tuple[str, str]) -> object:
    source = (
        WITNESS_START
        + _witness_code(each_case, all_prefixes)
        + WITNESS_CALL
        + each_case["witness"]["expression"]
        + WITNESS_END
    )
    completed_call = subprocess.run(
        [sys.executable, "-I", "-S", "-c", source],
        capture_output=True,
        text=True,
        check=True,
        timeout=WITNESS_SECONDS,
    )
    return json.loads(completed_call.stdout)


def verify_witness(each_case: dict) -> None:
    """Check the before and after program for the controller's witness.

    Args:
        each_case: Trusted repository-authored case.
    Raises:
        EvaluationRunFatal: The code and label disagree.
    """
    for each_prefixes, each_target in ALL_WITNESS_STATES:
        if (
            _witness_observed(each_case, each_prefixes)
            != each_case["witness"][each_target]
        ):
            raise EvaluationRunFatal(
                f"witness mismatch: {each_case['id']} {each_target}"
            )
    if bool(each_case["expected"]) != (
        each_case["witness"]["observed"] != each_case["witness"]["expected"]
    ):
        raise EvaluationRunFatal(f"label mismatch: {each_case['id']}")


def _validate_finding(each_finding: dict) -> None:
    if not isinstance(each_finding, dict) or set(each_finding) != ALL_FINDING_FIELDS:
        raise EvaluationItemBlocked("finding schema")
    if (
        type(each_finding["line"]) is not int
        or each_finding["line"] < 1
        or each_finding["category"] not in ALL_CATEGORIES
    ):
        raise EvaluationItemBlocked("finding label")
    if (
        not isinstance(each_finding["failure_scenario"], str)
        or not each_finding["failure_scenario"].strip()
    ):
        raise EvaluationItemBlocked("missing scenario")


def _validated_findings(reply_by_key: object) -> list[dict]:
    if (
        not isinstance(reply_by_key, dict)
        or set(reply_by_key) != {"findings"}
        or not isinstance(reply_by_key["findings"], list)
    ):
        raise EvaluationItemBlocked("response schema")
    all_findings = reply_by_key["findings"]
    if len(all_findings) > MAX_FINDINGS:
        raise EvaluationItemBlocked("finding cap")
    for each_finding in all_findings:
        _validate_finding(each_finding)
    return all_findings


def _finding_counts(each_case: dict, all_findings: list[dict]) -> dict:
    all_expected = {
        (each_finding["line"], each_finding["category"])
        for each_finding in each_case["expected"]
    }
    all_predicted = [
        (each_finding["line"], each_finding["category"])
        for each_finding in all_findings
    ]
    matched = len(all_expected.intersection(all_predicted))
    return {
        "tp": matched,
        "fp": len(all_predicted) - matched,
        "fn": len(all_expected) - matched,
        "pass": matched == len(all_expected) and len(all_predicted) == matched,
        "clean": not all_expected,
    }


def grade(each_case: dict, reply_by_key: object) -> dict:
    """Count localized defects and false alarms without duplicate credit.

    Args:
        each_case: Controller labels for this case.
        reply_by_key: Untrusted captured JSON reply.
    Returns:
        Localized finding counts and clean-case verdict.
    Raises:
        EvaluationItemBlocked: The reply violates the output schema.
    """
    return _finding_counts(each_case, _validated_findings(reply_by_key))


def _divide(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _wilson_interval(passes: int, count: int) -> list[float] | None:
    if not count:
        return None
    proportion = passes / count
    denominator = 1 + WILSON_Z**WILSON_POWER / count
    center = (
        proportion + WILSON_Z**WILSON_POWER / (WILSON_CENTER_FACTOR * count)
    ) / denominator
    margin = (
        WILSON_Z
        * math.sqrt(
            proportion * (1 - proportion) / count
            + WILSON_Z**WILSON_POWER / (WILSON_VARIANCE_FACTOR * count**WILSON_POWER)
        )
        / denominator
    )
    return [center - margin, center + margin]


def _attempt_counts(all_attempts: list[dict], all_scored: list[dict]) -> dict:
    passes = sum(each_attempt["grade"]["pass"] for each_attempt in all_scored)
    count = len(all_scored)
    return {
        "attempted": len(all_attempts),
        "scored": count,
        "infra_errors": sum(
            each_attempt["status"] == "infra_error" for each_attempt in all_attempts
        ),
        "output_errors": sum(
            each_attempt["status"] == "output_error" for each_attempt in all_attempts
        ),
        "passes": passes,
        "pass_rate": _divide(passes, count),
        "pass_rate_wilson_95": _wilson_interval(passes, count),
    }


def _finding_metrics(all_scored: list[dict]) -> dict:
    count_by_metric = {
        each_key: sum(each_attempt["grade"][each_key] for each_attempt in all_scored)
        for each_key in ALL_COUNT_FIELDS
    }
    return {
        "precision": _divide(
            count_by_metric["tp"], count_by_metric["tp"] + count_by_metric["fp"]
        ),
        "recall": _divide(
            count_by_metric["tp"], count_by_metric["tp"] + count_by_metric["fn"]
        ),
        **count_by_metric,
    }


def _clean_metrics(all_scored: list[dict]) -> dict:
    all_clean = [
        each_attempt for each_attempt in all_scored if each_attempt["grade"]["clean"]
    ]
    return {
        "specificity": _divide(
            sum(each_attempt["grade"]["pass"] for each_attempt in all_clean),
            len(all_clean),
        ),
        "false_positive_rate": _divide(
            sum(not each_attempt["grade"]["pass"] for each_attempt in all_clean),
            len(all_clean),
        ),
    }


def summarize(all_attempts: list[dict]) -> dict:
    """Report task scores separately from infrastructure and output errors.

    Args:
        all_attempts: Every attempted case, including failed captures.
    Returns:
        Metrics with separate infrastructure and output failures.
    """
    all_scored = [
        each_attempt
        for each_attempt in all_attempts
        if each_attempt["status"] == "scored"
    ]
    return {
        **_attempt_counts(all_attempts, all_scored),
        **_finding_metrics(all_scored),
        **_clean_metrics(all_scored),
    }


def prompt(each_case: dict, recipe: str) -> str:
    """Supply the task and recipe while keeping controller labels hidden.

    Args:
        each_case: Case containing contract and diff.
        recipe: Review recipe text.

    Returns:
        Task prompt with controller labels omitted.
    """
    return NEWLINE.join(
        [
            PROMPT_START,
            recipe,
            PROMPT_FORMAT + CATEGORY_SEPARATOR.join(ALL_CATEGORIES),
            PROMPT_SCENARIO,
            each_case["input"],
        ]
    )


def validate_trace(all_events: list[dict], reply_by_key: object) -> None:
    """Require completed inference, no tools and matching captured output.

    Args:
        all_events: Raw Codex JSONL events.
        reply_by_key: Captured final JSON reply.
    Raises:
        EvaluationItemBlocked: Trace provenance cannot support scoring.
    """
    if not any(
        each_event.get("type") == "thread.started" for each_event in all_events
    ) or not any(
        each_event.get("type") == "turn.completed" for each_event in all_events
    ):
        raise EvaluationItemBlocked("incomplete_trace")
    all_blocks = [
        each_event["item"] for each_event in all_events if "item" in each_event
    ]
    if any(
        each_block.get("type") not in ALL_ALLOWED_TRACE_BLOCKS
        for each_block in all_blocks
    ):
        raise EvaluationItemBlocked("unexpected_tool_or_error")
    all_messages = [
        each_block["text"]
        for each_block in all_blocks
        if each_block.get("type") == "agent_message"
    ]
    if not all_messages or json.loads(all_messages[-1]) != reply_by_key:
        raise EvaluationItemBlocked("trace_response_mismatch")
