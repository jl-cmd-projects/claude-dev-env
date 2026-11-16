"""Check the eval cases: unique ids, known labels, the row shape, and none of the private originals."""

import json
from pathlib import Path

CASES_PATH = Path(__file__).resolve().parent / "cases.json"
ALL_LABELS = {"pass", "hold-promise", "hold-list", "hold-both"}
ALL_ROW_KEYS = {
    "id",
    "set",
    "label",
    "prompt",
    "reply",
    "question_tool",
    "incident1_row",
}
ALL_PRIVATE_ORIGINALS = (
    " ".join(
        (
            "What I deferred or sidestepped,",
            "checked against the transcript",
            "and both pull request bodies:",
        )
    ),
    " ".join(("okay, going to bed.", "just see either", "outcome through")),
    " ".join(
        (
            "don't need this; just need you",
            "to act accordingly and see",
            "the fixes through to completion",
        )
    ),
    " ".join(("A full write-up will be here", "when you are back.")),
    " ".join(
        (
            "I want to know what you did",
            "that was deferred work,",
            "and what you sidestepped.",
        )
    ),
    " ".join(
        ("The altitude agent is still running,", "and I'll report once it finishes.")
    ),
    "__".join(("mcp", "claude-code-remote", "send_later")),
    " ".join(("[command hook 6]: There are uncommitted", "changes in the repository.")),
    " ".join(("I'll apply or skip each finding", "once they report back.")),
)


def _cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def test_should_give_every_case_a_unique_id() -> None:
    all_ids = [each_case["id"] for each_case in _cases()]
    assert len(all_ids) == len(set(all_ids))


def test_should_label_every_case_with_a_known_label() -> None:
    assert {each_case["label"] for each_case in _cases()} <= ALL_LABELS


def test_should_give_every_case_the_row_shape() -> None:
    for each_case in _cases():
        assert set(each_case) == ALL_ROW_KEYS, each_case["id"]
        assert isinstance(each_case["prompt"], str) and isinstance(
            each_case["reply"], str
        )
        assert isinstance(each_case["question_tool"], bool)
        assert isinstance(each_case["incident1_row"], bool)
        assert each_case["id"].startswith(each_case["set"] + "/")


def test_should_hold_none_of_the_private_originals() -> None:
    for each_case in _cases():
        case_text = each_case["prompt"] + "\n" + each_case["reply"]
        for each_original in ALL_PRIVATE_ORIGINALS:
            assert each_original not in case_text, (each_case["id"], each_original[:20])


def test_should_carry_both_incident_twins() -> None:
    all_labels_by_id = {each_case["id"]: each_case["label"] for each_case in _cases()}
    assert all_labels_by_id["twins/INC1"] == "hold-promise"
    assert all_labels_by_id["twins/INC2"] == "hold-list"
