"""Read what a session spawned and what each child ran at, then grade it."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from routing_eval_support.config.constants import (
    ALL_ALLOWED_EFFORTS_BY_FAMILY,
    ALL_SPAWN_TOOL_NAMES,
    ASSISTANT_ENTRY_TYPE,
    CHILD_META_SUFFIX,
    CHILD_TRANSCRIPT_PATTERN_TEMPLATE,
    CHILD_TRANSCRIPT_SUFFIX,
    EFFORT_INPUT_KEY,
    ENTRY_EFFORT_FIELD,
    ENTRY_MESSAGE_FIELD,
    ENTRY_TURN_EFFORT_FIELD,
    ENTRY_TYPE_FIELD,
    HOOK_OUTPUT_FIELD,
    HOOK_RESPONSE_SUBTYPE,
    HOOK_SPECIFIC_OUTPUT_FIELD,
    META_AGENT_TYPE_FIELD,
    META_TOOL_USE_ID_FIELD,
    MODEL_INPUT_KEY,
    SESSION_ID_FIELD,
    UPDATED_INPUT_FIELD,
)
from session_eval_support.grading import ToolCall


@dataclass(frozen=True)
class ChildRun:
    """One child agent and every (model, effort) pair its turns ran at."""

    tool_use_id: str | None
    agent_type: str | None
    all_pairs: tuple[tuple[str, str | None], ...] = field(default_factory=tuple)


def model_family(model: object) -> str | None:
    """Return the Anthropic family a model alias or id names.

    ::

        "claude-opus-5-5" -> "opus"     "haiku" -> "haiku"     "gpt-5" -> None

    Args:
        model: A model alias, a model id, or anything else.

    Returns:
        The family name, or None when the model names no Anthropic family.
    """
    if not isinstance(model, str):
        return None
    lowered_model = model.lower()
    return next(
        (each_family for each_family in ALL_ALLOWED_EFFORTS_BY_FAMILY if each_family in lowered_model),
        None,
    )


def is_allowed_pair(model: object, effort: object) -> bool:
    """Return True when the rule's table allows the model at the effort.

    ::

        ("claude-opus-5-5", "high") -> True       ("opus", "max") -> False
        ("claude-haiku-5-5", "max") -> True       ("gpt-5", "low") -> False

    Args:
        model: A model alias or id.
        effort: An effort level, or None when it is unknown.
    """
    family = model_family(model)
    return family is not None and effort in ALL_ALLOWED_EFFORTS_BY_FAMILY[family]


def spawn_calls(all_calls: Iterable[ToolCall]) -> list[ToolCall]:
    """Return the Agent and Task calls in the order the session made them.

    Args:
        all_calls: Every tool call of the session.
    """
    return [each_call for each_call in all_calls if each_call.name in ALL_SPAWN_TOOL_NAMES]


def named_in_rule(call: ToolCall) -> bool:
    """Return True when a spawn names a model and an effort the table allows.

    Args:
        call: One Agent or Task call.
    """
    return is_allowed_pair(
        call.tool_input.get(MODEL_INPUT_KEY), call.tool_input.get(EFFORT_INPUT_KEY)
    )


def session_id(all_events: Iterable[Mapping[str, object]]) -> str | None:
    """Return the session id the stream's events carry.

    Args:
        all_events: The session's stream-json events.

    Returns:
        The first non-empty ``session_id``, or None when no event has one.
    """
    for each_event in all_events:
        found_id = each_event.get(SESSION_ID_FIELD)
        if isinstance(found_id, str) and found_id:
            return found_id
    return None


def routed_count(all_events: Iterable[Mapping[str, object]]) -> int:
    """Return how many hook responses changed a tool call's input.

    Args:
        all_events: The session's stream-json events, with hook events in them.

    Returns:
        The count of hook responses whose output holds ``updatedInput``.
    """
    routed = 0
    for each_event in all_events:
        if each_event.get("subtype") != HOOK_RESPONSE_SUBTYPE:
            continue
        try:
            hook_reply = json.loads(str(each_event.get(HOOK_OUTPUT_FIELD) or ""))
        except json.JSONDecodeError:
            continue
        specific = hook_reply.get(HOOK_SPECIFIC_OUTPUT_FIELD) if isinstance(hook_reply, dict) else None
        if isinstance(specific, dict) and UPDATED_INPUT_FIELD in specific:
            routed += 1
    return routed


def _turn_pairs(transcript_text: str) -> tuple[tuple[str, str | None], ...]:
    all_pairs: list[tuple[str, str | None]] = []
    for each_line in transcript_text.splitlines():
        try:
            entry = json.loads(each_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict) or entry.get(ENTRY_TYPE_FIELD) != ASSISTANT_ENTRY_TYPE:
            continue
        message = entry.get(ENTRY_MESSAGE_FIELD)
        model = message.get(MODEL_INPUT_KEY) if isinstance(message, dict) else None
        if isinstance(model, str):
            effort = entry.get(ENTRY_TURN_EFFORT_FIELD) or entry.get(ENTRY_EFFORT_FIELD)
            all_pairs.append((model, effort if isinstance(effort, str) else None))
    return tuple(all_pairs)


def _child_meta(transcript_path: Path) -> dict[str, object]:
    meta_path = transcript_path.with_name(
        transcript_path.name.removesuffix(CHILD_TRANSCRIPT_SUFFIX) + CHILD_META_SUFFIX
    )
    try:
        loaded = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def child_runs(projects_directory: Path, found_session_id: str) -> list[ChildRun]:
    """Return each child agent the session started, read from its transcript.

    Args:
        projects_directory: The Claude Code projects folder.
        found_session_id: The parent session's id.

    Returns:
        One ChildRun per child transcript, sorted by file name.
    """
    all_transcripts = sorted(
        projects_directory.glob(CHILD_TRANSCRIPT_PATTERN_TEMPLATE.format(session_id=found_session_id))
    )
    all_children = []
    for each_path in all_transcripts:
        meta = _child_meta(each_path)
        all_children.append(
            ChildRun(
                meta.get(META_TOOL_USE_ID_FIELD) if isinstance(meta.get(META_TOOL_USE_ID_FIELD), str) else None,
                meta.get(META_AGENT_TYPE_FIELD) if isinstance(meta.get(META_AGENT_TYPE_FIELD), str) else None,
                _turn_pairs(each_path.read_text(encoding="utf-8", errors="replace")),
            )
        )
    return all_children


def child_in_rule(child: ChildRun) -> bool:
    """Return True when every turn of the child ran at an allowed pair.

    Args:
        child: One child agent.
    """
    return bool(child.all_pairs) and all(
        is_allowed_pair(each_model, each_effort) for each_model, each_effort in child.all_pairs
    )


def grade_case(
    all_spawns: list[ToolCall], all_children: list[ChildRun], routed: int
) -> dict[str, int]:
    """Grade one session.

    ::

        no spawn                            -> in_rule 1, spawned 0, named_in_rule 0, routed 0
        one Opus child at medium, routed    -> in_rule 1, spawned 1, named_in_rule 0, routed 1
        one Opus child at max               -> in_rule 0, spawned 1

    Args:
        all_spawns: The session's Agent and Task calls.
        all_children: The child agents read from their transcripts.
        routed: How many hook responses changed a call's input.

    Returns:
        ``in_rule``: every child ran at an allowed pair at every turn.
        ``spawned``: the session made at least one spawn.
        ``named_in_rule``: it spawned, and every spawn named an allowed pair.
        ``routed``: the hook changed at least one spawn.
    """
    spawned = bool(all_spawns)
    return {
        "in_rule": int(all(child_in_rule(each_child) for each_child in all_children)),
        "spawned": int(spawned),
        "named_in_rule": int(spawned and all(named_in_rule(each_call) for each_call in all_spawns)),
        "routed": int(routed > 0),
    }
