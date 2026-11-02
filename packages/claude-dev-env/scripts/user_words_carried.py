"""Check that a worker prompt carries the user's own words, word for word.

A prompt that paraphrases the request starts the worker from the paraphrase.
The check passes when the user's words, after HTML unescaping and whitespace
collapse, appear in the prompt text.

::

    prompt "Please list three colors." with words "list three colors."  -> True
    prompt "Name three colors." with words "List three colors."         -> False
"""

from __future__ import annotations

import html

from dev_env_scripts_constants.user_words_carried_constants import TEXT_JOIN_SEPARATOR


def _normalized(text: str) -> str:
    return TEXT_JOIN_SEPARATOR.join(html.unescape(text).split())


def prompt_carries_user_words(prompt_text: str, user_words: str) -> bool:
    """Return True when the user's words appear word for word in the prompt.

    An empty set of user words never passes, so a caller cannot skip the check
    by sending no words.

    ::

        "Please list three colors." carries "list three colors."  -> True
        "Name three colors." carries "List three colors."          -> False
        "Name three colors." carries ""                           -> False

    Args:
        prompt_text: The full prompt text the worker receives.
        user_words: The user's message, copied from the session.

    Returns:
        True when the normalized user words are a substring of the prompt.
    """
    normalized_words = _normalized(user_words)
    return bool(normalized_words) and normalized_words in _normalized(prompt_text)
