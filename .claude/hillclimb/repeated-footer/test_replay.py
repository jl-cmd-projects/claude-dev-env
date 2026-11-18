import json

from replay import ReplayOutcome, first_reply, footer_text, held_reply, outcome_rows, replay, with_footer
from repeated_footer_eval_support.config.constants import HOOKS_DIRECTORY, SCENARIO_FILE

ALL_FOOTER_ITEMS = ["I am shipping pull request 8590 once its automated tests pass."]
TURN_FIELDS = {
    "body": "Nothing is new.",
    "tracker_body": "The task list now shows the hold.",
    "read_body": "I read all nine.",
}


def test_should_write_the_footer_under_the_minimal_policy_only_when_it_changed() -> None:
    footer_reply = first_reply(TURN_FIELDS, ALL_FOOTER_ITEMS, None, "minimal")
    assert footer_reply == with_footer("Nothing is new.", ALL_FOOTER_ITEMS)
    last_footer = footer_reply.split("\n\n", 1)[1]
    assert first_reply(TURN_FIELDS, ALL_FOOTER_ITEMS, last_footer, "minimal") == "Nothing is new."
    assert first_reply(TURN_FIELDS, ALL_FOOTER_ITEMS, last_footer, "logged") == footer_reply


def test_should_answer_each_hold_the_way_the_session_did() -> None:
    tracker_hold = "This turn worked on the user's ask and left the task list unchanged."
    footer_hold = "This session did work while work is still in progress and ended without the In progress footer."
    assert held_reply([tracker_hold], TURN_FIELDS, "Done.", ALL_FOOTER_ITEMS) == (
        ["TaskUpdate"],
        "The task list now shows the hold.",
    )
    assert held_reply([footer_hold], TURN_FIELDS, "Done.", ALL_FOOTER_ITEMS) == (
        [],
        with_footer("Done.", ALL_FOOTER_ITEMS),
    )


def test_should_send_the_footer_once_per_change_through_this_checkout_gates() -> None:
    all_scenario_fields = json.loads(SCENARIO_FILE.read_text(encoding="utf-8"))
    outcome = replay(HOOKS_DIRECTORY, all_scenario_fields, "minimal")
    all_footer_replies = [each_reply for each_reply in outcome.all_replies if "In progress:" in each_reply]
    assert len(all_footer_replies) == 2
    assert [each_lead for _, each_lead in outcome.all_holds if "In progress" in each_lead] == []


def test_should_print_the_summary_then_each_hold_of_a_replay() -> None:
    outcome = ReplayOutcome([footer_text(ALL_FOOTER_ITEMS), "Done."], [(1, "This turn worked on the user's ask")])
    assert outcome_rows("main", "minimal", outcome) == [
        "main [minimal]: replies 2, holds 1, footer copies 1, repeated lines 0",
        "  turn 1 hold: This turn worked on the user's ask",
    ]
