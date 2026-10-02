from hooks_constants import verify_before_acting_constants as constants


def test_mutating_tool_names_cover_edit_and_agent_tools() -> None:
    assert constants.ALL_ALWAYS_MUTATING_TOOL_NAMES == frozenset(
        {"Write", "Edit", "MultiEdit", "NotebookEdit", "Agent", "Task", "apply_patch"}
    )
    assert constants.ALL_SHELL_TOOL_NAMES == frozenset({"Bash", "PowerShell"})


def test_hedge_pattern_matches_uncertainty_without_matching_checked_work() -> None:
    assert constants.HEDGE_PATTERN.search("I MIGHT BE mistaken") is not None
    assert constants.HEDGE_PATTERN.search("I checked the output") is None
