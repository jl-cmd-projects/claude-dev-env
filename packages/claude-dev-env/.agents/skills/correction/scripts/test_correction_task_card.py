"""Behavior tests for correction_task_card against the shipped fix playbook."""

from __future__ import annotations

import importlib
import io
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

correction_task_card = importlib.import_module("correction_task_card")

FIX_PLAYBOOK_TEXT = (SCRIPTS_DIRECTORY.parent / "playbooks" / "fix.md").read_text(
    encoding="utf-8"
)


def _card_input(**overrides: object) -> dict[str, object]:
    card_input: dict[str, object] = {
        "title": "Add a lint for bare except blocks in hooks",
        "tldr": "Agents keep writing bare except blocks in hook files.",
        "brief": "Correction: stop writing bare except\nEvidence: hooks/example.py:12",
        "files": ["packages/claude-dev-env/hooks/blocking/example.py"],
    }
    card_input.update(overrides)
    return card_input


def _run_main(
    card_input: object, all_arguments: list[str], monkeypatch: pytest.MonkeyPatch
) -> int:
    piped_bytes = json.dumps(card_input).encode("utf-8")
    monkeypatch.setattr(
        sys, "stdin", io.TextIOWrapper(io.BytesIO(piped_bytes), encoding="utf-8")
    )
    return correction_task_card.main(all_arguments)


def test_should_print_the_three_spawn_task_fields(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_main(_card_input(), [], monkeypatch) == 0
    task_card = json.loads(capsys.readouterr().out)
    assert list(task_card) == ["title", "tldr", "prompt"]
    assert task_card["title"] == "Add a lint for bare except blocks in hooks"
    assert task_card["tldr"] == "Agents keep writing bare except blocks in hook files."


def test_should_carry_the_brief_files_and_playbook_steps_in_the_prompt() -> None:
    prompt = correction_task_card.build_task_card(_card_input(), FIX_PLAYBOOK_TEXT)[
        "prompt"
    ]
    assert (
        "Correction: stop writing bare except\nEvidence: hooks/example.py:12" in prompt
    )
    assert "- `packages/claude-dev-env/hooks/blocking/example.py`" in prompt
    assert "Start at step 2." in prompt
    for each_step_number in range(2, 9):
        assert f"\n{each_step_number}. " in prompt
    assert "**Reply:**" in prompt


def test_should_leave_out_step_one_and_relative_links() -> None:
    prompt = correction_task_card.build_task_card(_card_input(), FIX_PLAYBOOK_TEXT)[
        "prompt"
    ]
    assert "\n1. Write the brief" not in prompt
    assert "](../" not in prompt
    assert "`correction-lens.md`" in prompt


def test_should_print_only_the_prompt_for_the_handoff_brief(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_main(_card_input(), ["--prompt-only"], monkeypatch) == 0
    printed = capsys.readouterr().out
    assert (
        printed
        == correction_task_card.build_task_card(_card_input(), FIX_PLAYBOOK_TEXT)[
            "prompt"
        ]
    )


def test_should_name_no_files_when_the_session_names_none() -> None:
    prompt = correction_task_card.build_task_card(
        _card_input(files=[]), FIX_PLAYBOOK_TEXT
    )["prompt"]
    assert "- None named in the session. Step 4 finds them." in prompt


@pytest.mark.parametrize(
    ("overrides", "reason_fragment"),
    [
        ({"title": "x" * 60}, "title has 60 characters; the limit is 59"),
        ({"title": "  "}, "title is empty"),
        ({"title": "Add a lint\nfor hooks"}, "title must be one line"),
        ({"tldr": "first line\nsecond line"}, "tldr must be one line"),
        ({"brief": ""}, "brief is empty"),
        ({"files": "hooks/example.py"}, "files must be a list of strings"),
        ({"files": ["/home/me/repo/hooks/example.py"]}, "is absolute"),
        ({"files": ["C:\\repo\\hooks\\example.py"]}, "is absolute"),
        ({"files": ["~/repo/hooks/example.py"]}, "is absolute"),
    ],
)
def test_should_refuse_a_card_that_breaks_a_field_rule(
    overrides: dict[str, object],
    reason_fragment: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run_main(_card_input(**overrides), [], monkeypatch) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert reason_fragment in captured.err


def test_should_accept_a_title_at_the_length_limit() -> None:
    task_card = correction_task_card.build_task_card(
        _card_input(title="A" * 59), FIX_PLAYBOOK_TEXT
    )
    assert len(task_card["title"]) == 59


def test_should_refuse_input_that_is_not_one_json_object(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_main(["a", "list"], [], monkeypatch) == 1
    assert "standard input must hold one JSON object" in capsys.readouterr().err


def test_should_return_the_playbook_from_step_two() -> None:
    handed_off_steps = correction_task_card.handed_off_playbook_steps(FIX_PLAYBOOK_TEXT)
    assert handed_off_steps.startswith("2. ")
    assert "pull request link" in handed_off_steps
