from hooks_constants import reply_length_gate_constants as length_constants
from hooks_constants import resolve_thread_reply_gate_constants as constants

ALL_LENGTH_PHRASES_BY_CAP_STATE = {
    (True, True): (
        f" at most {length_constants.MAXIMUM_SENTENCE_COUNT} sentences of at most"
        f" {length_constants.MAXIMUM_WORDS_PER_SENTENCE} words each,"
    ),
    (True, False): f" at most {length_constants.MAXIMUM_SENTENCE_COUNT} sentences,",
    (False, True): f" at most {length_constants.MAXIMUM_WORDS_PER_SENTENCE} words per sentence,",
    (False, False): " the same meaning in fewer words,",
}


def test_should_name_the_length_phrase_for_the_cap_flags_in_force() -> None:
    cap_state = (
        length_constants.SENTENCE_CAP_ENABLED,
        length_constants.WORDS_PER_SENTENCE_CAP_ENABLED,
    )
    assert constants.RESOLVE_LENGTH_PHRASE == ALL_LENGTH_PHRASES_BY_CAP_STATE[cap_state]


def test_should_ask_for_a_shorter_reply_with_the_footer_in_the_missing_reply_reason() -> None:
    assert constants.RESOLVE_LENGTH_PHRASE in constants.MISSING_REPLY_REASON
    assert "footer included, and send it again." in constants.MISSING_REPLY_REASON
