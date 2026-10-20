from pathlib import Path

import pytest

from spawn_brief_text import spawn_brief_text


@pytest.mark.parametrize(
    ("tool_name", "tool_input", "expected_brief"),
    [
        ("Agent", {"prompt": "Do X."}, "Do X."),
        ("mcp__hearthbot__start_remote_control", {"instructions": "Do Y."}, "Do Y."),
        ("multi_agent_v1__spawn_agent", {"message": "Do Z."}, "Do Z."),
        ("Agent", {"description": "No prompt"}, ""),
        (
            "mcp__github__actions_run_trigger",
            {"method": "run_workflow", "inputs": {"prompt": "Do W."}},
            "Do W.",
        ),
        ("mcp__github__actions_run_trigger", {"method": "cancel_workflow_run"}, None),
        ("Bash", {"command": "ls"}, None),
        ("Workflow", {"name": "saved-review"}, ""),
    ],
)
def test_should_return_the_brief_each_spawn_tool_carries(
    tool_name: str, tool_input: dict[str, object], expected_brief: str | None
) -> None:
    assert spawn_brief_text(tool_name, tool_input) == expected_brief


def test_should_read_a_workflow_script_file(tmp_path: Path) -> None:
    script_path = tmp_path / "workflow.js"
    script_path.write_text("agent('Outcome: done.')", encoding="utf-8")
    assert spawn_brief_text("Workflow", {"scriptPath": str(script_path)}) == (
        "agent('Outcome: done.')"
    )
