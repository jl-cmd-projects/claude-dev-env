import json
import subprocess
import sys
from pathlib import Path

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import artifact_template_pointer
from hooks_constants.artifact_template_pointer_constants import ARTIFACT_TEMPLATE_PATH

HOOK_SCRIPT = Path(__file__).resolve().parent / "artifact_template_pointer.py"


def _payload(tool_name: str, tool_input: object) -> dict[str, object]:
    return {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}


def _run_hook(payload: dict[str, object]) -> str:
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def test_artifact_quickstart_gets_the_template_pointer() -> None:
    hook_output = json.loads(_run_hook(_payload("Artifact", {"action": "quickstart", "intent": "other"})))
    specific_output = hook_output["hookSpecificOutput"]
    assert specific_output["hookEventName"] == "PreToolUse"
    assert str(ARTIFACT_TEMPLATE_PATH) in specific_output["additionalContext"]
    assert "permissionDecision" not in specific_output


def test_artifact_design_skill_gets_the_template_pointer() -> None:
    hook_output = artifact_template_pointer.decide_hook_output(
        _payload("Skill", {"skill": "artifact-design"})
    )
    assert hook_output is not None
    assert str(ARTIFACT_TEMPLATE_PATH) in hook_output["hookSpecificOutput"]["additionalContext"]


def test_artifact_publish_stays_quiet() -> None:
    assert _run_hook(_payload("Artifact", {"action": "publish", "file_path": "page.html"})) == ""


def test_other_skill_stays_quiet() -> None:
    assert artifact_template_pointer.decide_hook_output(_payload("Skill", {"skill": "pr-lifecycle"})) is None


def test_tool_input_that_is_not_an_object_stays_quiet() -> None:
    assert artifact_template_pointer.decide_hook_output(_payload("Artifact", "quickstart")) is None


def test_empty_stdin_stays_quiet() -> None:
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)], input="", capture_output=True, text=True, check=True
    )
    assert completed.stdout == ""


def test_the_pointer_names_a_template_that_exists() -> None:
    assert ARTIFACT_TEMPLATE_PATH.is_file()
