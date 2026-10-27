"""Build the results-file row for one scored scope-boundary session."""

from session_eval_support.grading import ToolCall, tool_calls
from session_eval_support.session import (
    SessionRun,
    SessionSettings,
    final_event,
    served_models,
)

from scope_eval_support.config.constants import LATENCY_DECIMALS, STATUS_OK
from scope_eval_support.grading import decision_questions


def _row_meta(
    all_calls: list[ToolCall],
    final_by_field: dict[str, object],
    settings: SessionSettings,
    meta_by_field: dict[str, object],
) -> dict[str, object]:
    return {
        "questions": decision_questions(all_calls),
        "num_turns": final_by_field.get("num_turns"),
        "effort": settings.effort,
        **meta_by_field,
    }


def _session_fields(
    session_run: SessionRun,
    final_by_field: dict[str, object],
    all_calls: list[ToolCall],
    settings: SessionSettings,
) -> dict[str, object]:
    return {
        "stop_reason": final_by_field.get("subtype"),
        "status": STATUS_OK,
        "model": settings.model,
        "served_models": served_models(final_by_field),
        "usage": final_by_field.get("usage"),
        "cost_usd": final_by_field.get("total_cost_usd"),
        "latency_s": round(session_run.latency_seconds, LATENCY_DECIMALS),
        "tool_calls": len(all_calls),
    }


def _case_fields(case_by_field: dict[str, str], rep: int) -> dict[str, object]:
    return {
        "prompt_id": case_by_field["id"],
        "rep": rep,
        "prompt": case_by_field["prompt"],
        "tags": [case_by_field["group"], case_by_field["source"]],
    }


def scored_row(
    case_by_field: dict[str, str],
    rep: int,
    session_run: SessionRun,
    settings: SessionSettings,
    grade_by_metric: dict[str, int],
    meta_by_field: dict[str, object],
) -> dict[str, object]:
    """Return the results-file row for one session the judge scored.

    Args:
        case_by_field: The case, with its id, prompt, group and source.
        rep: The repetition number.
        session_run: What the session left behind.
        settings: The run's session settings.
        grade_by_metric: The grade from grading.grade_session.
        meta_by_field: The judge record, edited paths and run digest.

    Returns:
        The row, with the session's spend and the given meta.
    """
    final_by_field = final_event(session_run.all_events) or {}
    all_calls = tool_calls(session_run.all_events)
    return {
        **_case_fields(case_by_field, rep),
        **_session_fields(session_run, final_by_field, all_calls, settings),
        "grade": grade_by_metric,
        "meta": _row_meta(all_calls, final_by_field, settings, meta_by_field),
    }
