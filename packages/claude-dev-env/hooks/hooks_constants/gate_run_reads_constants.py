"""Constants for the read deadlines of one pull request lifecycle gate run."""

PROOF_AND_LOOK_READS_SECONDS = 12
FOLLOWUP_READS_SECONDS = 8
KILL_GRACE_SECONDS = 1
MOST_CUT_READS_PER_RUN = 2
STARTUP_AND_SCAN_MARGIN_SECONDS = 5
READS_RAN_OUT_SENTENCE = (
    " The gate's git and GitHub reads ran out of time on this run, so a second run may pass."
)
