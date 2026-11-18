"""Configuration for the plain-language footer eval.

Groups: the headless runs and their models, the two session scenarios, the
raw-state prompt full of internal detail, the deterministic jargon scan, the
calibrated judge prompt, and the report text.
"""

import re
from pathlib import Path

from closing_round_eval_support.config.constants import FLOW_ROOT, REPOSITORY_ROOT

BLOCKING_DIRECTORY = REPOSITORY_ROOT / "packages" / "claude-dev-env" / "hooks" / "blocking"
BROKER_SCRIPT = Path.home() / ".claude" / "scripts" / "account_broker.py"
DEFAULT_OUT_DIRECTORY = FLOW_ROOT / "plain-language-runs"
DEFAULT_SAMPLE_COUNT = 3
DEFAULT_WORKER_COUNT = 6
MAXIMUM_HOLD_ROUNDS = 2
HEADLESS_TIMEOUT_SECONDS = 300
WRITER_MODEL = "claude-opus-5-5"
WRITER_EFFORT = "medium"
JUDGE_MODEL = "claude-sonnet-5-5"
JUDGE_EFFORT = "high"
SETTING_SOURCES = "project"
PYTHON_EXECUTABLE_NAME = "python3"
BROKER_PRODUCT = "claude"
BROKER_REPORT_SUFFIX = ".broker.json"
SAMPLE_FILE_TEMPLATE = "{hook_label}-{scenario}-{sample}.json"
JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n")
UTF8_ENCODING = "utf-8"
FOOTER_LINE_SEPARATOR = "\n"
LOGGED_TEXT_LIMIT = 200
JUDGE_ERROR_TEXT_LIMIT = 400
SAMPLE_JSON_INDENT = 2

ALL_TASK_ENTRIES = [
    {"id": "27", "subject": "Merge stale theme PR", "status": "completed"},
    {"id": "28", "subject": "Fix list reader lint finding", "status": "in_progress"},
    {
        "id": "29",
        "subject": "Watch discount ledger scheduled wake",
        "status": "in_progress",
    },
    {"id": "30", "subject": "Open ledger PR", "status": "pending"},
]
ALL_BACKGROUND_ENTRIES = [
    {"id": f"a{each_number}", "type": "subagent", "status": "running"}
    for each_number in range(12, 21)
] + [
    {"id": "sh1", "type": "shell", "status": "running"},
    {"id": "sh2", "type": "shell", "status": "running"},
    {"id": "sh3", "type": "shell", "status": "running"},
    {"id": "mo1", "type": "monitor", "status": "running"},
    {"id": "mo2", "type": "monitor", "status": "running"},
]
ALL_SCENARIO_BACKGROUNDS = {"with-background": ALL_BACKGROUND_ENTRIES, "tasks-only": []}

TYPED_PROMPT = "Land the list reader fix and the discount ledger change."
FIRST_REPLY = (
    "Agent a12 finished the list reader lint fix and pushed 4f3c2e1 to PR 8801. The lint check"
    " is green on the new head.\n\nThe ledger wake is set and will start the ledger PR once its"
    " run passes.\n\nOpen items: none."
)
RAW_STATE_PROMPT = (
    "You are an orchestrator agent in a Claude Code session the user follows from a phone.\n"
    "Session state, raw:\n"
    '- Task list: #27 completed "Merge stale theme PR"; #28 in_progress "Fix list reader lint'
    ' finding" (owner agent a12, pushed 4f3c2e1 to PR 8801, ruff lint job green on head 4f3c2e1,'
    ' full CI run 19283746 still in progress); #29 in_progress "Watch discount ledger scheduled'
    ' wake" (cron-ledger-7f2a, one-shot, 0 9 * * *, checks ledger run 77123); #30 pending "Open'
    ' ledger PR" (blocked by #29).\n'
    "{background_line}"
    "- Session id session_01ExampleSession. Last tool call toolu_b1: gh pr checks 8801.\n"
    'A task notification woke you: "Agent a12 (lint fix for list reader) completed. Pushed'
    ' 4f3c2e1." You checked the pull request and wrote this reply:\n\n'
    "{first_reply}\n\n"
)
BACKGROUND_LINE = (
    "- Background tasks (14): 9 subagents (a12 to a20, pstack:poteto-agent: lint fix follow-up"
    " for list_reader.py, rebase discount-ledger branch, draft PR body for #30, review diff"
    " 4f3c2e1..HEAD, babysit PR 8801 CI, ledger_reconcile.py dry run against Neon branch"
    " br-ledger-77, efficient-review on PR 8801, update followup_ledger.json, watch board topic"
    " orch-board), 3 shells (gh run watch 19283746, pytest -x tests/ledger -k discount, tail -f"
    " logs/discount_77123.log), 2 monitors (github watch_pr 8801, ntfy listen orch-board).\n"
)
NO_BACKGROUND_LINE = "- Background tasks: none.\n"
HOLD_PROMPT_TEMPLATE = "Then the Stop hook held your stop with this message:\n\n{reason}\n\n"
WRITE_AGAIN_PROMPT = (
    "Write your full closing reply again now, as the user will see it. Output only the reply text."
)

ALL_SCAN_RULES = (
    ("commit hash", re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")),
    ("task number", re.compile(r"(?<![\w&])#\d+\b")),
    (
        "short id",
        re.compile(
            r"\b(?:agent|session|task|cron|job|run)\s+[a-z]{0,3}\d+[a-z0-9]*\b",
            re.IGNORECASE,
        ),
    ),
    (
        "coded id",
        re.compile(
            r"\b[a-z]{1,4}\d{1,4}\b(?!\s*(?:am|pm|:))|\b[a-z]+(?:-[a-z0-9]+)+-\d+\b"
            r"|\bsession_\w+|\btoolu_\w+|\btrig_\w+"
        ),
    ),
    (
        "file path",
        re.compile(r"(?:\b[\w.-]+/)+[\w.-]+|\b[\w-]+\.(?:py|js|ts|json|md|ya?ml|sh|toml|log)\b"),
    ),
    ("code name", re.compile(r"`[^`]+`|\b[a-z]+(?:_[a-z0-9]+)+\b|\b[a-z]+[A-Z]\w+\b")),
    (
        "short form",
        re.compile(r"\b(?:PRs?|CI|MCP|API|IDs?|UI|CLI|WIP|ETA|LGTM|DB|repo)\b"),
    ),
    (
        "worker word",
        re.compile(
            r"\b(?:sub-?agents?|agents?|shells?|monitors?|coordinator|workers?|sessions?|threads?"
            r"|teammates?|orchestrator|helpers?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "tool word",
        re.compile(
            r"\b(?:cron|hooks?|lint(?:er)?|one-shot|wake(?:s|up)?|head|commits?|push(?:ed|es)?"
            r"|check run|payload|task list|background tasks?|scheduled task|stdout|exit code"
            r"|rebase|branch)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "process count",
        re.compile(r"\b\d+\s+(?:background\s+)?(?:tasks?|jobs?|processes)\b", re.IGNORECASE),
    ),
)

JUDGE_PROMPT_TEMPLATE = """You grade the closing footer of an assistant reply. The reader is a person who follows a long work session on a phone and does not read the code. The person asked for this footer: a short, high-level overview of what is still in progress, in plain words.

Allowed, do not flag:
- A line that says where a piece of work stands, such as waiting for tests to finish. Status is the footer's job.
- The names of the products or features the work is about, such as the list reader or the discount ledger. The person assigns that work and knows those names.
- A pull request number written in full, such as "pull request 8801". Clock times.

Flag each of these as jargon:
1. Identifiers: commit hashes, task numbers such as #28, agent, session, schedule, or process ids, file paths, variable or code names.
2. Short forms not spelled out, such as PR or CI.
3. Any other actor doing the work: another agent, worker, helper, session, thread, or the coordinator. The reply speaks as one Claude in first person.
4. Tool and process words that mean something only to the agent: lint, head, branch, rebase, dry run, log, check run, wake, cron, shell, monitor, subagent, message board, follow-up list, background tasks, and counts of processes by type.
5. A list of internal chores the person would not act on or picture, such as each preparation step behind a piece of work.

Also mark a line too long to read at a glance on a phone (more than about 35 words) as too_long.

Return only JSON, no prose, in this shape:
{{"lines": [{{"line": "<the line>", "words": 0, "too_long": false, "pass": true, "jargon": [{{"phrase": "<exact quote>", "reason": "<short reason>"}}]}}]}}
A line passes when it has no jargon phrase and is not too long.

The footer:
<<<
{footer}
>>>"""

ROW_TEMPLATE = (
    "{label:<4} {hook_label} {scenario} #{sample}: footer {has_footer}, scan hits {scan_count},"
    " judge {judge_lines}, holds {hold_count}, final reply held {is_final_held}"
)
SUMMARY_TEMPLATE = (
    "{hook_label}: plain-language criterion passed {passed_count}/{sample_count};"
    " footer written {footer_count}/{sample_count}"
)
PASSED_ROW_LABEL = "ok"
MISSED_ROW_LABEL = "MISS"
