"""Behavior tests for reading the user's approval of one oversized pull request."""

import json
import sys
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import oversized_change_approval as approval


@pytest.mark.parametrize(
    "message_text",
    [
        "I approve this as one pull request",
        "keep it as one PR, that's approved",
        "don't split it",
        "Do not split this pull request.",
        "the size is fine for this pull request",
        "approved over the size bar",
        "Thanks. Don’t split it, it stays one PR.",
    ],
)
def test_should_count_a_message_that_approves_one_large_pull_request(message_text: str) -> None:
    assert approval.is_size_approval(message_text) is True


@pytest.mark.parametrize(
    "message_text",
    [
        "split that, it is way too big for one PR",
        "for the size gate, refuse, but allow it if the user has explicitly approved it.",
        "the size is fine if the tests pass",
        "Don't split it unless it's over 2,000 lines.",
        "Don't split hairs, just tell me the size.",
        "Do not split the commit, but split the PR.",
        "I never said don't split it.",
        "stop, don't split anything yet, I'm reading the diff",
        "approval of the size depends on the reviewer",
        "The font size is fine.",
        "ok, approved the size of the logo",
        "Line count is fine on the README",
        "approved",
        "is this one pull request?",
        "not approved over the size bar",
        "don't keep it as one PR",
        "ok, split it, it is too big for one pull request",
        'Add a test for "don\'t split it".',
        "I revoke my approval to keep it as one PR.",
        'Add a test with this prompt: "Thanks. Keep it as one PR. Then run the tests."',
        "Add a test with this prompt: “Thanks. Keep it as one PR. Then run the tests.”",
        "I withdraw the approval of this as one pull request.",
    ],
)
def test_should_not_count_a_message_that_does_not_approve_the_size(message_text: str) -> None:
    assert approval.is_size_approval(message_text) is False


def _transcript(tmp_path: Path, *all_records: dict[str, object]) -> str:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(
        "".join(json.dumps(each_record) + "\n" for each_record in all_records), encoding="utf-8"
    )
    return str(transcript_path)


def _user_record(content: object, **all_flags: object) -> dict[str, object]:
    return {"type": "user", "message": {"role": "user", "content": content}, **all_flags}


APPROVAL_TEXT = "keep it as one PR, that's approved"


def test_should_find_an_approval_the_user_typed(tmp_path: Path) -> None:
    path = _transcript(tmp_path, _user_record("start"), _user_record(APPROVAL_TEXT))
    assert approval.has_user_approved_oversized_pull_request(path) is True


def test_should_find_an_approval_in_a_text_block_beside_a_reminder(tmp_path: Path) -> None:
    content = [
        {"type": "text", "text": APPROVAL_TEXT},
        {"type": "text", "text": "<system-reminder>notes</system-reminder>"},
    ]
    assert approval.has_user_approved_oversized_pull_request(
        _transcript(tmp_path, _user_record(content))
    )


@pytest.mark.parametrize(
    "record",
    [
        {"type": "assistant", "message": {"role": "assistant", "content": APPROVAL_TEXT}},
        _user_record(
            [{"type": "tool_result", "content": [{"type": "text", "text": APPROVAL_TEXT}]}]
        ),
        _user_record(APPROVAL_TEXT, isMeta=True),
        _user_record(APPROVAL_TEXT, isSidechain=True),
        _user_record("<system-reminder>" + APPROVAL_TEXT + "</system-reminder>"),
    ],
)
def test_should_skip_the_same_words_outside_a_typed_user_message(
    tmp_path: Path, record: dict[str, object]
) -> None:
    assert approval.has_user_approved_oversized_pull_request(_transcript(tmp_path, record)) is False


def test_should_let_a_later_split_request_withdraw_an_approval(tmp_path: Path) -> None:
    path = _transcript(tmp_path, _user_record(APPROVAL_TEXT), _user_record("Split it after all."))
    assert approval.has_user_approved_oversized_pull_request(path) is False


def test_should_let_a_later_revocation_withdraw_an_approval(tmp_path: Path) -> None:
    path = _transcript(
        tmp_path,
        _user_record(APPROVAL_TEXT),
        _user_record("I revoke my approval to keep it as one PR."),
    )
    assert approval.has_user_approved_oversized_pull_request(path) is False


def test_should_read_the_text_blocks_of_one_message_together(tmp_path: Path) -> None:
    content = [
        {"type": "text", "text": APPROVAL_TEXT},
        {"type": "text", "text": "Split it after all."},
    ]
    path = _transcript(tmp_path, _user_record(content))
    assert approval.has_user_approved_oversized_pull_request(path) is False


def test_should_let_a_later_approval_replace_a_split_request(tmp_path: Path) -> None:
    path = _transcript(tmp_path, _user_record("Split that."), _user_record(APPROVAL_TEXT))
    assert approval.has_user_approved_oversized_pull_request(path) is True


@pytest.mark.parametrize(
    ("message_text", "expected_verdict"),
    [
        (APPROVAL_TEXT, True),
        ("Split it after all.", False),
        ("Approved as one PR. On second thought, split it.", False),
        ("Thanks, but split it into two PRs.", False),
        ("I revoke my approval to keep it as one PR.", False),
        ("Cancel that, split it.", False),
        ("I revoke my approval, it is not okay as one PR.", False),
        ("Cancel the meeting.", None),
        ("If the size changes, split it into two PRs.", None),
        ('Add a case for "Hi. Split it. Thanks."', None),
        ("Don't split hairs.", None),
        ("Run the tests.", None),
    ],
)
def test_should_give_one_size_verdict_per_message(
    message_text: str, expected_verdict: bool | None
) -> None:
    assert approval.size_verdict(message_text) is expected_verdict


def test_should_skip_an_approval_a_peer_agent_sent(tmp_path: Path) -> None:
    record = _user_record(APPROVAL_TEXT, origin={"kind": "peer", "from": "agent-1"})
    assert approval.has_user_approved_oversized_pull_request(_transcript(tmp_path, record)) is False


def test_should_find_an_approval_with_a_human_origin(tmp_path: Path) -> None:
    record = _user_record(APPROVAL_TEXT, origin={"kind": "human"})
    assert approval.has_user_approved_oversized_pull_request(_transcript(tmp_path, record)) is True


def _queued_record(prompt: str, **all_attachment_fields: object) -> dict[str, object]:
    return {
        "type": "attachment",
        "attachment": {"type": "queued_command", "prompt": prompt, **all_attachment_fields},
    }


def test_should_find_an_approval_the_user_queued_during_a_turn(tmp_path: Path) -> None:
    record = _queued_record(APPROVAL_TEXT, origin={"kind": "human"})
    assert approval.has_user_approved_oversized_pull_request(_transcript(tmp_path, record)) is True


def test_should_find_an_approval_cited_in_a_queued_relay(tmp_path: Path) -> None:
    record = _queued_record(
        _relay_text(APPROVAL_TEXT, "Build it."), origin={"kind": "task-notification"}, isMeta=True
    )
    assert approval.has_user_approved_oversized_pull_request(_transcript(tmp_path, record)) is True


@pytest.mark.parametrize(
    "all_attachment_fields",
    [
        {},
        {"origin": {"kind": "peer"}},
        {"origin": {"kind": "human"}, "isMeta": True},
        {"origin": {"kind": "task-notification"}},
    ],
)
def test_should_skip_a_queued_approval_the_user_did_not_type(
    tmp_path: Path, all_attachment_fields: dict[str, object]
) -> None:
    record = _queued_record(APPROVAL_TEXT, **all_attachment_fields)
    assert approval.has_user_approved_oversized_pull_request(_transcript(tmp_path, record)) is False


def test_should_skip_a_cited_block_a_peer_agent_quoted(tmp_path: Path) -> None:
    record = _user_record(_relay_text(APPROVAL_TEXT, "Report."), origin={"kind": "peer"})
    assert approval.has_user_approved_oversized_pull_request(_transcript(tmp_path, record)) is False


def _relay_text(cited_text: str, note_text: str) -> str:
    return (
        '<relay from="coordinator" session="s" reason="spawn">\n'
        '  <cited id="cmsg_1" author="user" name="Jon" where="timeline">\n'
        f"      {cited_text}\n"
        "  </cited>\n"
        f"  <note>{note_text}</note>\n"
        "</relay>"
    )


def test_should_find_an_approval_inside_a_cited_user_block_of_a_relay(tmp_path: Path) -> None:
    record = _user_record(_relay_text(APPROVAL_TEXT, "Build it."), isMeta=True)
    assert approval.has_user_approved_oversized_pull_request(_transcript(tmp_path, record)) is True


def test_should_skip_an_approval_in_the_agent_note_of_a_relay(tmp_path: Path) -> None:
    record = _user_record(_relay_text("Please build the gate.", APPROVAL_TEXT), isMeta=True)
    assert approval.has_user_approved_oversized_pull_request(_transcript(tmp_path, record)) is False


def test_should_find_no_approval_when_the_transcript_cannot_be_read(tmp_path: Path) -> None:
    assert (
        approval.has_user_approved_oversized_pull_request(str(tmp_path / "missing.jsonl")) is False
    )
    assert approval.has_user_approved_oversized_pull_request(None) is False
