"""Replay a session that spammed the In progress footer through the Stop gates and count the repeats.

::

    python3 replay.py
    python3 replay.py --hooks <main checkout>/packages/claude-dev-env/hooks --label main

``scenario.json`` holds nine pull requests in progress, the footer the agent
would write at each point, and seven turns shaped like the session that sent
the same nine-line footer again and again: a typed prompt with work, a "still
waiting" notice, a notice that leads to reads and a message, and four more
"still waiting" notices.

Each reply goes through ``open_tasks_stop_gate.py`` and
``closing_question_round_gate.py`` the way Claude Code runs them, with the
nine tasks in the task store. A stand-in ``claude`` on PATH plays the reply
judge and flags any line ending in a colon above three list items as an
open-item list, which the session's judge did with its footer. The agent
answers each hold the way the session did::

    task list hold        -> a TaskUpdate call, then a one-sentence reply
    open-item list hold   -> a read call, then a one-sentence reply
    footer hold           -> the reply again, with the footer under it

Two agent policies write each turn's first reply::

    minimal   the footer only when it differs from the last footer sent
    logged    the footer on every turn, as the session did

The run prints the replies, holds, footer copies, and repeated lines per
policy, as ``repeated_lines.repeat_report`` counts them, then each hold.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from repeated_footer_eval_support.config.constants import (
    ALL_FOOTER_HOLD_TEXTS,
    ALL_POLICIES,
    FOOTER_HEADING_LINE,
    FOOTER_LIST_MARKER,
    HOLD_LEAD_LENGTH,
    HOLD_ROW_TEMPLATE,
    HOOKS_DIRECTORY,
    HUMAN_TURN_ORIGIN,
    LINE_BREAK,
    LIST_HOLD_TEXT,
    LOGGED_POLICY,
    MAXIMUM_HOLDS_PER_STOP,
    NOTIFICATION_TEMPLATE,
    NOTIFICATION_TURN_KIND,
    NOTIFICATION_TURN_ORIGIN,
    READ_TOOL_NAME,
    REPLY_PARAGRAPH_SEPARATOR,
    REPORT_TEMPLATE,
    SCENARIO_FILE,
    SCENARIO_FOOTERS_KEY,
    SCENARIO_TASKS_KEY,
    SCENARIO_TURNS_KEY,
    STOP_FEEDBACK_TEMPLATE,
    TASK_UPDATE_TOOL_NAME,
    TRACKER_HOLD_TEXT,
    TURN_BODY_KEY,
    TURN_FOOTER_KEY,
    TURN_KIND_KEY,
    TURN_READ_BODY_KEY,
    TURN_TEXT_KEY,
    TURN_TOOLS_KEY,
    TURN_TRACKER_BODY_KEY,
    UTF8_ENCODING,
)
from repeated_footer_eval_support.replay_session import ReplaySession
from repeated_lines import repeat_report

logger = logging.getLogger(__name__)


class ReplayOutcome(NamedTuple):
    """What one replay sent and which holds it met.

    Attributes:
        all_replies: Each reply the agent sent, in order.
        all_holds: The turn number and the start of the first line of each hold reason.
    """

    all_replies: list[str]
    all_holds: list[tuple[int, str]]


def footer_text(all_footer_lines: list[str]) -> str:
    """Return the In progress footer, one list line per piece of work.

    Args:
        all_footer_lines: The footer's lines, without list markers.

    Returns:
        The heading, then each line as a list line.
    """
    return LINE_BREAK.join([FOOTER_HEADING_LINE, *(FOOTER_LIST_MARKER + each_line for each_line in all_footer_lines)])


def with_footer(body: str, all_footer_lines: list[str]) -> str:
    """Return the body with the footer under it.

    Args:
        body: The reply above the footer.
        all_footer_lines: The footer's lines, without list markers.

    Returns:
        The reply.
    """
    return body + REPLY_PARAGRAPH_SEPARATOR + footer_text(all_footer_lines)


def first_reply(
    all_turn_fields: dict[str, object], all_footer_lines: list[str], last_footer: str | None, policy: str
) -> str:
    """Return the turn's first reply under the policy.

    ::

        logged                              -> body and footer
        minimal, footer as last sent        -> body only
        minimal, footer changed or unsent   -> body and footer

    Args:
        all_turn_fields: The scenario turn.
        all_footer_lines: The footer the agent would write now.
        last_footer: The last footer sent, or None.
        policy: ``minimal`` or ``logged``.

    Returns:
        The reply.
    """
    body = str(all_turn_fields[TURN_BODY_KEY])
    if policy == LOGGED_POLICY or footer_text(all_footer_lines) != last_footer:
        return with_footer(body, all_footer_lines)
    return body


def held_reply(
    all_reasons: list[str], all_turn_fields: dict[str, object], last_reply: str, all_footer_lines: list[str]
) -> tuple[list[str], str]:
    """Return the tool calls and the reply the agent sends after a hold.

    ::

        task list hold        -> [TaskUpdate], the tracker sentence
        open-item list hold   -> [Bash], the read sentence
        footer hold           -> [], the last reply's body with the footer under it

    Args:
        all_reasons: The reason of each gate that held.
        all_turn_fields: The scenario turn.
        last_reply: The reply the gates held.
        all_footer_lines: The footer the agent would write now.

    Returns:
        The tool names to call, then the reply.
    """
    joined_reasons = LINE_BREAK.join(all_reasons)
    all_tool_names: list[str] = []
    reply_body = last_reply.split(REPLY_PARAGRAPH_SEPARATOR + FOOTER_HEADING_LINE)[0]
    if TRACKER_HOLD_TEXT in joined_reasons:
        all_tool_names.append(TASK_UPDATE_TOOL_NAME)
        reply_body = str(all_turn_fields[TURN_TRACKER_BODY_KEY])
    if LIST_HOLD_TEXT in joined_reasons:
        all_tool_names.append(READ_TOOL_NAME)
        reply_body = str(all_turn_fields[TURN_READ_BODY_KEY])
    if any(each_text in joined_reasons for each_text in ALL_FOOTER_HOLD_TEXTS):
        return all_tool_names, with_footer(reply_body, all_footer_lines)
    return all_tool_names, reply_body


def _start_turn(session: ReplaySession, all_turn_fields: dict[str, object]) -> None:
    turn_text = str(all_turn_fields[TURN_TEXT_KEY])
    if all_turn_fields[TURN_KIND_KEY] == NOTIFICATION_TURN_KIND:
        session.add_user_text(NOTIFICATION_TEMPLATE.format(summary=turn_text), NOTIFICATION_TURN_ORIGIN)
    else:
        session.add_user_text(turn_text, HUMAN_TURN_ORIGIN)
    session.add_tool_calls(list(all_turn_fields[TURN_TOOLS_KEY]))


def _held_turn_replies(
    session: ReplaySession, hooks_directory: Path, all_turn_fields: dict[str, object], all_footer_lines: list[str], reply_text: str
) -> tuple[list[str], list[str]]:
    all_replies: list[str] = []
    all_hold_leads: list[str] = []
    is_held_stop = False
    for _ in range(MAXIMUM_HOLDS_PER_STOP + 1):
        session.add_reply(reply_text)
        all_replies.append(reply_text)
        all_reasons = session.stop_reasons(hooks_directory, reply_text, is_held_stop)
        if not all_reasons:
            break
        all_hold_leads.extend(each_reason.split(LINE_BREAK)[0][:HOLD_LEAD_LENGTH] for each_reason in all_reasons)
        for each_reason in all_reasons:
            session.add_user_text(STOP_FEEDBACK_TEMPLATE.format(reasons=each_reason), None)
        all_tool_names, reply_text = held_reply(all_reasons, all_turn_fields, reply_text, all_footer_lines)
        session.add_tool_calls(all_tool_names)
        is_held_stop = True
    return all_replies, all_hold_leads


def replay(hooks_directory: Path, all_scenario_fields: dict[str, object], policy: str) -> ReplayOutcome:
    """Replay every turn of the scenario through the Stop gates under one policy.

    Args:
        hooks_directory: The ``hooks`` folder whose gates run.
        all_scenario_fields: The parsed scenario file.
        policy: ``minimal`` or ``logged``.

    Returns:
        The replies sent and the holds met.
    """
    all_footers = all_scenario_fields[SCENARIO_FOOTERS_KEY]
    all_replies: list[str] = []
    all_holds: list[tuple[int, str]] = []
    last_footer: str | None = None
    with tempfile.TemporaryDirectory() as session_directory_name:
        session = ReplaySession(Path(session_directory_name), all_scenario_fields[SCENARIO_TASKS_KEY])
        for each_turn_number, each_turn in enumerate(all_scenario_fields[SCENARIO_TURNS_KEY], start=1):
            all_footer_lines = all_footers[each_turn[TURN_FOOTER_KEY]]
            _start_turn(session, each_turn)
            reply_text = first_reply(each_turn, all_footer_lines, last_footer, policy)
            all_turn_replies, all_hold_leads = _held_turn_replies(
                session, hooks_directory, each_turn, all_footer_lines, reply_text
            )
            all_replies.extend(all_turn_replies)
            all_holds.extend((each_turn_number, each_lead) for each_lead in all_hold_leads)
            if any(FOOTER_HEADING_LINE in each_reply for each_reply in all_turn_replies):
                last_footer = footer_text(all_footer_lines)
    return ReplayOutcome(all_replies, all_holds)


def outcome_rows(label: str, policy: str, outcome: ReplayOutcome) -> list[str]:
    """Return the summary row for one replay, then one row per hold.

    Args:
        label: The name of the hooks under test.
        policy: The agent policy the replay used.
        outcome: What the replay sent and met.

    Returns:
        The rows, summary first.
    """
    report = repeat_report(outcome.all_replies)
    return [
        REPORT_TEMPLATE.format(
            label=label,
            policy=policy,
            reply_count=report.reply_count,
            hold_count=len(outcome.all_holds),
            footer_count=report.footer_count,
            repeated_line_count=report.repeated_line_count,
        ),
        *(
            HOLD_ROW_TEMPLATE.format(turn_number=each_turn_number, lead=each_lead)
            for each_turn_number, each_lead in outcome.all_holds
        ),
    ]


def main() -> int:
    """Replay the scenario under each policy and print the counts.

    Returns:
        Process exit status, always zero.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hooks", type=Path, default=HOOKS_DIRECTORY, help="The hooks folder whose gates run.")
    parser.add_argument("--label", default="this checkout", help="The name printed on each summary row.")
    parser.add_argument("--policy", choices=ALL_POLICIES, action="append", help="Run only this policy.")
    arguments = parser.parse_args()
    all_scenario_fields = json.loads(SCENARIO_FILE.read_text(encoding=UTF8_ENCODING))
    for each_policy in arguments.policy or list(ALL_POLICIES):
        each_outcome = replay(arguments.hooks, all_scenario_fields, each_policy)
        for each_row in outcome_rows(arguments.label, each_policy, each_outcome):
            logger.info("%s", each_row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
