"""Behavior tests for session event reading."""

from session_eval_support.session import final_event, served_models


def test_final_event_returns_last_result() -> None:
    events = [
        {"type": "result", "subtype": "first"},
        {"type": "assistant"},
        {"type": "result", "subtype": "last"},
    ]

    assert final_event(events) == events[-1]
    assert final_event([{"type": "assistant"}]) is None


def test_served_models_sorts_usage_keys() -> None:
    assert served_models({"modelUsage": {"z": {}, "a": {}}}) == ["a", "z"]
    assert served_models({}) == []
