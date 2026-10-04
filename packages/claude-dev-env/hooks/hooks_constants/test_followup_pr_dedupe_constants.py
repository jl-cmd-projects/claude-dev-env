import re

from hooks_constants import followup_pr_dedupe_constants as constants


def test_parent_pattern_reads_both_spellings_and_stops_at_the_number() -> None:
    assert re.search(constants.FOLLOWUP_PARENT_PATTERN, "followup to #12", re.IGNORECASE)
    assert re.search(constants.FOLLOWUP_PARENT_PATTERN, "Follow-up to #1731", re.IGNORECASE).group(1) == "1731"


def test_read_timeout_fits_inside_the_hook_timeout() -> None:
    assert constants.READ_TIMEOUT_SECONDS * 2 < 10
