from hooks_constants import verify_before_acting_constants as constants


def test_mutating_tool_and_mcp_names_are_classified() -> None:
    assert {"Write", "Edit"} <= constants.ALL_ALWAYS_MUTATING_TOOL_NAMES
    assert {"Bash", "PowerShell"} == constants.ALL_SHELL_TOOL_NAMES
    assert constants.MCP_ACTION_WORD_SPLIT_PATTERN.split("create_pull_request") == [
        "create",
        "pull",
        "request",
    ]
    assert "create" in constants.ALL_MCP_MUTATING_VERBS


def test_hedge_pattern_matches_a_hedged_claim_only() -> None:
    assert constants.HEDGE_PATTERN.search("Perhaps the command writes a file.")
    assert constants.HEDGE_PATTERN.search("I might be mistaken.")
    assert constants.HEDGE_PATTERN.search("I checked the command output.") is None
