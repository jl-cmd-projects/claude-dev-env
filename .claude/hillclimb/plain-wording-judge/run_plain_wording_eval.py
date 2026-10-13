"""Score the plain-wording prompt hook against Jon's held-out marks.

Reads the hook prompt from hooks.json and the cases from cases.json, sends each
held-out line through `claude -p` on Haiku, and counts fails caught and passes
flagged. Writes one JSON line per case to the results file.
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EVAL_DIRECTORY = Path(__file__).resolve().parent
HOOKS_CONFIG_PATH = EVAL_DIRECTORY.parents[2] / "packages" / "claude-dev-env" / "hooks" / "hooks.json"
CASES_PATH = EVAL_DIRECTORY / "cases.json"
JUDGE_STATUS_MESSAGE = "claude-dev-env: checking each line reads plainly"
REPLY_TOOL_NAME = "mcp__hearthbot__reply"
HELD_OUT_SPLIT = "held_out"
FAIL_LABEL = "fail"
VERDICT_PATTERN = re.compile(r'"ok"\s*:\s*(true|false)')
CALL_TIMEOUT_SECONDS = 120
DEFAULT_WORKER_COUNT = 8


def judge_prompt() -> str:
    """Return the shipped plain-wording hook prompt."""
    hooks_config = json.loads(HOOKS_CONFIG_PATH.read_text(encoding="utf-8"))
    for each_group in hooks_config["hooks"]["PreToolUse"]:
        for each_hook in each_group.get("hooks", []):
            if each_hook.get("statusMessage") == JUDGE_STATUS_MESSAGE:
                return each_hook["prompt"]
    raise SystemExit("plain-wording hook not found in hooks.json")


def judge_flags(prompt: str, line_text: str, command_prefix: list[str]) -> bool | None:
    """Return True when the judge denies the line, False when it allows it, None when unreadable."""
    hook_input = json.dumps({"tool_name": REPLY_TOOL_NAME, "tool_input": {"text": line_text}})
    filled_prompt = prompt.replace("$ARGUMENTS", hook_input)
    completed = subprocess.run(
        [*command_prefix, "claude", "-p", "--model", "haiku", filled_prompt],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=CALL_TIMEOUT_SECONDS,
        check=False,
    )
    verdict_match = VERDICT_PATTERN.search(completed.stdout)
    if verdict_match is None:
        return None
    return verdict_match.group(1) == "false"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKER_COUNT)
    parser.add_argument("--command-prefix", type=shlex.split, default=[])
    arguments = parser.parse_args()
    prompt = judge_prompt()
    all_cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    held_out_cases = [each_case for each_case in all_cases if each_case["split"] == HELD_OUT_SPLIT]
    with ThreadPoolExecutor(max_workers=arguments.workers) as executor:
        all_flags = list(
            executor.map(
                lambda each_case: judge_flags(prompt, each_case["text"], arguments.command_prefix),
                held_out_cases,
            )
        )
    with arguments.results.open("w", encoding="utf-8") as results_file:
        for each_case, each_flag in zip(held_out_cases, all_flags):
            results_file.write(json.dumps({**each_case, "flagged": each_flag}) + "\n")
    fail_flags = [
        each_flag
        for each_case, each_flag in zip(held_out_cases, all_flags)
        if each_case["expected"] == FAIL_LABEL
    ]
    pass_flags = [
        each_flag
        for each_case, each_flag in zip(held_out_cases, all_flags)
        if each_case["expected"] != FAIL_LABEL
    ]
    unreadable_count = sum(each_flag is None for each_flag in all_flags)
    print(
        f"fails caught: {sum(each_flag is True for each_flag in fail_flags)} of {len(fail_flags)}"
    )
    print(
        f"passes flagged: {sum(each_flag is True for each_flag in pass_flags)} of {len(pass_flags)}"
    )
    print(f"unreadable verdicts: {unreadable_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
