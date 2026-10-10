import json
import re

from hooks_constants import visual_reply_rules_constants as constants


def test_rules_file_path_points_at_the_shipped_rule_list() -> None:
    assert constants.RULES_FILE_PATH.is_file()


def test_capitalized_abbreviation_pattern_needs_two_capitals() -> None:
    assert constants.CAPITALIZED_ABBREVIATION_PATTERN.findall("CI and PRs, not Item or I") == ["CI", "PRs"]


def test_tracker_number_pattern_reads_items_issues_and_cards() -> None:
    assert [
        each.group(0) for each in constants.TRACKER_NUMBER_PATTERN.finditer("issue 5735, item #6, card 2")
    ] == ["issue 5735", "item #6", "card 2"]


def test_rule_key_constants_name_rules_in_the_shipped_rule_list() -> None:
    rules_document = json.loads(constants.RULES_FILE_PATH.read_text(encoding=constants.RULES_FILE_ENCODING))
    all_shipped_keys = {each_rule[constants.RULE_KEY_FIELD] for each_rule in rules_document[constants.RULES_LIST_KEY]}

    assert {
        constants.NO_PICTURE_RULE_KEY,
        constants.ABBREVIATIONS_RULE_KEY,
        constants.ONE_ITEM_RULE_KEY,
    } <= all_shipped_keys
    assert constants.ALLOWED_CAPITALIZED_WORDS_KEY in rules_document
    assert constants.LOWERCASE_ABBREVIATIONS_KEY in rules_document


def test_lowercase_abbreviation_template_matches_the_word_on_its_own_only() -> None:
    pattern = re.compile(constants.LOWERCASE_ABBREVIATION_TEMPLATE.format(abbreviation=re.escape("repo")))

    assert pattern.findall("the repo, my repos, a repo2 tag") == ["repo"]


def test_widget_anchor_pattern_matches_a_link_and_skips_other_tags() -> None:
    assert constants.WIDGET_ANCHOR_PATTERN.search('<A class="x" HREF="https://example.com">')
    assert constants.WIDGET_ANCHOR_PATTERN.search('<abbr title="a">') is None
    assert constants.WIDGET_ANCHOR_PATTERN.search("<a>no link</a>") is None
