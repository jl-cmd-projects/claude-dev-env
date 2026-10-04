---
paths:
  - "**/scripts/**"
  - "**/hooks/**"
  - "**/bin/**"
  - "**/ci/**"
  - "**/tools/**"
  - "**/skills/*/scripts/**"
  - "**/commands/**"
---

# Build needs a user

**When:** Before building a tool, script, hook, gate, skill, command, or workflow step.

Name its caller in this change, first-use date or event, and last manual use with frequency. Build only with all three answers; otherwise tell the owner in one line what the build is for and which answer is missing, then continue unaffected work. Search for an existing tool, size the build to first use, and turn a correction into a hook or lint only after it recurs.

**Enforcement:** `uncalled-new-file` checks new code under `scripts/`, `hooks/`, `bin/`, `ci/`, and `tools/` for a caller.

**Full text:** [`docs/rule-guides/build-needs-a-user.md`](../docs/rule-guides/build-needs-a-user.md). Read it when sizing a new check.
