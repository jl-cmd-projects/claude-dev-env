import pytest

from closing_reply_shapes import OpenItemList, open_item_list, promised_report_phrase, prompt_asks_for_list

BED_PROMPT = "heading out now. handle whatever the nightly job returns"
PROMISE_REPLY = (
    "Both fix runs are armed, and a wake is set for the end of CI."
    " The benchmark table will be posted when you get back."
)
DEFERRED_PROMPT = "You did a lot of work. I want to know what you put off."
DEFERRED_LEAD = (
    "What I deferred, checked against the build log:"
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
    "> The benchmark table will be posted when you get back.\n\n"
    "skip that; just apply the result and finish the fixes"
)


@pytest.mark.parametrize(
    ("reply_text", "prompt_text", "expected_phrase"),
    [
        (PROMISE_REPLY, BED_PROMPT, "when you get back"),
        ("I'll report back once CI ends.", BED_PROMPT, "I'll report back once"),
        ("I’ll report back once CI ends.", BED_PROMPT, "I’ll report back once"),
        ("Then I'll report back.", BED_PROMPT, "I'll report back"),
        ("The summary will be posted at the end.", BED_PROMPT, "summary will be posted"),
        ("I'll post the link once CI ends.", BED_PROMPT, "I'll post the link once"),
        (
            PROMISE_REPLY,
            "<task-notification>summary: the run ended</task-notification>",
            "when you get back",
        ),
        (PROMISE_REPLY, CORRECTION_PROMPT, "when you get back"),
        (PROMISE_REPLY, "no report needed, just finish", "when you get back"),
        (PROMISE_REPLY, "Never mind the report, just fix it", "when you get back"),
        (PROMISE_REPLY, 'The bot posted "Report ready" again. Fix the hook.', "when you get back"),
        (
            PROMISE_REPLY,
            "<system-reminder>write a report</system-reminder> just finish",
            "when you get back",
        ),
        (PROMISE_REPLY, "  > report back please\nfix it", "when you get back"),
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
        ("I'll merge each lint fix once the bots report back.", BED_PROMPT),
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


@pytest.mark.parametrize(
    "lead",
    [
        "I fixed the three follow-ups you flagged:",
        "All pending checks passed:",
        "I closed the remaining review threads:",
        "I removed the `deferred` flag from:",
        'The test named "pending jobs" now covers:',
        "The test named “pending jobs” now covers:",
        "I resolved all outstanding comments:",
        "Every remaining test now passes:",
        "Merged the pending pull requests:",
        "Completed to-dos:",
        "Closed follow-ups:",
    ],
)
def test_should_pass_a_list_of_finished_work_whose_lead_names_follow_ups(lead: str) -> None:
    assert open_item_list(f"{lead}\n{THREE_BULLETS}", DEFERRED_PROMPT) is None


@pytest.mark.parametrize(
    "lead",
    [
        DEFERRED_LEAD,
        "Open items:",
        "Still open:",
        "Not done yet:",
        "Deferred:",
        "Next steps:",
        "Follow-ups:",
        "What I fixed and what I deferred:",
        "Remaining work after the merged fixes:",
        "Follow-ups I did not get to:",
        "Pending your decision:",
        "Things I sidestepped:",
        "Unresolved after this round:",
        "Follow-ups not yet merged:",
        "Follow-ups that aren't fixed:",
        "Remaining tasks, not done:",
    ],
)
def test_should_flag_a_list_whose_lead_names_open_work(lead: str) -> None:
    assert open_item_list(f"{lead}\n{THREE_BULLETS}", DEFERRED_PROMPT) == OpenItemList(lead, 3)


def test_should_flag_a_promise_to_report_once_a_running_agent_finishes() -> None:
    reply_text = "The lint job is still running, and I'll report once it finishes."
    prompt_text = "<task-notification>the reuse agent finished</task-notification>"
    assert promised_report_phrase(reply_text, prompt_text) == "I'll report once"


@pytest.mark.parametrize(
    "lead",
    ["Remaining tasks, now done:", "Open items, all fixed:", "Follow-ups, already merged:", "Pending checks, passed:"],
)
def test_should_pass_a_lead_that_ends_in_a_completion_word(lead: str) -> None:
    assert open_item_list(f"{lead}\n{THREE_BULLETS}", DEFERRED_PROMPT) is None


@pytest.mark.parametrize(
    "prompt_text",
    [
        "Fix the report page.",
        "The summary card is cut off on mobile, fix it",
        "Fix the report page, then deploy it",
        "rename the recap table",
    ],
)
def test_should_hold_a_promise_when_the_prompt_names_a_report_as_a_noun(prompt_text: str) -> None:
    assert promised_report_phrase(PROMISE_REPLY, prompt_text) == "when you get back"


@pytest.mark.parametrize(
    ("prompt_text", "is_list_ask"),
    [
        ("list the deferred items as bullets", True),
        ("put the open calls in a table", True),
        ("don't list them, just fix them", False),
        ("Fix the build", False),
    ],
)
def test_should_report_whether_the_prompt_asks_for_a_list(prompt_text: str, is_list_ask: bool) -> None:
    assert prompt_asks_for_list(prompt_text) is is_list_ask
