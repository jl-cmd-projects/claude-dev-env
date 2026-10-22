from pathlib import Path

import pytest

from open_task_asks import claude_home, is_ask


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
        ('<agent-message from="afbaf992127c7512f">\nReport delivered.\n</agent-message>', False),
        ('<cross-session-message from="s-2">\nBuild the PR\n</cross-session-message>', False),
        ("<system-reminder>\nTool loaded.\n</system-reminder>", False),
        ("<system-reminder>\nTool loaded.\n</system-reminder>\n<system-reminder>\nMore.\n</system-reminder>", False),
        ("<system-reminder>\nTool loaded.\n</system-reminder>\nExport the APKs", True),
    ],
)
def test_should_classify_work_prompts_as_asks(prompt_text: str, is_expected_ask: bool) -> None:
    assert is_ask(prompt_text) is is_expected_ask


def test_should_read_the_claude_home_from_claude_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "profile"))
    assert claude_home() == tmp_path / "profile"


def test_should_default_the_claude_home_to_the_user_home(tmp_path: Path) -> None:
    assert claude_home() == tmp_path / ".claude"
