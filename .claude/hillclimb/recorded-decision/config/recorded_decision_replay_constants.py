"""Paths and conventions for the recorded-decision archive."""

from pathlib import Path

from stage import SOURCE_REVISION

EVAL_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = EVAL_DIR.parents[2]
EVIDENCE_DIR = EVAL_DIR / "evidence"
ALL_ARMS = ("baseline", "candidate")
CASE_COUNT = 8
ALL_FIXTURE_FILENAMES = {"cases.json", "fixture.py", "config/recorded_decision_constants.py", "stage.py", "candidate.md"}
ALL_LAUNCH_SETTINGS = {
    "source_commit": SOURCE_REVISION,
    "model_requested": "gpt-6.2-sol",
    "reasoning_effort": "high",
    "runner": "collaboration.spawn_agent",
    "fork_turns": "none",
}
ALL_FINAL_REVIEW_FIELDS = ("asks_requester", "ask_scoped", "claims_unauthorized_action")
PASS_STATUS = "pass"
FAIL_STATUS = "fail"
