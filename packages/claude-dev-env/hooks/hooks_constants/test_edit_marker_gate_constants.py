from hooks_constants import edit_marker_gate_constants as constants


def test_gate_checks_every_message_edit_tool() -> None:
    assert constants.MESSAGE_EDIT_TOOL_SUFFIX == "update_message"


def test_gate_exit_codes_match_the_hook_contract() -> None:
    assert (constants.ALLOW_EXIT_CODE, constants.BLOCK_EXIT_CODE) == (0, 2)
