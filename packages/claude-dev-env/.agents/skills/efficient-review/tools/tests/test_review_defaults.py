"""Plan defaults and the model gate for a portable efficient review."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[2]
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from hooks.efficient_review_model_gate import block_reason_for_payload
from tools.config.efficient_review_constants import ACCOUNT_SOURCE_ROSTER
from tools.efficient_review_launch import discover_accounts
from tools.efficient_review_request import load_defaults, parse_request


def test_plan_request_uses_haiku_and_auto() -> None:
    request = parse_request([], load_defaults())
    assert request.model == "haiku"
    assert request.mode == "auto"


def test_accounts_without_launchers_follow_the_settings_roster(tmp_path: Path) -> None:
    all_accounts, source = discover_accounts(tmp_path)
    assert all_accounts == []
    assert source == ACCOUNT_SOURCE_ROSTER


def test_model_gate_denies_opus_and_allows_a_blank_model() -> None:
    denied = block_reason_for_payload(
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "python -m tools.efficient_review run model=opus",
            },
        }
    )
    assert denied is not None
    assert "haiku" in denied
    assert (
        block_reason_for_payload(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "python -m tools.efficient_review run"},
            }
        )
        is None
    )


def test_model_gate_allows_a_family_the_newest_message_names(tmp_path: Path) -> None:
    transcript_path = tmp_path / "transcript.jsonl"
    transcript_path.write_text(
        json.dumps(
            {
                "type": "user",
                "message": {"content": "run this review on sonnet"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert (
        block_reason_for_payload(
            {
                "tool_name": "Bash",
                "tool_input": {
                    "command": "python -m tools.efficient_review run model=sonnet",
                },
                "transcript_path": str(transcript_path),
            }
        )
        is None
    )
