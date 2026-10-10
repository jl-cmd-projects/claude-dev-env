import re

from context_audit_constants.config import constants
from context_audit_constants.config.constants import CapKey, RowKind, Trigger


def test_every_cap_key_has_a_line_cap() -> None:
    assert set(constants.ALL_LINE_CAP_BY_KEY) == set(CapKey)
    assert constants.ALL_LINE_CAP_BY_KEY[CapKey.ROOT_INSTRUCTIONS] == 20
    assert constants.ALL_LINE_CAP_BY_KEY[CapKey.SKILL_BODY] == 200


def test_trigger_values_match_the_report_labels() -> None:
    assert [each_trigger.value for each_trigger in Trigger] == [
        "session-start",
        "folder-enter",
        "path-match",
        "skill-invoke",
        "on-link",
        "file-open",
    ]


def test_stub_kinds_cover_instruction_files_only() -> None:
    assert constants.ALL_STUB_KINDS == {
        RowKind.INSTRUCTIONS,
        RowKind.IMPORT,
        RowKind.RULE,
    }


def test_link_pattern_drops_the_anchor_from_a_target() -> None:
    assert re.findall(constants.LINK_PATTERN, "[a](guide.md#setup) [b](x y)") == [
        "guide.md"
    ]
