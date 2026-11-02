import user_words_carried


def test_prompt_carries_user_words_should_pass_words_copied_into_a_longer_prompt() -> (
    None
):
    assert user_words_carried.prompt_carries_user_words(
        "Please list three colors.\nOutcome: three colors are named.",
        "Please list three colors.",
    )


def test_prompt_carries_user_words_should_refuse_a_paraphrase() -> None:
    assert not user_words_carried.prompt_carries_user_words(
        "Name three colors.", "Please list three colors."
    )


def test_prompt_carries_user_words_should_match_html_escaped_words() -> None:
    assert user_words_carried.prompt_carries_user_words(
        "Send me X's output.", "Send me X&#39;s output."
    )


def test_prompt_carries_user_words_should_refuse_empty_words() -> None:
    assert not user_words_carried.prompt_carries_user_words("Name three colors.", "   ")
