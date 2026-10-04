---
paths:
  - "**/test_*.py"
  - "**/*_test.py"
  - "**/*.test.*"
  - "**/*.spec.*"
  - "**/conftest.py"
  - "**/tests/**"
---
# Anti-Corollary Tests

When adding or changing tests, keep cases that distinguish working behavior from a dead mechanism. Test canonical reduction once instead of every spelling pair. Name the degenerate result and use an input that makes it fail. Keep a paired control when a new check is meant to prove a break.

When this rule applies, read the full text guide before acting.

**Full text:** [`docs/rule-guides/anti-corollary-tests.md`](../docs/rule-guides/anti-corollary-tests.md)
