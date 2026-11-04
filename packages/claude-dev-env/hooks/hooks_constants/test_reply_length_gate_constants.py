import os
import subprocess
import sys
from pathlib import Path

from hooks_constants import reply_length_gate_constants as constants

HOOKS_DIRECTORY = Path(__file__).resolve().parents[1]
REPLY_LENGTH_ENVIRONMENT_PREFIX = "REPLY_LENGTH_"
CAP_PROBE = (
    "from hooks_constants import reply_length_gate_constants as c; "
    "from hooks_constants import chat_reply_gate_constants as chat; "
    "print(c.SENTENCE_CAP_ENABLED, c.WORDS_PER_SENTENCE_CAP_ENABLED); "
    "print(chat.REPLY_LIMIT_REMINDER)"
)
BOTH_CAPS_ON = {"REPLY_LENGTH_SENTENCE_CAP": "on", "REPLY_LENGTH_WORD_CAP": "on"}


def read_probe_lines_in_a_fresh_process(environment_overrides: dict[str, str]) -> list[str]:
    environment = {
        each_name: each_value
        for each_name, each_value in os.environ.items()
        if not each_name.startswith(REPLY_LENGTH_ENVIRONMENT_PREFIX)
    }
    environment.update(environment_overrides)
    completed_run = subprocess.run(
        [sys.executable, "-c", CAP_PROBE],
        cwd=HOOKS_DIRECTORY,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed_run.stdout.splitlines()


def test_should_keep_both_length_caps_off_when_the_environment_is_silent() -> None:
    flags_line, _ = read_probe_lines_in_a_fresh_process({})
    assert flags_line == "False False"


def test_should_turn_both_length_caps_on_from_the_environment() -> None:
    flags_line, _ = read_probe_lines_in_a_fresh_process(BOTH_CAPS_ON)
    assert flags_line == "True True"


def test_should_put_both_length_limits_in_the_reply_reminder_when_switched_on() -> None:
    _, reminder = read_probe_lines_in_a_fresh_process(BOTH_CAPS_ON)
    assert f"Keep it to {constants.MAXIMUM_SENTENCE_COUNT} sentences or fewer." in reminder
    assert f"Keep each sentence to {constants.MAXIMUM_WORDS_PER_SENTENCE} words or fewer." in reminder


def test_should_leave_the_length_limits_out_of_the_reply_reminder_when_switched_off() -> None:
    _, reminder = read_probe_lines_in_a_fresh_process({})
    assert "sentences or fewer" not in reminder
    assert "words or fewer" not in reminder


def test_gate_limits_replies_to_fifty_sentences_of_thirty_five_words() -> None:
    assert (constants.MAXIMUM_SENTENCE_COUNT, constants.MAXIMUM_WORDS_PER_SENTENCE) == (50, 35)


def test_gate_checks_the_three_chat_tools_that_post_to_the_user() -> None:
    assert constants.ALL_CHECKED_TOOL_NAMES == frozenset(
        {"mcp__hearthbot__reply", "mcp__hearthbot__post_message", "mcp__hearthbot__update_message"}
    )


def test_gate_exit_codes_match_the_hook_contract() -> None:
    assert (constants.ALLOW_EXIT_CODE, constants.BLOCK_EXIT_CODE) == (0, 2)


def test_default_banned_words_hold_the_hedges_and_intensifiers() -> None:
    assert {"likely", "probably", "seems", "real", "actually", "genuine"} <= set(
        constants.ALL_DEFAULT_BANNED_WORDS
    )


def test_gate_checks_the_project_decision_card_tool() -> None:
    assert constants.DECISION_CARD_TOOL_NAME == "mcp__hearthbot__ask_decision"


def test_default_banned_words_hold_the_added_hedge_phrases() -> None:
    assert {
        "maybe",
        "perhaps",
        "presumably",
        "might be",
        "may be",
        "appears to",
        "i believe",
        "not sure",
        "unsure",
    } <= set(constants.ALL_DEFAULT_BANNED_WORDS)


def test_gate_reads_only_the_prose_fields_of_a_decision_card() -> None:
    assert (
        constants.ALL_DECISION_CARD_PROSE_KEYS,
        constants.DECISION_CARD_OPTIONS_KEY,
        constants.ALL_DECISION_OPTION_PROSE_KEYS,
    ) == (("question", "context"), "options", ("label", "consequence"))


def test_colon_pattern_matches_a_colon_with_prose_after_it_on_the_line() -> None:
    assert constants.MID_SENTENCE_COLON_PATTERN.search("matters: one message")
    assert constants.MID_SENTENCE_COLON_PATTERN.search("at 9:47") is None
    assert constants.MID_SENTENCE_COLON_PATTERN.search("items:\n- one") is None


def test_gate_caps_card_context_at_two_sentences_and_checks_card_length_fields() -> None:
    assert (
        constants.MAXIMUM_CARD_CONTEXT_SENTENCE_COUNT,
        constants.ALL_DECISION_CARD_LENGTH_KEYS,
        constants.ALL_DECISION_OPTION_LENGTH_KEYS,
    ) == (2, ("question", "context", "reason"), ("consequence",))
