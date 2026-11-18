"""Files, protocol values and generated reader for the compact-session trials."""

import re

SESSION = ".session"
LOADED_RECEIPT_SUFFIX = ".loaded"
PREPARE = "prepare"
ASSESS = "assess"
BASELINE_ARM = "baseline"
CANDIDATE_ARM = "candidate"
NAMED_DELIVERY = "named"
STARTUP_DELIVERY = "startup"
HOOK_TIMEOUT_SECONDS = 10
HOOK_PACKAGE = "packages/claude-dev-env/hooks"
HOOK = "session/compaction_recall_prompt.py"
ALL_HOOK_SOURCES = (
    HOOK,
    "session/compaction_trim.py",
    "session/compaction_user_messages.py",
    "hooks_constants/__init__.py",
    "hooks_constants/compaction_user_messages_constants.py",
    "hooks_constants/context_budget_constants.py",
    "hooks_constants/gate_fault.py",
    "hooks_constants/gate_fault_constants.py",
    "hooks_constants/hook_specific_output_keys.py",
    "hooks_constants/pre_tool_use_stdin.py",
    "hooks_constants/setup_project_paths_constants.py",
)
CONTEXT = "compact-context.txt"
SUMMARY = "summary.txt"
TRANSCRIPT = "rollout.jsonl"
READER = "read-user-turns.py"
STARTUP = "startup.txt"
STARTUP_RECEIPT = "startup.sha256"
NAMED_RECEIPT = "delivered.json"
INSTRUCTIONS = "AGENTS.md"
CLIPPED_TURNS = re.compile(
    r"^\[[1-9]\d* earlier messages left out to fit the budget\]$"
)
CLIPPED_TURN = re.compile(
    r"^#\d+ .* \[[1-9]\d* more characters left out\](?: \(overruled by #\d+\))?$"
)
READER_SOURCE = '''"""Read an inclusive range of user-authored turns from the adjacent fixture."""

import argparse
import json
import sys
from pathlib import Path


session = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(session / "hooks" / "session"))
from compaction_user_messages import typed_user_messages


cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument("first", type=int)
cli.add_argument("last", type=int, nargs="?")
args = cli.parse_args()
last = args.first if args.last is None else args.last
with (session / "rollout.jsonl").open(encoding="utf-8") as trace:
    turns = typed_user_messages(trace)
if not 1 <= args.first <= last <= len(turns):
    cli.error(f"Choose an inclusive range within turns 1 through {len(turns)}")
print(json.dumps([
    {"position": turn.position, "text": turn.text} for turn in turns[args.first - 1:last]
], ensure_ascii=False, indent=2))
'''
