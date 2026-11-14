import json
import re
from pathlib import Path

from hooks_constants import followup_pr_dedupe_constants as constants
from hooks_constants.gate_run_reads_constants import (
    FOLLOWUP_READS_SECONDS,
    KILL_GRACE_SECONDS,
    MOST_CUT_READS_PER_RUN,
    PROOF_AND_LOOK_READS_SECONDS,
    STARTUP_AND_SCAN_MARGIN_SECONDS,
)

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
GATE_COMMAND_SUFFIX = "hooks/blocking/pr_lifecycle_" + "skill_gate.py"


def _registered_gate_timeout_seconds() -> int:
    all_registration_fields = json.loads((HOOKS_DIRECTORY / "hooks.json").read_text(encoding="utf-8"))
    all_timeouts = [
        each_hook["timeout"]
        for each_group in all_registration_fields["hooks"]["PreToolUse"]
        for each_hook in each_group["hooks"]
        if each_hook.get("command", "").endswith(GATE_COMMAND_SUFFIX)
    ]
    assert len(all_timeouts) == 1
    return all_timeouts[0]


def test_parent_pattern_reads_both_spellings_and_stops_at_the_number() -> None:
    assert re.search(constants.FOLLOWUP_PARENT_PATTERN, "followup to #12", re.IGNORECASE)
    assert re.search(constants.FOLLOWUP_PARENT_PATTERN, "Follow-up to #1731", re.IGNORECASE).group(1) == "1731"


def test_both_followup_reads_should_fit_inside_their_reserved_slice() -> None:
    assert constants.READ_TIMEOUT_SECONDS * 2 <= FOLLOWUP_READS_SECONDS


def test_registered_timeout_should_outlast_every_read_deadline_and_kill_grace() -> None:
    last_read_ends_at = (
        PROOF_AND_LOOK_READS_SECONDS
        + FOLLOWUP_READS_SECONDS
        + KILL_GRACE_SECONDS * MOST_CUT_READS_PER_RUN
    )
    assert _registered_gate_timeout_seconds() >= last_read_ends_at + STARTUP_AND_SCAN_MARGIN_SECONDS
