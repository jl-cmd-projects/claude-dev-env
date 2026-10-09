---
paths:
  - "**/test_*.py"
  - "**/*_test.py"
  - "**/*.test.*"
  - "**/*.spec.*"
  - "**/conftest.py"
  - "**/tests/**"
  - "**/scripts/**"
---

# Falsify before green

**When:** A new test, probe, sweep, mutation check, or measurement script first reports green.

Apply a named break that the same check must catch, and run a passing control beside it on the same command. Record the break, its failing output, and the control before counting the restored green as evidence. If the check stays green under its break, fix its reach; a probe needs a trip input, a sweep needs a planted violation in its claimed file set, and a writer assertion needs a disabled production writer.

**Enforcement:** none.

**Full text:** [guide](../docs/rule-guides/falsify-before-green.md). Read it when designing a break or reviewing a red record.
