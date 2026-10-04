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
# Falsify Before Green

Before a new test, probe, sweep, mutation check, or measurement counts as evidence, make that same check fail on a named deliberate break while a paired control passes. Restore the code and run it green. A green check that never detected its target break has no evidentiary value.

When this rule applies, read the full text guide before acting.

**Full text:** [`docs/rule-guides/falsify-before-green.md`](../docs/rule-guides/falsify-before-green.md)
