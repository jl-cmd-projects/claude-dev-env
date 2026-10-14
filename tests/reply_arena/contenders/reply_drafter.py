"""Ask a small headless model for a reply that passes ``reply_violation``.

``draft_compliant_reply`` sends the long reply, the rule it broke, and the
rule list to ``claude -p`` on a small model. It checks the draft with the
same ``reply_violation`` the gate uses, retries once with the new rule, and
returns None when no draft passes. The helper process carries
DRAFTER_GUARD_ENV_VAR, so a hook that runs inside it exits at once.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

hooks_directory = Path(__file__).resolve().parents[3] / "packages" / "claude-dev-env" / "hooks"
for each_path in (hooks_directory, hooks_directory / "blocking"):
    if str(each_path) not in sys.path:
        sys.path.insert(0, str(each_path))

from hooks_constants.reply_length_gate_constants import (
    MAXIMUM_SENTENCE_COUNT,
    MAXIMUM_WORDS_PER_SENTENCE,
)
from reply_length_gate import reply_violation

DRAFTER_GUARD_ENV_VAR = "CHAT_REPLY_DRAFTER_ACTIVE"
DRAFTER_MODEL_ENV_VAR = "CHAT_REPLY_DRAFTER_MODEL"
DEFAULT_DRAFTER_MODEL = "haiku"
DRAFTER_TIMEOUT_SECONDS = 45
MAXIMUM_DRAFT_ATTEMPTS = 2
ARENA_RUN_DIRECTORY_ENV_VAR = "ARENA_RUN_DIR"
HELPER_LOG_FILE_NAME = "helper.jsonl"
DRAFTER_RULES = (
    f"Rewrite the reply below so it obeys every rule. At most {MAXIMUM_SENTENCE_COUNT} sentences,"
    f" each at most {MAXIMUM_WORDS_PER_SENTENCE} words. Each line and each list item counts as one sentence."
    " Keep the outcome, the recommendation, and any number, path, or command the user needs."
    " Drop background the user did not ask for."
    " No colon in the middle of a sentence. No em dash."
    " Write a pull request number only inside a markdown link."
    " A sentence that gives a cause, with so, because, caused, due to, therefore, or means,"
    " must hold its own evidence as inline code, a URL, or a markdown link. Otherwise state the fact without the cause word."
    " Never use these words: real, really, genuine, actual, actually, likely, probably, seems, maybe, perhaps,"
    " might be, may be, appears to, suspect, guess, presumably."
    " Speak as the original author to the original reader."
    " Never mention the rule, the length, or this rewrite."
    " Never add, drop, or change a fact, a command, a flag, or a file name; leave out a whole point instead."
    " Return only the rewritten reply, with no preface."
)


def helper_command(model_name: str) -> list[str]:
    """Return the headless claude command that runs the drafter with no settings and no tools."""
    return [
        "claude",
        "-p",
        "--model",
        model_name,
        "--setting-sources",
        "",
        "--tools",
        "",
        "--no-session-persistence",
        "--session-id",
        str(uuid.uuid4()),
        "--output-format",
        "json",
        "--system-prompt",
        DRAFTER_RULES,
    ]


def helper_environment() -> dict[str, str]:
    """Return the environment for the helper process, marked so nested hooks exit."""
    environment = dict(os.environ)
    environment[DRAFTER_GUARD_ENV_VAR] = "1"
    environment.pop("CLAUDE_CODE_SESSION_ID", None)
    return environment


def ask_helper(original_reply: str, violation: str) -> tuple[str | None, float]:
    """Return the helper's draft and its cost in dollars, or None and 0 on failure."""
    request_text = (
        f"Rule the reply broke: {violation}\n\nReply to rewrite:\n\n{original_reply}"
    )
    model_name = os.environ.get(DRAFTER_MODEL_ENV_VAR, DEFAULT_DRAFTER_MODEL)
    try:
        completed = subprocess.run(
            helper_command(model_name),
            input=request_text,
            capture_output=True,
            text=True,
            timeout=DRAFTER_TIMEOUT_SECONDS,
            env=helper_environment(),
            check=False,
        )
        helper_result = json.loads(completed.stdout)
        draft_text = helper_result.get("result")
        cost = float(helper_result.get("total_cost_usd") or 0.0)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, AttributeError, ValueError):
        return None, 0.0
    if helper_result.get("is_error") is True:
        return None, cost
    if not isinstance(draft_text, str) or not draft_text.strip():
        return None, cost
    return draft_text.strip(), cost


def log_helper_call(record: dict[str, object]) -> None:
    """Append one helper call record to the arena run directory, when one is set."""
    run_directory = os.environ.get(ARENA_RUN_DIRECTORY_ENV_VAR)
    if not run_directory:
        return
    with open(
        Path(run_directory) / HELPER_LOG_FILE_NAME, "a", encoding="utf-8"
    ) as log_file:
        log_file.write(json.dumps(record) + "\n")


def draft_compliant_reply(original_reply: str, violation: str) -> str | None:
    """Return a draft that passes ``reply_violation``, or None after MAXIMUM_DRAFT_ATTEMPTS."""
    started_at = time.monotonic()
    total_cost = 0.0
    current_violation = violation
    passing_draft = None
    attempt_count = 0
    for attempt_count in range(1, MAXIMUM_DRAFT_ATTEMPTS + 1):
        draft_text, call_cost = ask_helper(original_reply, current_violation)
        total_cost += call_cost
        if draft_text is None:
            continue
        draft_violation = reply_violation(draft_text, None, None)
        if draft_violation is None:
            passing_draft = draft_text
            break
        current_violation = draft_violation
    log_helper_call(
        {
            "attempts": attempt_count,
            "passed": passing_draft is not None,
            "cost_usd": total_cost,
            "seconds": round(time.monotonic() - started_at, 2),
            "draft": passing_draft,
        }
    )
    return passing_draft
