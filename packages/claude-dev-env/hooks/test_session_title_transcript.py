import json
from pathlib import Path

import pytest

from session_title_transcript import (
    available_title_tools,
    read_transcript_entries,
    shown_title,
    title_status,
)

REMOTE_TITLE_TOOL = "mcp__claude-code-remote__set_session_title"
DESKTOP_TITLE_TOOL = "mcp__ccd_session_mgmt__set_session_title"
SNAPSHOT_LISTING = {
    "type": "attachment",
    "attachment": {
        "type": "prompt_snapshot",
        "tools": [{"name": "Bash"}, {"name": REMOTE_TITLE_TOOL}],
    },
}
DEFERRED_LISTING = {
    "type": "attachment",
    "attachment": {"type": "deferred_tools_delta", "addedNames": [DESKTOP_TITLE_TOOL]},
}
REMOVAL_LISTING = {
    "type": "attachment",
    "attachment": {"type": "deferred_tools_delta", "removedNames": [DESKTOP_TITLE_TOOL]},
}
RED_FLAG_TITLE = "\U0001f6a9 Merge approval"
HOURGLASS_TITLE = "⏳ Export"


def title_call(tool_use_id: str, title: str, is_sidechain: bool = False) -> dict[str, object]:
    return {
        "type": "assistant",
        "isSidechain": is_sidechain,
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": REMOTE_TITLE_TOOL,
                    "input": {"title": title},
                }
            ]
        },
    }


def title_result(
    tool_use_id: str, is_error: bool = False, is_sidechain: bool = False
) -> dict[str, object]:
    return {
        "type": "user",
        "isSidechain": is_sidechain,
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": "ok",
                    "is_error": is_error,
                }
            ]
        },
    }


def test_should_find_the_title_tool_in_a_listing_a_deferred_delta_or_a_call() -> None:
    assert available_title_tools([SNAPSHOT_LISTING]) == [REMOTE_TITLE_TOOL]
    assert available_title_tools([DEFERRED_LISTING]) == [DESKTOP_TITLE_TOOL]
    assert available_title_tools([title_call("t1", HOURGLASS_TITLE)]) == [REMOTE_TITLE_TOOL]
    assert available_title_tools([{"type": "user"}]) == []


def test_should_drop_a_title_tool_a_later_delta_removes() -> None:
    assert available_title_tools([DEFERRED_LISTING, REMOVAL_LISTING]) == []


def test_should_return_the_last_main_chain_title_that_came_back_without_an_error() -> None:
    all_entries = [
        title_call("t1", HOURGLASS_TITLE),
        title_result("t1"),
        title_call("t2", RED_FLAG_TITLE),
        title_result("t2", is_error=True),
        title_call("t3", "✅ Subagent", is_sidechain=True),
        title_result("t3", is_sidechain=True),
    ]
    assert shown_title(all_entries) == HOURGLASS_TITLE
    assert shown_title([SNAPSHOT_LISTING]) is None


@pytest.mark.parametrize(
    ("title", "expected_status"),
    [(RED_FLAG_TITLE, "\U0001f6a9"), ("⏳️ Export", "⏳"), ("Export", None)],
)
def test_should_read_the_status_emoji_without_its_variation_selector(
    title: str, expected_status: str | None
) -> None:
    assert title_status(title) == expected_status


def test_should_read_object_lines_and_skip_the_rest(tmp_path: Path) -> None:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(
        json.dumps(SNAPSHOT_LISTING) + "\nnot json\n[1, 2]\n", encoding="utf-8"
    )
    assert read_transcript_entries(str(transcript_path)) == [SNAPSHOT_LISTING]
    assert read_transcript_entries(str(tmp_path / "missing.jsonl")) == []
    assert read_transcript_entries(None) == []
