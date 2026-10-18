"""Read a Claude stream-json review."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from tools.config import review_run_constants as c


@dataclass
class StreamState:
    trace: list[dict] = field(default_factory=list)
    all_tool_calls: list[str] = field(default_factory=list)
    advisor_calls: int = 0
    compactions: int = 0
    peak_context_tokens: int = 0
    all_loaded: Mapping = field(default_factory=dict)
    final: Mapping = field(default_factory=dict)


def claude_record_from_stream(all_lines: Iterable[str]) -> dict:
    """Return the review text, cost, and served models a stream-json run printed.

    Args:
        all_lines: The standard output lines.

    Returns:
        The review record fields the runner stores.
    """
    state = StreamState()
    for each_line in all_lines:
        event = _json_object(each_line)
        if event is not None:
            _apply_stream_event(state, event)
    return _stream_record(state)


def _json_object(line: str) -> Mapping | None:
    try:
        event = json.loads(line)
    except ValueError:
        return None
    if isinstance(event, Mapping):
        return event
    return None


def _apply_stream_event(state: StreamState, all_event: Mapping) -> None:
    if all_event.get("type") == "result":
        state.final = all_event
        return
    _note_subtype(state, all_event)
    message = all_event.get("message")
    _note_peak_context(state, all_event, message)
    if isinstance(message, Mapping) and isinstance(message.get("content"), list):
        _apply_blocks(state, all_event, message["content"])


def _note_subtype(state: StreamState, all_event: Mapping) -> None:
    if all_event.get("subtype") == c.COMPACT_BOUNDARY_SUBTYPE:
        state.compactions += 1
    if all_event.get("subtype") == c.INIT_SUBTYPE:
        state.all_loaded = all_event


def _note_peak_context(state: StreamState, all_event: Mapping, message: object) -> None:
    if all_event.get("type") != "assistant":
        return
    if not isinstance(message, Mapping):
        return
    _note_usage_peak(state, message)


def _note_usage_peak(state: StreamState, all_message: Mapping) -> None:
    usage = all_message.get("usage") or {}
    if isinstance(usage, Mapping):
        state.peak_context_tokens = max(
            state.peak_context_tokens, _context_tokens(usage)
        )


def _context_tokens(all_usage: Mapping) -> int:
    return sum(int(all_usage.get(each_key) or 0) for each_key in c.ALL_CONTEXT_USAGE_KEYS)


def _apply_blocks(state: StreamState, all_event: Mapping, all_blocks: list) -> None:
    for each_block in all_blocks:
        if isinstance(each_block, Mapping):
            _apply_block(state, all_event, each_block)


def _apply_block(state: StreamState, all_event: Mapping, all_block: Mapping) -> None:
    block_type = all_block.get("type")
    if block_type == "server_tool_use" and all_block.get("name") == c.ADVISOR_TOOL_NAME:
        _note_advisor(state)
        return
    if block_type == "tool_use":
        _note_tool_use(state, all_block)
        return
    if block_type == "tool_result":
        state.trace.append({"role": "tool_result", "content": _block_text(all_block)})
        return
    if block_type == "text" and all_event.get("type") == "assistant":
        state.trace.append({"role": "assistant", "content": all_block["text"]})


def _note_advisor(state: StreamState) -> None:
    state.advisor_calls += 1
    state.trace.append(
        {"role": "tool_call", "name": c.ADVISOR_TOOL_NAME, "content": "{}"}
    )


def _note_tool_use(state: StreamState, all_block: Mapping) -> None:
    call_text = json.dumps(all_block.get("input", {}), indent=c.JSON_INDENT)
    state.all_tool_calls.append(f"{all_block.get('name')} {call_text}")
    state.trace.append(
        {"role": "tool_call", "name": str(all_block.get("name")), "content": call_text}
    )


def _block_text(all_block: Mapping) -> str:
    content = all_block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return c.LINE_SEPARATOR.join(
            str(each_part.get("text", ""))
            for each_part in content
            if isinstance(each_part, Mapping)
        )
    return ""


def _stream_record(state: StreamState) -> dict:
    all_model_usage = state.final.get("modelUsage") or {}
    cli_cost = float(state.final.get("total_cost_usd") or 0.0)
    return {
        "review_text": str(state.final.get("result") or ""),
        "is_error": bool(state.final.get("is_error")),
        "cost_usd": model_usage_cost_usd(all_model_usage, cli_cost),
        "all_served_models": sorted(all_model_usage),
        "advisor_calls": state.advisor_calls,
        "compactions": state.compactions,
        "peak_context_tokens": state.peak_context_tokens,
        "all_tool_calls": state.all_tool_calls,
        "trace": state.trace,
    }


def model_usage_cost_usd(all_model_usage: Mapping, cli_cost: float) -> float:
    """Return a run's cost, pricing tokens where the CLI did not know the model.

    Args:
        all_model_usage: The modelUsage object from the final stream event.
        cli_cost: The CLI total_cost_usd number.

    Returns:
        The cost in US dollars.
    """
    if not _has_unknown_cost_basis(all_model_usage):
        return cli_cost
    return sum(
        _priced_usage(str(each_model), each_usage)
        for each_model, each_usage in all_model_usage.items()
    )


def _has_unknown_cost_basis(all_model_usage: Mapping) -> bool:
    return any(
        isinstance(each_usage, Mapping)
        and each_usage.get(c.COST_BASIS_KEY) == c.UNKNOWN_COST_BASIS
        for each_usage in all_model_usage.values()
    )


def _priced_usage(model: str, each_usage: object) -> float:
    if not isinstance(each_usage, Mapping):
        return 0.0
    if each_usage.get(c.COST_BASIS_KEY) != c.UNKNOWN_COST_BASIS:
        return float(each_usage.get("costUSD") or 0.0)
    priced = cost_usd(model, _usage_counts(each_usage))
    if priced is None:
        return float(each_usage.get("costUSD") or 0.0)
    return priced


def _usage_counts(all_usage: Mapping) -> dict[str, object]:
    return {
        each_usage_key: all_usage.get(each_model_usage_key, 0)
        for each_usage_key, each_model_usage_key in c.ALL_MODEL_USAGE_TOKEN_KEYS
    }


def cost_usd(model: str, all_usage: Mapping) -> float | None:
    """Return the list-price cost of one Claude call from its usage block.

    Args:
        model: The model id used for the call.
        all_usage: The token counts from the completed call.

    Returns:
        The cost in US dollars, or None when the model has no price entry.
    """
    prices = c.ALL_PRICE_PER_MILLION_TOKENS.get(model)
    if prices is None:
        return None
    input_dollars = prices["in"] * (
        all_usage.get("input_tokens", 0)
        + c.CACHE_WRITE_MULTIPLIER * all_usage.get("cache_creation_input_tokens", 0)
        + c.CACHE_READ_MULTIPLIER * all_usage.get("cache_read_input_tokens", 0)
    )
    completion_dollars = prices["out"] * all_usage.get("output_tokens", 0)
    return (input_dollars + completion_dollars) / c.TOKENS_PER_MILLION
