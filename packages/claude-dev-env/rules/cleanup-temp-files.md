# Clean up temporary files

**When:** Creating scratch files, debug dumps, or one-off helpers during a task.

Prefer memory to scratch files and track any temporary files you create. At completion, remove those files and leave user-requested files in place. Files under the OS temporary root or `$CLAUDE_JOB_DIR` need no explicit removal; a parent handles child-agent scratch. Use the permitted removal form.

**Enforcement:** none, the agent applies it.

**Full text:** [`docs/rule-guides/cleanup-temp-files.md`](../docs/rule-guides/cleanup-temp-files.md). Read it to classify a file or choose cleanup.
