from hooks_constants import pr_lifecycle_skill_gate_constants as constants


def test_gate_targets_the_named_skill_and_pre_tool_use() -> None:
    assert constants.SKILL_NAME == "pr-lifecycle"
    assert constants.HOOK_EVENT_NAME == "PreToolUse"
    assert constants.DENY_DECISION == "deny"


def test_gate_covers_shells_and_pull_request_tools() -> None:
    assert constants.SHELL_TOOL_NAMES == {"Bash", "PowerShell"}
    assert len(constants.ALL_GITHUB_MCP_TOOL_SUFFIXES) == 4


def test_scan_sentence_should_join_a_deny_reason_and_name_only_the_skill_repair() -> None:
    assert constants.SCAN_RAN_OUT_SENTENCE.startswith(" ")
    assert "loading the skill again" in constants.SCAN_RAN_OUT_SENTENCE
    assert "build-eval" not in constants.SCAN_RAN_OUT_SENTENCE


def test_gate_name_should_read_as_a_noun_phrase_in_the_fault_reason() -> None:
    assert constants.GATE_NAME == "pull request lifecycle"
