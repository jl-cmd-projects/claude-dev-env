from hooks_constants import pr_lifecycle_skill_gate_constants as constants


def test_gate_targets_the_named_skill_and_pre_tool_use() -> None:
    assert constants.SKILL_NAME == "pr-lifecycle"
    assert constants.HOOK_EVENT_NAME == "PreToolUse"
    assert constants.DENY_DECISION == "deny"


def test_gate_covers_shells_and_pull_request_tools() -> None:
    assert constants.SHELL_TOOL_NAMES == {"Bash", "PowerShell"}
    assert len(constants.ALL_GITHUB_MCP_TOOL_SUFFIXES) == 4


def test_skill_loaded_marker_should_name_the_skill_in_a_tag() -> None:
    assert constants.SKILL_LOADED_MARKER == '<skill-loaded name="pr-lifecycle">'
    assert constants.SKILL_LOADED_CLOSING_TAG == "</skill-loaded>"
