import pytest

from closing_reply_shapes import OpenItemList, open_item_list, promised_report_phrase

BED_PROMPT = "okay, going to bed. just see either outcome through"
PROMISE_REPLY = (
    "Both fix runs are armed, and a wake is set for the end of CI."
    " A full write-up with the run's outcome will be here when you are back."
)
DEFERRED_PROMPT = "You did a lot of work. I want to know what you put off."
DEFERRED_LEAD = (
    "What I deferred or sidestepped, checked against the transcript and both pull request bodies:"
)
DEFERRED_REPLY = (
    f"{DEFERRED_LEAD}\n\n"
    "1. The retry budget for the sync job.\n"
    "2. The second fixture for the Windows path.\n"
    "3. The docs page for the new flag.\n"
    "4. The cleanup of the stale branch.\n"
    "5. The follow-up issue for the timeout."
)
THREE_BULLETS = "- The retry budget.\n- The docs page.\n- The stale branch."
CORRECTION_PROMPT = (
    "<!-- reply 1 -->\n"
    "> A full write-up with the run’s outcome will be here when you are back.\n\n"
    "don't need this; just need you to act accordingly and see the fixes through to completion"
)


@pytest.mark.parametrize(
    ("reply_text", "prompt_text", "expected_phrase"),
    [
        (PROMISE_REPLY, BED_PROMPT, "when you are back"),
        ("I'll report back once CI ends.", BED_PROMPT, "I'll report back once"),
        ("I’ll report back once CI ends.", BED_PROMPT, "I’ll report back once"),
        ("Then I'll report back.", BED_PROMPT, "I'll report back"),
        ("The summary will be posted at the end.", BED_PROMPT, "summary will be posted"),
        ("I'll post the link once CI ends.", BED_PROMPT, "I'll post the link once"),
        (
            PROMISE_REPLY,
            "<task-notification>summary: the run ended</task-notification>",
            "when you are back",
        ),
        (PROMISE_REPLY, CORRECTION_PROMPT, "when you are back"),
        (PROMISE_REPLY, "no report needed, just finish", "when you are back"),
        (PROMISE_REPLY, "Never mind the report, just fix it", "when you are back"),
        (PROMISE_REPLY, 'The bot posted "Report ready" again. Fix the hook.', "when you are back"),
        (
            PROMISE_REPLY,
            "<system-reminder>write a report</system-reminder> just finish",
            "when you are back",
        ),
        (PROMISE_REPLY, "  > report back please\nfix it", "when you are back"),
    ],
)
def test_should_flag_a_promised_later_report_no_prompt_asked_for(
    reply_text: str, prompt_text: str, expected_phrase: str
) -> None:
    assert promised_report_phrase(reply_text, prompt_text) == expected_phrase


@pytest.mark.parametrize(
    ("reply_text", "prompt_text"),
    [
        ("No report will follow.", BED_PROMPT),
        ("> I'll report back once CI ends.", BED_PROMPT),
        ("The draft says `I'll report back once CI ends` today.", BED_PROMPT),
        ("```\nI'll report back once CI ends.\n```", BED_PROMPT),
        ("I'll apply or skip each finding once they report back.", BED_PROMPT),
        ("Both checkers are running. I continue when they report.", BED_PROMPT),
        ("Both builds passed.", BED_PROMPT),
        (PROMISE_REPLY, "report back when the run ends"),
        (PROMISE_REPLY, "don't stop until it is merged, then give me a summary"),
        (PROMISE_REPLY, "do not merge yet; send me a summary when CI ends"),
        (PROMISE_REPLY, "without breaking main, fix it and report back"),
        (PROMISE_REPLY, "nothing else, report when done"),
        (PROMISE_REPLY, "no, report back once merged"),
        (PROMISE_REPLY, 'Fix it and give me a "summary" at the end'),
        (PROMISE_REPLY, "No rush. Report back when done."),
        (PROMISE_REPLY, "I don't want to babysit this. Let me know when it lands"),
    ],
)
def test_should_pass_a_reply_with_no_unasked_promise(reply_text: str, prompt_text: str) -> None:
    assert promised_report_phrase(reply_text, prompt_text) is None


@pytest.mark.parametrize(
    ("reply_text", "prompt_text", "expected_list"),
    [
        (DEFERRED_REPLY, DEFERRED_PROMPT, OpenItemList(DEFERRED_LEAD, 5)),
        (f"## Next steps\n\n{THREE_BULLETS}", DEFERRED_PROMPT, OpenItemList("## Next steps", 3)),
        (
            "Open items:\n\n| Item | State |\n|---|---|\n| Retry | open |\n| Docs | open |\n| Branch | open |",
            DEFERRED_PROMPT,
            OpenItemList("Open items:", 3),
        ),
        (f"Remaining:\n{THREE_BULLETS}", DEFERRED_PROMPT, OpenItemList("Remaining:", 3)),
        (
            "Still open:\n\n- The retry budget.\n\n  It needs a number.\n\n- The docs page.\n- The stale branch.",
            DEFERRED_PROMPT,
            OpenItemList("Still open:", 3),
        ),
        (DEFERRED_REPLY, "no list please, ask me instead", OpenItemList(DEFERRED_LEAD, 5)),
        (DEFERRED_REPLY, "what's on the to-do list?", OpenItemList(DEFERRED_LEAD, 5)),
        (DEFERRED_REPLY, "the bullet journal app needs a fix", OpenItemList(DEFERRED_LEAD, 5)),
        (
            DEFERRED_REPLY,
            "<system-reminder>list them</system-reminder> go on",
            OpenItemList(DEFERRED_LEAD, 5),
        ),
    ],
)
def test_should_flag_a_run_of_open_items_under_an_open_item_lead(
    reply_text: str, prompt_text: str, expected_list: OpenItemList
) -> None:
    assert open_item_list(reply_text, prompt_text) == expected_list


@pytest.mark.parametrize(
    ("reply_text", "prompt_text"),
    [
        (f"Changed files:\n\n{THREE_BULLETS}\n- The hook.\n- The test.", DEFERRED_PROMPT),
        ("Deferred:\n\n- The retry budget.\n- The docs page.", DEFERRED_PROMPT),
        (f"Nothing deferred.\n\n{THREE_BULLETS}", DEFERRED_PROMPT),
        (f"Skipped, with reasons\n\n{THREE_BULLETS}\n- The hook.", DEFERRED_PROMPT),
        (f"Deferred:\n\n```\n{THREE_BULLETS}\n```", DEFERRED_PROMPT),
        (f"Deferred:\n\n<details>\n{THREE_BULLETS}\n</details>", DEFERRED_PROMPT),
        (
            "Deferred:\n\n> - The retry budget.\n> - The docs page.\n> - The stale branch.",
            DEFERRED_PROMPT,
        ),
        (DEFERRED_REPLY, "list the deferred items as bullets"),
        (DEFERRED_REPLY, "don't use a table; list the items"),
        (DEFERRED_REPLY, "no questions, just list them"),
        (DEFERRED_REPLY, "Not a wall of text. A list of what is left is fine."),
    ],
)
def test_should_pass_a_reply_with_no_unasked_open_item_list(
    reply_text: str, prompt_text: str
) -> None:
    assert open_item_list(reply_text, prompt_text) is None
