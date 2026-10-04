from hooks_constants import reply_length_gate_constants as constants


def test_gate_limits_replies_to_three_sentences_of_fifteen_words() -> None:
    assert (constants.MAXIMUM_SENTENCE_COUNT, constants.MAXIMUM_WORDS_PER_SENTENCE) == (3, 15)


def test_gate_checks_the_two_chat_tools_that_post_to_the_user() -> None:
    assert constants.ALL_CHECKED_TOOL_NAMES == frozenset(
        {"mcp__hearthbot__reply", "mcp__hearthbot__post_message"}
    )


def test_gate_exit_codes_match_the_hook_contract() -> None:
    assert (constants.ALLOW_EXIT_CODE, constants.BLOCK_EXIT_CODE) == (0, 2)


def test_default_banned_words_hold_the_hedges_and_intensifiers() -> None:
    assert {"likely", "probably", "seems", "real", "actually", "genuine"} <= set(
        constants.ALL_DEFAULT_BANNED_WORDS
    )
