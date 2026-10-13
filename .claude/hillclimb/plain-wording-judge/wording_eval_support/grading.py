"""Fill the hook prompt, read the judge's verdict, and tally a run."""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from wording_eval_support.config.constants import (
    ARGUMENTS_PLACEHOLDER,
    DENIED_VERDICT,
    FAIL_LABEL,
    JUDGE_STATUS_MESSAGE,
    REPLY_TOOL_NAME,
    VERDICT_PATTERN,
)


@dataclass(frozen=True)
class Tally:
    """Counts from one scored run."""

    fails_caught: int
    fail_count: int
    passes_flagged: int
    pass_count: int
    unreadable_count: int


def find_judge_prompt(all_hooks_config: Mapping) -> str:
    """Return the plain-wording hook prompt from a parsed hooks.json.

    Args:
        all_hooks_config: The parsed hooks.json document.

    Returns:
        The prompt text of the hook whose statusMessage names the wording judge.

    Raises:
        LookupError: When no hook carries the wording judge statusMessage.
    """
    all_hooks = [
        each_hook
        for each_group in all_hooks_config["hooks"]["PreToolUse"]
        for each_hook in each_group.get("hooks", [])
    ]
    for each_hook in all_hooks:
        if each_hook.get("statusMessage") == JUDGE_STATUS_MESSAGE:
            return each_hook["prompt"]
    raise LookupError(JUDGE_STATUS_MESSAGE)


def fill_prompt(prompt: str, line_text: str) -> str:
    """Return the prompt with the reply hook input in place of its placeholder.

    Args:
        prompt: The hook prompt holding the arguments placeholder.
        line_text: The reply text the judge reads.

    Returns:
        The prompt the hook would send for that reply.
    """
    hook_input = json.dumps({"tool_name": REPLY_TOOL_NAME, "tool_input": {"text": line_text}})
    return prompt.replace(ARGUMENTS_PLACEHOLDER, hook_input)


def parse_verdict(judge_stdout: str) -> bool | None:
    """Return whether the judge denied the line.

    Args:
        judge_stdout: The judge's stdout.

    Returns:
        True for a deny, False for an allow, None when no verdict is present.
    """
    verdict_match = VERDICT_PATTERN.search(judge_stdout)
    if verdict_match is None:
        return None
    return verdict_match.group(1) == DENIED_VERDICT


def tally(all_cases: Iterable[Mapping], all_flags: Iterable[bool | None]) -> Tally:
    """Count fails caught and passes flagged.

    Args:
        all_cases: Cases carrying an expected label.
        all_flags: The judge verdict for each case, in the same order.

    Returns:
        The run's counts.
    """
    all_pairs = list(zip(all_cases, all_flags))
    all_fail_flags = [each_flag for each_case, each_flag in all_pairs if each_case["expected"] == FAIL_LABEL]
    all_pass_flags = [each_flag for each_case, each_flag in all_pairs if each_case["expected"] != FAIL_LABEL]
    return Tally(
        fails_caught=sum(each_flag is True for each_flag in all_fail_flags),
        fail_count=len(all_fail_flags),
        passes_flagged=sum(each_flag is True for each_flag in all_pass_flags),
        pass_count=len(all_pass_flags),
        unreadable_count=sum(each_flag is None for each_flag in all_flags),
    )
