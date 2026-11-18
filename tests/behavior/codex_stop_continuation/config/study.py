"""Fixture paths and settings for the matched Stop continuation study."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[2]
DEFAULT_RECEIVER = REPO_ROOT / "tests/codex_outcomes"
MODEL = "gpt-6.2-sol"
EFFORT = "high"
MAX_SECONDS = 180
PINNED = "36fc2586c1d849ac4d4852117f3cbbde03c20361"
STOP_HOOK = Path("packages/claude-dev-env/hooks/blocking/open_tasks_stop_gate.py")
BASELINE_ARM = "baseline"
CANDIDATE_ARM = "candidate"
REPEATED_CANDIDATE_ARM = "candidate_repeated"
ALL_ARMS = (BASELINE_ARM, CANDIDATE_ARM)
DEFAULT_REPEATS = 2
JSON_INDENT = 2
TIMING_PRECISION = 2
MILLISECONDS_PER_SECOND = 1000
PROBE_TIMEOUT_SECONDS = 12
BLOCK_EXIT = 2
CODEX_DIRECTORY = ".codex"
CLAUDE_DIRECTORY = ".claude"
CLAUDE_HOME_ENVIRONMENT = "CLAUDE_CONFIG_DIR"
NO_BYTECODE_ENVIRONMENT = "PYTHONDONTWRITEBYTECODE"
NEWLINE = "\n"
