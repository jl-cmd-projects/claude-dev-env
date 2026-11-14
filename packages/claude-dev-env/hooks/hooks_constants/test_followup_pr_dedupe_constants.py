import re

from hooks_constants import followup_pr_dedupe_constants as constants


def test_parent_pattern_reads_both_spellings_and_stops_at_the_number() -> None:
    assert re.search(constants.FOLLOWUP_PARENT_PATTERN, "followup to #12", re.IGNORECASE)
    assert re.search(constants.FOLLOWUP_PARENT_PATTERN, "Follow-up to #1731", re.IGNORECASE).group(1) == "1731"


def test_python_program_pattern_should_read_versioned_and_launcher_names_only() -> None:
    for each_name in ("python", "python3", "python3.11", "python3.13", "pythonw", "py", "pyw"):
        assert re.fullmatch(constants.PYTHON_PROGRAM_NAME_PATTERN, each_name)
    for each_name in ("pytest", "pyright", "python-config", "ipython"):
        assert re.fullmatch(constants.PYTHON_PROGRAM_NAME_PATTERN, each_name) is None
