import io
import json
import sys
from pathlib import Path

import pytest

import question_brief_gate

QUESTION_ID = "toolu_value_card"
SHORT_POLL_LIMIT_SECONDS = 0.3

SALE_WINDOW_CARD = {
    "questions": [
        {
            "question": (
                "Black Friday is Friday, November 27, 2026. Which discount window should the"
                " Black Friday plan use? The research on window length is unfinished."
            ),
            "header": "BF window",
            "multiSelect": False,
            "options": [
                {"label": "Fri Nov 27 to Mon Nov 30", "description": "Four days."},
                {"label": "Mon Nov 23 to Mon Nov 30", "description": "Eight days."},
                {"label": "Decide after the backtest", "description": "Ask again later."},
            ],
        }
    ]
}

SALE_WINDOW_IN_DESCRIPTIONS_CARD = {
    "questions": [
        {
            "question": "Which Black Friday sale window do you want for the phone theme store?",
            "header": "Sale window",
            "multiSelect": False,
            "options": [
                {
                    "label": "Weekend only",
                    "description": "Fri Nov 27 to Mon Nov 30: a 4-day sale that feels more urgent.",
                },
                {
                    "label": "Full week",
                    "description": "Mon Nov 23 to Mon Nov 30: an 8-day sale that starts before Thanksgiving.",
                },
            ],
        }
    ]
}

DISCOUNT_DEPTH_CARD = {
    "questions": [
        {
            "question": "For Black Friday, how should themes that sell be priced?",
            "header": "Sellers",
            "multiSelect": False,
            "options": [
                {"label": "30% with a holdout (Recommended)", "description": "A fifth stays full."},
                {"label": "30% on all sellers", "description": "Every seller gets 30%."},
                {"label": "No discount for sellers", "description": "Sellers stay full."},
            ],
        },
        {
            "question": "How deep should themes that do not sell go for Black Friday?",
            "header": "Non-sellers",
            "multiSelect": False,
            "options": [
                {"label": "Split 50 and 70 (Recommended)", "description": "Half get 50%."},
                {"label": "70% on all", "description": "Every non-seller gets 70%."},
                {"label": "50% on all", "description": "Every non-seller gets 50%."},
            ],
        },
    ]
}

PULL_REQUEST_HOLD_CARD = {
    "questions": [
        {
            "question": "PR 5384 edits five files the new set flow must also change. How should I build around it?",
            "header": "PR 5384",
            "multiSelect": False,
            "options": [
                {
                    "label": "Stack on its branch (Recommended)",
                    "description": "One writer per file.",
                },
                {"label": "I approve it first", "description": "You approve PR 5384."},
                {"label": "Work around its files", "description": "My change stays out of them."},
            ],
        }
    ]
}

FIRST_LIVE_BATCH_CARD = {
    "questions": [
        {
            "question": "When the Black Friday plan file is ready, how should the first live run go?",
            "header": "First live",
            "multiSelect": False,
            "options": [
                {
                    "label": "Small watched batch (Recommended)",
                    "description": "I set about five themes per account while you watch.",
                },
                {"label": "Full run on approval", "description": "You approve the plan file."},
            ],
        }
    ]
}

APPROVE_RESEARCHED_VALUE_CARD = {
    "questions": [
        {
            "question": (
                "Last year's sales and this year's retail calendars set the Black Friday window"
                " to Nov 16 to Nov 30. Approve it?"
            ),
            "header": "BF window",
            "multiSelect": False,
            "options": [
                {"label": "Approve Nov 16 to Nov 30 (Recommended)", "description": "I build it."},
                {"label": "Hold the plan", "description": "Nothing is set yet."},
            ],
        }
    ]
}


def run_gate_on_card(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    question_input: dict[str, object],
) -> tuple[int, str]:
    transcript_entries = [
        {"type": "user", "message": {"role": "user", "content": "Plan the sale."}},
        {
            "type": "assistant",
            "message": {
                "id": "msg_a",
                "role": "assistant",
                "stop_reason": "tool_use",
                "content": [
                    {"type": "text", "text": "One call needs you."},
                    {
                        "type": "tool_use",
                        "id": QUESTION_ID,
                        "name": "AskUserQuestion",
                        "input": question_input,
                    },
                ],
            },
        },
    ]
    transcript_path = tmp_path / "transcript.jsonl"
    transcript_path.write_text(
        "\n".join(json.dumps(each_entry) for each_entry in transcript_entries) + "\n",
        encoding="utf-8",
    )
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "AskUserQuestion",
        "tool_use_id": QUESTION_ID,
        "transcript_path": str(transcript_path),
        "tool_input": question_input,
    }
    monkeypatch.setattr(
        question_brief_gate, "TRANSCRIPT_POLL_LIMIT_SECONDS", SHORT_POLL_LIMIT_SECONDS
    )
    monkeypatch.setattr(
        sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode()), encoding="utf-8")
    )
    exit_code = question_brief_gate.main()
    return exit_code, capsys.readouterr().err


@pytest.mark.parametrize(
    ("question_input", "all_expected_labels"),
    [
        (SALE_WINDOW_CARD, ["Fri Nov 27 to Mon Nov 30", "Mon Nov 23 to Mon Nov 30"]),
        (SALE_WINDOW_IN_DESCRIPTIONS_CARD, ["Weekend only", "Full week"]),
        (DISCOUNT_DEPTH_CARD, ["30% with a holdout (Recommended)", "30% on all sellers"]),
    ],
)
def test_should_refuse_a_card_that_asks_the_user_to_pick_a_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    question_input: dict[str, object],
    all_expected_labels: list[str],
) -> None:
    exit_code, reason = run_gate_on_card(tmp_path, monkeypatch, capsys, question_input)
    assert exit_code == 2
    for each_label in all_expected_labels:
        assert each_label in reason
    assert "research" in reason
    assert "hands or eyes" in reason


@pytest.mark.parametrize(
    "question_input",
    [PULL_REQUEST_HOLD_CARD, FIRST_LIVE_BATCH_CARD, APPROVE_RESEARCHED_VALUE_CARD],
)
def test_should_pass_a_card_that_asks_for_a_preference_an_approval_or_a_watched_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    question_input: dict[str, object],
) -> None:
    assert run_gate_on_card(tmp_path, monkeypatch, capsys, question_input) == (0, "")


@pytest.mark.parametrize(
    ("label", "is_expected_value"),
    [
        ("30% on all", True),
        ("40 percent off", True),
        ("$1.99 floor", True),
        ("Nov 27 to Nov 30", True),
        ("27 November only", True),
        ("Start 2026-11-16", True),
        ("11/16 to 11/30", True),
        ("A 7-day window", True),
        ("Two weeks", False),
        ("Stack on PR 5384", False),
        ("About 5 themes per account", False),
        ("Market 3 first", False),
        ("I'll approve it", False),
    ],
)
def test_should_tell_a_label_that_names_a_value_from_one_that_names_a_step(
    label: str, is_expected_value: bool
) -> None:
    assert question_brief_gate.label_holds_value(label) is is_expected_value


def test_should_not_count_a_duration_that_a_description_states_as_an_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    effect_duration_card = {
        "questions": [
            {
                "question": "Grading runs one judge call at a time. Should grades run in parallel?",
                "header": "Grading",
                "options": [
                    {"label": "Grade in parallel", "description": "About 5 hours total."},
                    {"label": "Keep it serial", "description": "About 19 hours total."},
                ],
            }
        ]
    }
    assert run_gate_on_card(tmp_path, monkeypatch, capsys, effect_duration_card) == (0, "")


def test_should_pass_a_card_with_one_value_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    one_value_card = {
        "questions": [
            {
                "question": "Research sets 30% for sellers. Go?",
                "header": "Sellers",
                "options": [
                    {"label": "Set 30%", "description": "I set it."},
                    {"label": "Hold", "description": "Nothing is set."},
                ],
            }
        ]
    }
    assert run_gate_on_card(tmp_path, monkeypatch, capsys, one_value_card) == (0, "")


@pytest.mark.parametrize(
    "question_input",
    [None, "text", {"questions": "x"}, {"questions": [{"options": "x"}]}, {"questions": [7]}],
)
def test_should_find_no_value_menu_in_a_malformed_input(question_input: object) -> None:
    assert question_brief_gate.value_menu_labels(question_input) == []
