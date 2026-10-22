from pathlib import Path

import pytest

from open_task_asks import is_ask, record_prompt, recorded_prompts


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


@pytest.mark.parametrize(
    ("prompt_text", "is_expected_ask"),
    [
        ("Export the OneUI8 and OneUI9 APKs and submit them", True),
        ("can you check the release dates in neon?", True),
        (
            "set the 8 to ready to export in neon\n\ni dont think you're correct in none are released?",
            True,
        ),
        ("wait, did /deepstack-mode fail?", False),
        ("are you monitoring these? yes or no", False),
        ("<task-notification>\n<task-id>b1</task-id>", False),
        ("   ", False),
        ("thanks!", False),
        ("ok, thanks", False),
        ("Looks good", False),
        ("ok, ship it", True),
        ("yes", True),
    ],
)
def test_should_classify_work_prompts_as_asks(prompt_text: str, is_expected_ask: bool) -> None:
    assert is_ask(prompt_text) is is_expected_ask


def test_should_number_asks_and_keep_every_prompt_in_order() -> None:
    assert record_prompt("s-1", "Export the APKs") == "ask-1"
    assert record_prompt("s-1", "did it fail?") is None
    assert record_prompt("s-1", "Submit them") == "ask-2"
    assert [each_prompt.ask_id for each_prompt in recorded_prompts("s-1")] == [
        "ask-1",
        None,
        "ask-2",
    ]


def test_should_skip_a_session_id_that_is_not_a_plain_name() -> None:
    assert record_prompt("../escape", "Export the APKs") is None
    assert recorded_prompts("../escape") == []
