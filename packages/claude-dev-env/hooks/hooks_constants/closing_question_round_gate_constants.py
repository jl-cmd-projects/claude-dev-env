"""Constants for the closing question round Stop gate.

Groups: the payload and transcript fields that mark a stop the gate leaves
alone, the transcript text each cheap scan looks for, the time and size
budget, the wording that marks an open item, the masking of indented code,
the old declaration line, the In progress footer and the words its coverage
check skips, the hold cap, the four hold reasons, and the keyword
and flag file that turn the gate off for one session.
"""

from __future__ import annotations

import os
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
FOOTER_JOBS_MARKER_NAME = "closing-question-round-footer-jobs"
FOOTER_JOBS_KEY_TEMPLATE = "footer-jobs-{digest}"
FOOTER_JOBS_FILE_TEMPLATE = "claude-{marker}-{session}.txt"
FOOTER_JOBS_FILE_MODE = 0o600
FOOTER_JOBS_TEMP_SUFFIX = ".part"
MESSAGE_ID_KEY = "id"
FOOTER_SNAPSHOT_SEPARATOR = " "
FOOTER_SNAPSHOT_PART_COUNT = 3
FOOTER_SNAPSHOT_LINE_SEPARATOR = "\n"
FOOTER_SNAPSHOT_KEPT_COUNT = 3
NO_FOLLOW_FLAG = getattr(os, "O_NOFOLLOW", 0)
FOOTER_JOBS_READ_LIMIT = 1024
FOOTER_JOBS_TEXT_ENCODING = "ascii"
FOOTER_JOBS_DIGEST_LENGTH = 32
FIRST_PERSON_ITEM_PATTERN = re.compile(r"^\W*I(?:\s|['’]m\b)")
SENTENCE_BREAK_PATTERN = re.compile(r"(?<=[.!?;])\s+")
OTHER_PARTY_REQUEST_PATTERN = re.compile(
    r"\b(?:need|needs|want|wants|waiting\s+for|wait\s+for|ask|asks|asking)\b[^.!?;]{0,80}?\bto\s+"
    r"(?:pick|choose|select|approve|confirm|decide|reply|answer|review|sign|say|tell)\b"
    r"|\b(?:until|once|when|after|unless|before)\b[^.!?;]{0,80}?"
    r"\b(?:picks|chooses|selects|approves|decides|answers|replies|signs\s+off)\b"
    r"|\b(?:need|needs|want|wants|waiting\s+for|wait\s+for)\b[^.!?;]{0,80}?\bfrom\s+(?:the\s+|a\s+|an\s+|my\s+|our\s+)?"
    r"(?:owner|user|client|customer|team|lead|manager|reviewer|approver|admin|maintainer|designer|stakeholder)s?\b",
    re.IGNORECASE,
)
REQUEST_WORD_ALTERNATIVES = (
    "please|pick|choose|select|approve|confirm|decide|reply|answer|tell|send|review|let|give|share|sign|say|name"
)
REQUEST_OPENER_PATTERN = re.compile(
    r"^\W*(?:(?:next|then|finally|also|now|first|second|third|lastly|and|so)\b\W*)?"
    rf"(?:{REQUEST_WORD_ALTERNATIVES})\b",
    re.IGNORECASE,
)
USER_MENTION_PATTERN = re.compile(r"\byou(?:r|rs|rself)?\b", re.IGNORECASE)
PURPOSE_CLAUSE_PATTERN = re.compile(
    r"\bso(?:\s+that)?\s+(?:you(?:\s+can)?\s+(?:see|know|get|read|follow|have|hear|learn|find|watch|track)"
    r"|your(?:\s+\w+){1,2}?\s+(?:stays?|remains?|keeps?|updates?|shows?|match(?:es)?|loads?|works?|runs?|arrives?|is|are))\b",
    re.IGNORECASE,
)
PURPOSE_CLAUSE_STAND_IN = "so"
COORDINATED_REQUEST_PATTERN = re.compile(
    PURPOSE_CLAUSE_PATTERN.pattern
    + rf"[^.!?;]{{0,80}}?\b(?:and|or|then)\s+(?:then\s+)?(?:{REQUEST_WORD_ALTERNATIVES})\b",
    re.IGNORECASE,
)
DECISION_DEPENDENCY_PATTERN = re.compile(
    r"\b(?:approv\w*|decid\w*|decision\w*|sign-?off|go-ahead|permission|consent|answers?|input|choices?|confirmation)\b",
    re.IGNORECASE,
)
ALL_BACKGROUND_JOB_ID_KEYS = ("id", "task_id", "taskId")
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
MAXIMUM_REPLAYED_TRANSCRIPT_BYTES = 64 * 1024 * 1024
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
PATH_EDGE_CHARACTERS = "\"'`()[]<>{},;:!?.*_~\u201c\u201d\u2018\u2019\u00ab\u00bb\u2039\u203a\u2026"
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
IN_PROGRESS_TASKS_REASON_LEAD = (
    "This session declared no open items while its own task list holds work in progress."
)
FOOTER_MISSING_REASON_LEAD = (
    "This session did work while work is still in progress and ended without the In progress footer."
)
FOOTER_CHANGED_REASON_LEAD = (
    "This session's work changed since its last In progress footer, and the reply ended without a new one."
)
FOOTER_GAP_REASON_LEAD = (
    "This session's In progress footer leaves out work that is still in progress."
)
ALL_REASON_LEADS = (
    CLOSING_ROUND_REASON_LEAD,
    IN_PROGRESS_TASKS_REASON_LEAD,
    FOOTER_MISSING_REASON_LEAD,
    FOOTER_GAP_REASON_LEAD,
)
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
    " written after the cards start a new round. When work is still in progress, end the reply"
    " with the In progress footer. When nothing is in progress, end it with no closing line."
)
CLOSING_ROUND_INSTRUCTION = (
    f"{READ_ITEMS_INSTRUCTION} {CARD_INSTRUCTION} When the lines name nothing that is still open,"
    " send one question that says so and lets the user add an item."
)
FOOTER_HEADING = "In progress:"
FOOTER_HEADING_PATTERN = re.compile(
    r"(?P<mark>\*\*|__|)" + re.escape(FOOTER_HEADING) + r"(?P=mark)", re.IGNORECASE
)
FOOTER_ITEM_LINE_PATTERN = re.compile(r"^ {0,3}[-*+][ \t]+(?P<item>\S.*)$")
FOOTER_CONTINUATION_LINE_PATTERN = re.compile(r"^[ \t]+\S")
FOOTER_WORD_PATTERN = re.compile(r"[a-z][a-z']+")
POSSESSIVE_ENDING = "'s"
MATCH_PREFIX_LENGTH = 5
ALL_SUBJECT_SKIP_WORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "at", "by", "with",
        "from", "into", "fix", "fixes", "watch", "open", "opens", "run", "runs", "check",
        "checks", "finding", "findings", "make", "add", "update", "scheduled", "wake", "lint",
        "pr", "prs", "pull", "request", "ci", "task", "tasks", "new", "old", "stale", "merge",
        "start", "get", "set",
    }
)
TASK_KEY_WORD_SEPARATOR = " "
FOOTER_ITEM_PART_SEPARATOR = " "
FOOTER_TASK_LINE_TEMPLATE = "- {subject} [{key_words}]"
FOOTER_TASKS_LABEL = "Work in progress, with the words that name each task in brackets:"
FOOTER_GAP_LABEL = "Left out of the footer:"
FOOTER_KEY_WORDS_INSTRUCTION = "Keep the words in brackets above, so the footer names each task."
FOOTER_INSTRUCTION = (
    f"End the reply with the In progress footer: a line that holds only {FOOTER_HEADING}, then"
    " one list item for each piece of work still in progress. The user reads this footer on a"
    " phone and does not read the code, so write it for them in plain words. Write each item in"
    " first person, as one Claude, and say what the work does for the user and where it stands,"
    " in at most 25 words. Leave out task numbers, run, build, and check numbers, commit ids, agent, session, schedule, or"
    " process ids, file paths, and code names. A pull request number is the one number that may"
    " stay. Leave out which agent, helper, or worker does the work. Leave out tool and process"
    " words, such as agent, subagent, shell, monitor, lint, cron, wake, push, branch, rebase,"
    " check run, log, or background. When the work waits on tests, call them the automated"
    " tests, not checks, and do not call the work a run. Say what is left before the work is done and what it shows the"
    " user, in words the user can picture. Write each short form in full: pull request, not PR."
    " Give the work that runs on its own one short clause that says what it gets the user, and do"
    " not list each job or each preparation step. Write the footer in your own words for this"
    " session. Do not end with the line Open items: none. When nothing is in progress and no"
    " background work runs, end the reply with no closing line. Send the footer once: a later"
    " reply ends with it again only when a piece of work started, finished, or changed where it"
    " stands, so a reply that says nothing is new ends with no footer."
)
REASON_PART_SEPARATOR = "\n"
SCANNED_PARAGRAPH_SEPARATOR = "\n\n"
FOOTER_STATUS_MARKER_PATTERN = re.compile(r"\b(?:pending|blocked|not done|not run)\b", re.IGNORECASE)
FOOTER_STATUS_STAND_IN = "in progress"

SESSION_ID_KEY = "session_id"
BYPASS_KEYWORD = "--nocards"
BYPASS_KEYWORD_PATTERN = re.compile(
    rf"(?<![\w-]){re.escape(BYPASS_KEYWORD)}(?![\w-])", re.IGNORECASE
)
BYPASS_FLAG_FILE_PREFIX = "claude-closing-question-gate-off."
BYPASS_FLAG_FILE_SUFFIX = ".flag"
BYPASS_FLAG_CREATE_MODE = "x"
ADDITIONAL_CONTEXT_KEY = "additionalContext"
GATE_TURNED_OFF_CONTEXT = "Question-card stop gate is now OFF"
GATE_TURNED_ON_CONTEXT = "Question-card stop gate is now ON"
