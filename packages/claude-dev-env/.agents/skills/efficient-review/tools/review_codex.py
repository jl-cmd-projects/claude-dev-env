"""Read a Codex review rollout."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from tools.config import review_run_constants as c


def codex_home(all_variables: Mapping[str, str]) -> Path:
    """Return the configured Codex home, or the default home folder.

    Args:
        all_variables: The process environment.

    Returns:
        The Codex home directory.
    """
    configured = all_variables.get(c.CODEX_HOME_ENVIRONMENT)
    if configured:
        return Path(configured)
    return Path.home() / c.DEFAULT_CODEX_HOME_NAME


def codex_record_from_rollouts(
    home: Path, started_at: float, checkout: Path
) -> dict:
    """Return the review, models, and tool calls of one Codex run.

    Args:
        home: The Codex home for this attempt.
        started_at: The launch time, as seconds since the epoch.
        checkout: The reviewed checkout.

    Returns:
        The review record fields the runner stores.
    """
    combined = _empty_rollout()
    resolved_checkout = checkout.resolve()
    for each_path in _recent_rollouts(home, started_at):
        rollout = _read_codex_rollout(
            each_path.read_text(encoding=c.JSON_READ_ENCODING, errors="replace")
        )
        if _same_checkout(rollout["cwd"], resolved_checkout):
            _merge_rollout(combined, rollout)
    return _codex_record(combined)


def _recent_rollouts(home: Path, started_at: float) -> list[Path]:
    sessions = home / c.CODEX_SESSIONS_DIRECTORY
    if not sessions.is_dir():
        return []
    return [
        each_path
        for each_path in sorted(sessions.rglob(c.CODEX_ROLLOUT_GLOB))
        if each_path.stat().st_mtime >= started_at - c.CODEX_LAUNCH_SLACK_SECONDS
    ]


def _same_checkout(cwd: object, resolved_checkout: Path) -> bool:
    return os.path.normcase(str(Path(str(cwd or ".")).resolve())) == os.path.normcase(
        str(resolved_checkout)
    )


def _empty_rollout() -> dict:
    return {
        "models": set(),
        "efforts": set(),
        "tool_calls": [],
        "trace": [],
        "review_output": None,
        "final_message": "",
        "usage": {},
    }


def _merge_rollout(combined: dict, rollout: dict) -> None:
    combined["models"].update(rollout["models"])
    combined["efforts"].update(rollout["efforts"])
    combined["tool_calls"].extend(rollout["tool_calls"])
    combined["trace"].extend(rollout["trace"])
    if rollout["review_output"] is not None:
        combined["review_output"] = rollout["review_output"]
    if rollout["final_message"]:
        combined["final_message"] = rollout["final_message"]
    for each_key, each_count in rollout["usage"].items():
        combined["usage"][each_key] = combined["usage"].get(each_key, 0) + each_count


def _codex_record(combined: dict) -> dict:
    review_body = combined["review_output"]
    return {
        "review_text": json.dumps(review_body or {}, indent=c.JSON_INDENT),
        "review_output": review_body,
        "final_message": combined["final_message"],
        "all_served_models": sorted(combined["models"]),
        "all_tool_calls": combined["tool_calls"],
        "trace": combined["trace"],
    }


def _read_codex_rollout(text: str) -> dict:
    rollout = _empty_rollout()
    rollout["cwd"] = ""
    for each_line in text.splitlines():
        all_entry = _json_object(each_line)
        if all_entry is not None:
            _read_codex_entry(rollout, all_entry)
    return rollout


def _json_object(line: str) -> Mapping | None:
    try:
        loaded = json.loads(line)
    except ValueError:
        return None
    if isinstance(loaded, Mapping):
        return loaded
    return None


def _read_codex_entry(rollout: dict, all_entry: Mapping) -> None:
    payload = all_entry.get("payload")
    if isinstance(payload, Mapping):
        _read_codex_rollout_entry(rollout, all_entry.get("type"), payload)


def _read_codex_rollout_entry(
    rollout: dict, entry_type: object, all_payload: Mapping
) -> None:
    payload_type = all_payload.get("type")
    if entry_type == "session_meta":
        rollout["cwd"] = str(all_payload.get("cwd", ""))
    if entry_type == "turn_context":
        rollout["models"].add(str(all_payload.get("model", "")))
        rollout["efforts"].add(str(all_payload.get("effort", "")))
    if entry_type == "response_item" and payload_type in c.ALL_CODEX_TOOL_CALL_TYPES:
        _record_tool_turn(rollout, all_payload, payload_type)
    if entry_type == "event_msg":
        _read_codex_event(rollout, payload_type, all_payload)


def _record_tool_turn(
    rollout: dict, all_payload: Mapping, payload_type: object
) -> None:
    call_text = json.dumps(
        all_payload.get("arguments")
        or all_payload.get("action")
        or all_payload.get("input")
    )
    _record_codex_tool_call(
        rollout, str(all_payload.get("name", payload_type)), call_text
    )


def _read_codex_event(
    rollout: dict, payload_type: object, all_payload: Mapping
) -> None:
    if payload_type == "token_count":
        _record_token_count(rollout, all_payload)
    if payload_type in c.ALL_CODEX_OUTSIDE_CALL_EVENTS:
        _record_codex_tool_call(
            rollout, str(payload_type), json.dumps(all_payload, default=str)
        )
    if payload_type == "task_complete":
        rollout["final_message"] = str(all_payload.get("last_agent_message") or "")
    if payload_type in c.ALL_CODEX_REVIEW_END_EVENTS:
        _record_review_body(rollout, all_payload)


def _record_token_count(rollout: dict, all_payload: Mapping) -> None:
    totals = (all_payload.get("info") or {}).get("total_token_usage") or {}
    if not isinstance(totals, Mapping):
        return
    rollout["usage"] = {
        each_usage_key: int(each_token_count)
        for each_usage_key, each_token_count in totals.items()
        if isinstance(each_token_count, int)
    }


def _record_review_body(rollout: dict, all_payload: Mapping) -> None:
    codex_review = _codex_review_from_event(all_payload)
    if codex_review is None:
        return
    rollout["review_output"] = codex_review
    rollout["trace"].append(
        {"role": "assistant", "content": json.dumps(codex_review, indent=c.JSON_INDENT)}
    )


def _codex_review_from_event(all_payload: Mapping) -> Mapping | None:
    candidate: object = all_payload.get("review_output")
    if all_payload.get("type") == "task_complete":
        candidate = _parsed_last_message(all_payload)
    if isinstance(candidate, Mapping) and isinstance(candidate.get("findings"), list):
        return candidate
    return None


def _parsed_last_message(all_payload: Mapping) -> object:
    try:
        return json.loads(str(all_payload.get("last_agent_message") or ""))
    except ValueError:
        return None


def _record_codex_tool_call(rollout: dict, name: str, call_text: str) -> None:
    rollout["tool_calls"].append(f"{name} {call_text}")
    rollout["trace"].append({"role": "tool_call", "name": name, "content": call_text})
