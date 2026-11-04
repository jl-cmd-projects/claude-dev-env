"""Grade the reply length gate's exit code on fixed replies under each switch setting."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_HOOKS_DIRECTORY = Path(__file__).resolve().parents[1] / "hooks"
GATE_RELATIVE_PATH = Path("blocking") / "reply_length_gate.py"
REPLY_TOOL_NAME = "mcp__hearthbot__reply"
REPLY_LENGTH_ENVIRONMENT_PREFIX = "REPLY_LENGTH_"
SWITCHES_ON = {"REPLY_LENGTH_SENTENCE_CAP": "on", "REPLY_LENGTH_WORD_CAP": "on"}
BASELINE_CONFIGURATION = "baseline"
SWITCHES_UNSET_CONFIGURATION = "switches unset"
SWITCHES_ON_CONFIGURATION = "switches on"
FIRST_STDERR_LINE_LENGTH = 90
CASES = (
    (
        "51 short sentences",
        " ".join(["Build one passed."] * 51),
        {
            BASELINE_CONFIGURATION: 2,
            SWITCHES_UNSET_CONFIGURATION: 0,
            SWITCHES_ON_CONFIGURATION: 2,
        },
    ),
    (
        "one 40-word sentence",
        " ".join(["word"] * 40) + ".",
        {
            BASELINE_CONFIGURATION: 2,
            SWITCHES_UNSET_CONFIGURATION: 0,
            SWITCHES_ON_CONFIGURATION: 2,
        },
    ),
    (
        "3 short sentences",
        "The fix is in. Tests pass. It ships next.",
        {
            BASELINE_CONFIGURATION: 0,
            SWITCHES_UNSET_CONFIGURATION: 0,
            SWITCHES_ON_CONFIGURATION: 0,
        },
    ),
    (
        "banned word maybe",
        "The cause is maybe the cache.",
        {
            BASELINE_CONFIGURATION: 2,
            SWITCHES_UNSET_CONFIGURATION: 2,
            SWITCHES_ON_CONFIGURATION: 2,
        },
    ),
)


def run_gate(
    hooks_directory: Path, reply_text: str, switch_overrides: dict[str, str]
) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as home_directory:
        claude_directory = Path(home_directory) / ".claude"
        claude_directory.mkdir()
        (claude_directory / "visual-reply-mode.json").write_text(
            '{"enabled": true}', encoding="utf-8"
        )
        environment = {
            each_name: each_value
            for each_name, each_value in os.environ.items()
            if not each_name.startswith(REPLY_LENGTH_ENVIRONMENT_PREFIX)
        }
        environment.update(
            {
                "HOME": home_directory,
                "USERPROFILE": home_directory,
                "PYTHONPATH": str(hooks_directory),
                "CLAUDE_REPLY_BANNED_WORDS_PATH": str(
                    Path(home_directory) / "absent.json"
                ),
            }
        )
        environment.update(switch_overrides)
        hook_input = {
            "hook_event_name": "PreToolUse",
            "tool_name": REPLY_TOOL_NAME,
            "tool_input": {"text": reply_text},
        }
        completed_run = subprocess.run(
            [sys.executable, str(hooks_directory / GATE_RELATIVE_PATH)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            cwd=hooks_directory,
            env=environment,
        )
    stderr_lines = completed_run.stderr.strip().splitlines()
    first_stderr_line = (
        stderr_lines[0][:FIRST_STDERR_LINE_LENGTH] if stderr_lines else ""
    )
    return completed_run.returncode, first_stderr_line


def configurations(
    baseline_hooks_directory: Path | None,
) -> list[tuple[str, Path, dict[str, str]]]:
    all_configurations = [
        (SWITCHES_UNSET_CONFIGURATION, REPO_HOOKS_DIRECTORY, {}),
        (SWITCHES_ON_CONFIGURATION, REPO_HOOKS_DIRECTORY, SWITCHES_ON),
    ]
    if baseline_hooks_directory is None:
        return all_configurations
    return [(BASELINE_CONFIGURATION, baseline_hooks_directory, {}), *all_configurations]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-hooks-dir", type=Path)
    arguments = parser.parse_args()
    all_failed_runs = []
    total_runs = 0
    for each_case_name, each_reply, each_expected_exit_codes in CASES:
        for (
            each_configuration_name,
            each_hooks_directory,
            each_switches,
        ) in configurations(arguments.baseline_hooks_dir):
            exit_code, first_stderr_line = run_gate(
                each_hooks_directory, each_reply, each_switches
            )
            expected_exit_code = each_expected_exit_codes[each_configuration_name]
            verdict = "PASS" if exit_code == expected_exit_code else "FAIL"
            total_runs += 1
            if verdict == "FAIL":
                all_failed_runs.append(f"{each_case_name} | {each_configuration_name}")
            print(
                f"{verdict} | {each_case_name} | {each_configuration_name} | "
                f"exit={exit_code} expected={expected_exit_code} | {first_stderr_line}"
            )
    print(f"{total_runs - len(all_failed_runs)}/{total_runs} runs passed")
    return 1 if all_failed_runs else 0


if __name__ == "__main__":
    raise SystemExit(main())
