"""The cases expect build-eval only for a feature that changes a file agents read or load."""

import json
from pathlib import Path

CASES_PATH = Path(__file__).resolve().parent / "cases.json"
AGENT_SURFACE_FEATURE_GROUP = "agent-surface-feature"


def _all_cases() -> list[dict[str, str]]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def test_only_agent_surface_features_should_expect_build_eval() -> None:
    all_mismatched_ids = [
        each_case["id"]
        for each_case in _all_cases()
        if (each_case["expected"] == "build-eval")
        != (each_case["group"] == AGENT_SURFACE_FEATURE_GROUP)
    ]
    assert all_mismatched_ids == []


def test_cases_should_hold_at_least_two_agent_surface_features() -> None:
    all_agent_surface_ids = [
        each_case["id"]
        for each_case in _all_cases()
        if each_case["group"] == AGENT_SURFACE_FEATURE_GROUP
    ]
    assert len(all_agent_surface_ids) >= 2
