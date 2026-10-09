from hooks_constants import issue_close_handoff_gate_constants as constants


def test_gate_checks_every_issue_comment_and_write_tool() -> None:
    assert constants.ALL_ISSUE_TOOL_SUFFIXES == (
        "add_issue_comment",
        "issue_write",
        "update_issue_comment",
    )


def test_gate_exit_codes_match_the_hook_contract() -> None:
    assert (constants.ALLOW_EXIT_CODE, constants.BLOCK_EXIT_CODE) == (0, 2)


def test_close_declaration_skips_a_reopen_heading() -> None:
    assert constants.CLOSE_DECLARATION_PATTERN.search("## Reopened: the reading") is None
