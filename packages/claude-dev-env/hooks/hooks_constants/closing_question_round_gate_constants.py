"""Constants for the closing question round Stop gate.

Groups: the payload and transcript fields that mark a stop the gate leaves
alone, the transcript text each cheap scan looks for, the time and size
budget, the wording that marks an open item, the masking of indented code,
the declaration line, the hold cap, and the two hold reasons.
"""

from __future__ import annotations

import re

from hooks_constants.open_tasks_stop_gate_constants import (
    ALL_QUESTION_TOOL_NAMES,
    TOOL_RESULT_BLOCK_TYPE,
)

SUBAGENT_ID_KEY = "agent_id"
BACKGROUND_TASKS_KEY = "background_tasks"
SESSION_ATTENDED_ENVIRONMENT_VARIABLE = "CLAUDE_CODE_SESSION_ATTENDED"
HEADLESS_SESSION_ATTENDED_TEXT = "0"
TURN_ORIGIN_KEY = "turnOrigin"
HUMAN_TURN_ORIGIN = "human"
IS_SIDECHAIN_KEY = "isSidechain"
ATTENDED_SESSION_TEXT = "1"
LAST_ASSISTANT_MESSAGE_KEY = "last_assistant_message"
TOOL_USE_BLOCK_ID_KEY = "id"
IS_ERROR_KEY = "is_error"

TURN_ORIGIN_SCAN_TEXT = f'"{TURN_ORIGIN_KEY}"'
USER_ROLE_SCAN_TEXT = '"user"'
TOOL_RESULT_SCAN_TEXT = f'"{TOOL_RESULT_BLOCK_TYPE}"'
ASSISTANT_SCAN_TEXT = '"assistant"'
ALL_QUESTION_TOOL_NAME_SCAN_TEXTS = tuple(
    f'"{each_tool_name}"' for each_tool_name in sorted(ALL_QUESTION_TOOL_NAMES)
)

STOP_DEADLINE_SECONDS = 7.0
WATCHDOG_GRACE_SECONDS = 1.0
DECISION_PROCESS_FLAG = "--decide"
STDIN_WATCHDOG_SECONDS = 8.5
OUTPUT_WATCHDOG_SECONDS = 1.0
MAXIMUM_SCANNED_BYTES = 16 * 1024 * 1024
MAXIMUM_PAYLOAD_BYTES = 16 * 1024 * 1024
MAXIMUM_SCANNED_TEXT_BYTES = 2 * 1024 * 1024
LINE_FEED_BYTES = b"\n"
ESCAPED_ASCII_TEXT = "\\u00"
ESCAPED_PRINTABLE_ASCII_PATTERN = re.compile(r"\\u00[2-7][0-9a-fA-F]")
MARKER_SCAN_WINDOW_CHARACTERS = 1024 * 1024
MARKER_SCAN_OVERLAP_CHARACTERS = 128
MARKER_SCAN_LOOKAHEAD_CHARACTERS = 4
SEPARATOR_RUN_PATTERN = re.compile(r"[\s-]{2,}")
HYPHEN_CHARACTER = "-"

OPEN_ITEM_MARKER_PATTERN = re.compile(
    r"(?<![^\W_])(?<![^\W_]_)(?<![^\W_]__)(?<![^\W_]___)(?:"
    r"deferred|defer|defers|deferring|deferrals?"
    r"|follow-?ups?"
    r"|(?:a|the|another|one)\s+follow\s+ups?"
    r"|follow\s+up\s+(?:pr|pull\s+request|issue|task|ticket|change|commit)"
    r"|parked"
    r"|out[\s-]+of[\s-]+scope"
    r"|not\s+covered"
    r"|for\s+later"
    r"|later\s+(?:pull\s+request|pr)"
    r"|known\s+(?:gap|limitation)s?"
    r"|open\s+questions?"
    r"|unresolved"
    r"|uncertain|uncertainty"
    r"|not\s+sure"
    r"|unsure"
    r"|unclear"
    r"|i\s+assumed|we\s+assumed|(?:i|we)\s+assume"
    r"|assuming"
    r"|assumptions?"
    r"|unverified"
    r"|(?:could\s+not|couldn['\u2019]t|did\s+not)\s+verify"
    r"|untested"
    r"|not\s+tested"
    r"|(?:didn['’]t|did\s+not)\s+test"
    r"|you\s+may\s+want\s+to"
    r"|your\s+judge?ment"
    r"|(?:could\s+not|couldn['’]t|unable\s+to)\s+confirm"
    r"|separate\s+(?:pr|pull\s+request)"
    r"|not\s+yet\s+implemented"
    r"|judge?ment\s+calls?"
    r"|your\s+call"
    r"|up\s+to\s+you"
    r"|needs\s+your\s+(?:decision|judge?ment|approval)"
    r"|needs?\s+your\s+input"
    r"|i\s+need\s+you\s+to"
    r"|pending"
    r"|todo|tbd"
    r"|skipped|skipping"
    r"|not\s+done"
    r"|blocked"
    r"|(?:didn['’]t|not)\s+run"
    r"|(?:could\s+not|couldn['’]t)\s+reproduce"
    r"|left\s+(?:it|this|that|them|these)\s+for\s+you"
    r"|for\s+you\s+to\s+decide"
    r"|(?:waiting|waits)\s+on\s+you"
    r")(?![^\W_])(?!_{1,3}[^\W_])",
    re.IGNORECASE,
)
INDENTED_CODE_LINE_PATTERN = re.compile(r"^(?: {4}|\t)")
LIST_ITEM_LINE_PATTERN = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])[ \t]+\S")
PATH_JOINING_CHARACTERS = "./\\"
PATH_SEPARATOR_PATTERN = re.compile(r"[/\\]")
PATH_BREAK_PATTERN = re.compile(r"\s")
FILE_NAME_PATTERN = re.compile(r"[^\s/\\]+\.(?P<extension>[a-z0-9]{1,5})")
PATH_EDGE_CHARACTERS = "\"'`()[]<>{},;:!?.*_~\u201c\u201d\u2018\u2019\u00ab\u00bb\u2026"
PATH_REACH_CHARACTERS = 96
MINIMUM_PATH_SEGMENT_COUNT = 2
NO_OPEN_ITEMS_DECLARATION = "Open items: none."
DECLARATION_LINE_PATTERN = re.compile(
    r"(?P<mark>\*\*|__|\*|_|)"
    + re.escape(NO_OPEN_ITEMS_DECLARATION.removesuffix("."))
    + r"\.?(?P=mark)"
)

MAXIMUM_HOLD_COUNT = 2
FEEDBACK_OPENING_LENGTH = 200
MAXIMUM_QUOTED_LINE_COUNT = 8
MAXIMUM_QUOTED_LINE_LENGTH = 160
CLIPPED_LINE_END = "..."

CLOSING_ROUND_REASON_LEAD = (
    "This session wrote about open items and sent no question card after them."
)
WORK_REASON_LEAD = (
    "This session did work and ended without a question card or the declaration line."
)
ALL_REASON_LEADS = (CLOSING_ROUND_REASON_LEAD, WORK_REASON_LEAD)
OPEN_ITEM_LINES_LABEL = "The lines:"
QUOTED_LINE_TEMPLATE = '"{line}"'
REMAINING_LINES_TEMPLATE = "Earlier lines left out here: {remaining_count}."
CODE_SPAN_SHOWN_TEXT = "`...`"
READ_ITEMS_INSTRUCTION = (
    "Read the task list, your notes, and the live state of each item. Drop each item that is done."
)
CARD_INSTRUCTION = (
    "Write one short chat brief that covers every item that still stands, with each link in it."
    " question_brief_gate.py counts every chat word and every list or table item this turn wrote"
    " since the last typed prompt or question result, the reply above included, and refuses a"
    " question past 450 words or 15 items. Keep the brief short enough that the total stays"
    " inside that limit. When the reply above is already over it, write a one-line brief and send"
    " the cards: that first call is refused, and a refused question starts a new count, so send"
    " the same cards again at once with no new text. Send each item as its own AskUserQuestion"
    " question. Put at most four questions in one call, so a longer round takes more calls. Give"
    " each question a header of 12 characters or fewer and two or three options, your"
    " recommendation first. Give each option a one-sentence description. A card shows plain"
    " text, so write a link in a card as a bare URL. After the user answers, act on each answer"
    " and close with what you did with it. Do not restate the items, because open-item lines"
    " written after the cards start a new round. When that work leaves nothing open, end the"
    f" reply with the line {NO_OPEN_ITEMS_DECLARATION}"
)
CLOSING_ROUND_INSTRUCTION = (
    f"{READ_ITEMS_INSTRUCTION} {CARD_INSTRUCTION} When the lines name nothing that is still open,"
    " send one question that says so and lets the user add an item."
)
WORK_INSTRUCTION = (
    f"{READ_ITEMS_INSTRUCTION} When something is deferred, uncertain, or needs or can use the"
    " user's judgment, brief it and send the cards, as follows."
    f" {CARD_INSTRUCTION} When nothing is, do not list what is not open: end the reply with this"
    f" exact line alone, in plain text with no backticks or list marker: {NO_OPEN_ITEMS_DECLARATION}"
)
REASON_PART_SEPARATOR = "\n"
