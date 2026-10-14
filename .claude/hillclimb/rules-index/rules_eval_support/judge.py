"""Ask a second model whether a session followed its case's rule."""

import json
import tempfile
from pathlib import Path

from rules_eval_support.launch import launch_words
from rules_eval_support.config.constants import (
    JUDGE_EFFORT,
    JUDGE_MODEL,
    JUDGE_PROMPT_TEMPLATE,
    JUDGE_REPLY_FILE_NAME,
    JUDGE_REPORT_FILE_NAME,
    JUDGE_TIMEOUT_SECONDS,
    JUDGE_TRANSCRIPT_CHARACTER_LIMIT,
    JUDGE_WORK_DIRECTORY_NAME,
    OBJECT_START,
)
from session_eval_support.config.constants import JSON_INDENT, SESSION_SETTING_SOURCES
from session_eval_support.session import run_until_timeout


def _transcript_within_limit(all_turns: list[dict[str, str]]) -> str:
    all_kept = list(all_turns)
    transcript = json.dumps(all_kept, indent=JSON_INDENT)
    while len(transcript) > JUDGE_TRANSCRIPT_CHARACTER_LIMIT and len(all_kept) > 1:
        del all_kept[1]
        transcript = json.dumps(all_kept, indent=JSON_INDENT)
    return transcript


def judge_prompt(prompt: str, rubric: str, all_turns: list[dict[str, str]]) -> str:
    """Return the judge's ask for one session, with the transcript cut to its limit.

    The transcript stays valid JSON: the first turn, the user's ask, stays,
    and whole turns after it drop, oldest first, until the JSON fits.

    Args:
        prompt: The case's ask.
        rubric: The case's pass and fail criteria.
        all_turns: The session as trace turns.

    Returns:
        The full text sent to the judge.
    """
    return JUDGE_PROMPT_TEMPLATE.format(prompt=prompt, rubric=rubric, transcript=_transcript_within_limit(all_turns))


def parse_verdict(judge_reply: str) -> dict[str, object] | None:
    """Return the judge's verdict object, or None when the reply carries none.

    ::

        'Done. {"pass": true, "reason": "Read the README."}' -> {"pass": True, ...}
        '{"pass": false, "reason": "uses {x}"}'              -> {"pass": False, ...}
        '{"pass": true, "evidence": {"pass": false}}'        -> {"pass": True, ...}
        "I cannot tell."                                    -> None

    Args:
        judge_reply: The judge's final text.

    Returns:
        The last top-level JSON object in the reply that has a boolean
        ``pass`` field. Braces inside strings and nested objects belong to
        the object around them.
    """
    decoder = json.JSONDecoder()
    verdict: dict[str, object] | None = None
    object_start = judge_reply.find(OBJECT_START)
    while object_start >= 0:
        try:
            candidate, object_end = decoder.raw_decode(judge_reply, object_start)
        except json.JSONDecodeError:
            object_start = judge_reply.find(OBJECT_START, object_start + 1)
            continue
        if isinstance(candidate, dict) and isinstance(candidate.get("pass"), bool):
            verdict = candidate
        object_start = judge_reply.find(OBJECT_START, object_end)
    return verdict


def run_judge(prompt_text: str, is_direct: bool) -> tuple[dict[str, object] | None, dict[str, object]]:
    """Run the judge once, headless, in an empty folder that is removed afterward.

    The prompt goes on standard input, so a long transcript stays clear of
    the command-line length limit and of shell parsing in a launcher shim.

    Args:
        prompt_text: The text from judge_prompt.
        is_direct: Whether to skip the broker and run on the caller's account.

    Returns:
        The verdict (None when unreadable or timed out) and the judge's result event.
    """
    all_judge_words = [
        "claude", "-p", "--model", JUDGE_MODEL, "--effort", JUDGE_EFFORT,
        "--max-turns", "1", "--output-format", "json", "--setting-sources", SESSION_SETTING_SOURCES,
    ]
    with tempfile.TemporaryDirectory(prefix="rules-judge-", ignore_cleanup_errors=True) as judge_root_name:
        judge_root = Path(judge_root_name)
        judge_directory = judge_root / JUDGE_WORK_DIRECTORY_NAME
        judge_directory.mkdir()
        reply_path = judge_root / JUDGE_REPLY_FILE_NAME
        with reply_path.open("wb") as reply_file:
            exit_code = run_until_timeout(
                launch_words(judge_root / JUDGE_REPORT_FILE_NAME, all_judge_words, is_direct),
                judge_directory,
                reply_file,
                JUDGE_TIMEOUT_SECONDS,
                prompt_text.encode("utf-8"),
            )
        reply_text = reply_path.read_text(encoding="utf-8", errors="replace")
    if exit_code is None:
        return None, {}
    try:
        judge_event = json.loads(reply_text)
    except json.JSONDecodeError:
        return None, {}
    if not isinstance(judge_event, dict):
        return None, {}
    return parse_verdict(str(judge_event.get("result", ""))), judge_event
