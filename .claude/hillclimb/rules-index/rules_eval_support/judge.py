"""Ask a second model whether a session followed its case's rule."""

import json
import subprocess
import tempfile
from pathlib import Path

from rules_eval_support.launch import launch_words
from rules_eval_support.config.constants import (
    JSON_INDENT,
    JUDGE_EFFORT,
    JUDGE_MODEL,
    JUDGE_PROMPT_TEMPLATE,
    JUDGE_REPORT_FILE_NAME,
    JUDGE_SETTING_SOURCES,
    JUDGE_TIMEOUT_SECONDS,
    JUDGE_TRANSCRIPT_CHARACTER_LIMIT,
    JUDGE_VERDICT_PATTERN,
)


def judge_prompt(prompt: str, rubric: str, all_turns: list[dict[str, str]]) -> str:
    """Return the judge's ask for one session, with the transcript cut to its limit.

    Args:
        prompt: The case's ask.
        rubric: The case's pass and fail criteria.
        all_turns: The session as trace turns.

    Returns:
        The full text sent to the judge.
    """
    transcript = json.dumps(all_turns, indent=JSON_INDENT)[-JUDGE_TRANSCRIPT_CHARACTER_LIMIT:]
    return JUDGE_PROMPT_TEMPLATE.format(prompt=prompt, rubric=rubric, transcript=transcript)


def parse_verdict(judge_reply: str) -> dict[str, object] | None:
    """Return the judge's verdict object, or None when the reply carries none.

    ::

        'Done. {"pass": true, "reason": "Read the README."}' -> {"pass": True, ...}
        "I cannot tell."                                    -> None

    Args:
        judge_reply: The judge's final text.

    Returns:
        The last JSON object in the reply that has a boolean ``pass`` field.
    """
    for each_match in reversed(JUDGE_VERDICT_PATTERN.findall(judge_reply)):
        try:
            verdict = json.loads(each_match)
        except json.JSONDecodeError:
            continue
        if isinstance(verdict.get("pass"), bool):
            return verdict
    return None


def run_judge(prompt_text: str, is_direct: bool) -> tuple[dict[str, object] | None, dict[str, object]]:
    """Run the judge once, headless, in an empty folder.

    Args:
        prompt_text: The text from judge_prompt.
        is_direct: Whether to skip the broker and run on the caller's account.

    Returns:
        The verdict (None when unreadable) and the judge's result event.
    """
    judge_directory = Path(tempfile.mkdtemp(prefix="rules-judge-"))
    all_judge_words = [
        "claude", "-p", prompt_text, "--model", JUDGE_MODEL, "--effort", JUDGE_EFFORT,
        "--max-turns", "1", "--output-format", "json", "--setting-sources", JUDGE_SETTING_SOURCES,
    ]
    completed = subprocess.run(
        launch_words(judge_directory.parent / (judge_directory.name + "-" + JUDGE_REPORT_FILE_NAME), all_judge_words, is_direct),
        cwd=judge_directory,
        capture_output=True,
        text=True,
        timeout=JUDGE_TIMEOUT_SECONDS,
        check=False,
    )
    try:
        judge_event = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None, {}
    if not isinstance(judge_event, dict):
        return None, {}
    return parse_verdict(str(judge_event.get("result", ""))), judge_event
