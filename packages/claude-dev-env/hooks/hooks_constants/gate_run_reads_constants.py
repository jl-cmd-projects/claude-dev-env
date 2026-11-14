"""Constants for the read deadlines of one pull request lifecycle gate run."""

PROOF_AND_LOOK_READS_SECONDS = 12
FOLLOWUP_READS_SECONDS = 8
EVAL_WRITE_SCAN_SECONDS = 5
KILL_GRACE_SECONDS = 1
WINDOWS_TREE_KILL_SECONDS = 0.5
ALL_WINDOWS_TREE_KILL_WORDS = ("taskkill", "/T", "/F", "/PID")
KERNEL32_LIBRARY_NAME = "kernel32"
PROCESS_HANDLE_ATTRIBUTE = "_handle"
STOPPED_JOB_EXIT_CODE = 1
TERMINATE_JOB_CALL = "TerminateJobObject"
CLOSE_HANDLE_CALL = "CloseHandle"
MOST_CUT_READS_PER_RUN = 2
STARTUP_AND_OUTPUT_MARGIN_SECONDS = 5
READS_RAN_OUT_SENTENCE = (
    " The gate's git and GitHub reads ran out of time on this run, so a second run may pass."
)
