from hooks_constants import visual_reply_rules_constants as constants


def test_rules_file_path_points_at_the_shipped_rule_list() -> None:
    assert constants.RULES_FILE_PATH.is_file()


def test_capitalized_abbreviation_pattern_needs_two_capitals() -> None:
    assert constants.CAPITALIZED_ABBREVIATION_PATTERN.findall("CI and PRs, not Item or I") == ["CI", "PRs"]


def test_tracker_number_pattern_reads_items_issues_and_cards() -> None:
    assert [
        each.group(0) for each in constants.TRACKER_NUMBER_PATTERN.finditer("issue 5735, item #6, card 2")
    ] == ["issue 5735", "item #6", "card 2"]
