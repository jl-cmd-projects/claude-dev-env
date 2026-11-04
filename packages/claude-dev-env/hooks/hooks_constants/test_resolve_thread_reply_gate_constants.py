import os
import subprocess
import sys
from pathlib import Path

import pytest

from hooks_constants import reply_length_gate_constants as length_constants
from hooks_constants import resolve_thread_reply_gate_constants as constants

HOOKS_DIRECTORY = Path(__file__).resolve().parents[1]
REPLY_LENGTH_ENVIRONMENT_PREFIX = "REPLY_LENGTH_"
PHRASE_PROBE = (
    "from hooks_constants import resolve_thread_reply_gate_constants as c; "
    "print(c.RESOLVE_LENGTH_PHRASE)"
)
ALL_SENTENCE_LIMIT_FRAGMENTS = f"{length_constants.MAXIMUM_SENTENCE_COUNT} sentences"
ALL_WORD_LIMIT_FRAGMENTS = f"{length_constants.MAXIMUM_WORDS_PER_SENTENCE} words"


def read_phrase_in_a_fresh_process(environment_overrides: dict[str, str]) -> str:
    environment = {
        each_name: each_value
        for each_name, each_value in os.environ.items()
        if not each_name.startswith(REPLY_LENGTH_ENVIRONMENT_PREFIX)
    }
    environment.update(environment_overrides)
    completed_run = subprocess.run(
        [sys.executable, "-c", PHRASE_PROBE],
        cwd=HOOKS_DIRECTORY,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed_run.stdout.strip()


@pytest.mark.parametrize(
    ("switch_overrides", "all_expected_fragments"),
    [
        (
            {"REPLY_LENGTH_SENTENCE_CAP": "on", "REPLY_LENGTH_WORD_CAP": "on"},
            [ALL_SENTENCE_LIMIT_FRAGMENTS, ALL_WORD_LIMIT_FRAGMENTS],
        ),
        ({"REPLY_LENGTH_SENTENCE_CAP": "on"}, [ALL_SENTENCE_LIMIT_FRAGMENTS]),
        ({"REPLY_LENGTH_WORD_CAP": "on"}, [ALL_WORD_LIMIT_FRAGMENTS]),
        ({}, ["same meaning in fewer words"]),
    ],
)
def test_should_name_each_limit_in_force_in_the_phrase(
    switch_overrides: dict[str, str], all_expected_fragments: list[str]
) -> None:
    phrase = read_phrase_in_a_fresh_process(switch_overrides)
    assert all(each_fragment in phrase for each_fragment in all_expected_fragments)


def test_should_ask_for_a_shorter_reply_with_the_footer_in_the_missing_reply_reason() -> None:
    assert constants.RESOLVE_LENGTH_PHRASE in constants.MISSING_REPLY_REASON
    assert "footer included, and send it again." in constants.MISSING_REPLY_REASON
