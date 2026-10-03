from hooks_constants import transcript_skill_scan_constants as constants


def test_transcript_entry_names() -> None:
    assert constants.COMPACT_BOUNDARY_SUBTYPE == "compact_boundary"
    assert constants.SKILL_TOOL_NAME == "Skill"
    assert constants.TOOL_USE_BLOCK_TYPE == "tool_use"
