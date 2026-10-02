"""Pin the PR done reminder's command shape and checklist wording."""

from __future__ import annotations

from hooks_constants import pr_done_reminder_constants as constants


def test_gh_probe_asks_for_every_field_the_checklist_reads() -> None:
    assert constants.ALL_GH_PR_VIEW_ARGUMENTS[:3] == ("gh", "pr", "view")
    all_requested_fields = constants.ALL_GH_PR_VIEW_ARGUMENTS[-1].split(",")
    for each_field in ("number", "url", "isDraft", "mergeable", "statusCheckRollup", "labels"):
        assert each_field in all_requested_fields


def test_checklist_lines_join_on_a_single_newline() -> None:
    assert constants.REMINDER_LINE_SEPARATOR == "\n"


def test_every_mergeable_value_has_a_hint() -> None:
    assert set(constants.ALL_REMINDER_HINTS_BY_MERGEABLE) == {
        constants.MERGEABLE_CLEAN_VALUE,
        constants.MERGEABLE_CONFLICTING_VALUE,
        constants.MERGEABLE_UNKNOWN_VALUE,
    }


def test_header_says_it_never_blocks() -> None:
    assert "never a block" in constants.REMINDER_HEADER
    assert "never a block" in constants.NO_PULL_REQUEST_REMINDER
