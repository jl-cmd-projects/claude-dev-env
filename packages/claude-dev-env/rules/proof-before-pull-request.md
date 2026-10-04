# Proof before a pull request

**When:** Before you open a pull request, in any project.

Run the changed thing the way its user runs it, and see the effect it exists to produce. Run the same scenario without the change first, and cover the case it should leave alone. For a hook, skill, rule, setting, prompt, or output style, spawn each test session through the account broker. Put each command, the quoted output, and the difference between the runs under a "Proof in practice" heading in the body. When you cannot prove it, leave the pull request unopened and tell the user what you could not run.

**Enforcement:** `hooks/blocking/pull_request_proof.py`, run by `pr_lifecycle_skill_gate.py`, denies a new pull request whose body has no "Proof in practice" section with a command in backticks.

**Full text:** [`docs/rule-guides/proof-before-pull-request.md`](../docs/rule-guides/proof-before-pull-request.md). Read it before you plan the proof run.
