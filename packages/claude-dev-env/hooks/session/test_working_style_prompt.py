"""Tests for working_style_prompt — SessionStart hook that injects working-style text."""

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import working_style_prompt as starter

from hooks_constants.working_style_prompt_constants import (
    WORKING_STYLE_GUIDE_RELATIVE_PATH,
    WORKING_STYLE_PROMPT,
)

WORKING_STYLE_GUIDE_PATH = _HOOKS_ROOT.parent / WORKING_STYLE_GUIDE_RELATIVE_PATH


def _run_main() -> str:
    """Return stdout produced by running the hook's main()."""
    captured_stdout = StringIO()
    with patch("sys.stdout", captured_stdout):
        starter.main()
    return captured_stdout.getvalue()


class TestWorkingStylePrompt:
    def test_main_emits_additional_context(self) -> None:
        emitted = json.loads(_run_main())
        hook_output = emitted["hookSpecificOutput"]
        assert hook_output["hookEventName"] == "SessionStart"
        assert "additionalContext" in hook_output

    def test_additional_context_matches_prompt_exactly(self) -> None:
        emitted = json.loads(_run_main())
        assert emitted["hookSpecificOutput"]["additionalContext"] == WORKING_STYLE_PROMPT

    def test_prompt_points_at_the_working_style_guide(self) -> None:
        assert f"~/.claude/{WORKING_STYLE_GUIDE_RELATIVE_PATH}" in WORKING_STYLE_PROMPT
        assert WORKING_STYLE_GUIDE_PATH.is_file()

    def test_prompt_stays_a_short_pointer(self) -> None:
        assert len(WORKING_STYLE_PROMPT) < len(WORKING_STYLE_GUIDE_PATH.read_text(encoding="utf-8")) // 10

    def test_guide_carries_the_policy_and_scope_guidance(self) -> None:
        guide_text = WORKING_STYLE_GUIDE_PATH.read_text(encoding="utf-8")
        assert "Document each task in a location that remains easy to find later." in guide_text
        assert "Deliver the requested work at its intended scope." in guide_text
        assert "A request to remove something is complete once it is gone." in guide_text
        assert "Send the user only what they must act on or need to know." in guide_text
        assert "starts a turn and nothing in it needs the user, end the turn with no text." in guide_text
        assert "On a typed request, state your next action in one sentence" in guide_text
        assert "Pause for the user's choice before making a high-impact decision." in guide_text

    def test_build_session_directive_returns_the_shared_constant(self) -> None:
        assert starter.build_session_directive() == WORKING_STYLE_PROMPT
