---
paths:
  - "**/test_*.py"
  - "**/*_test.py"
  - "**/*.test.*"
  - "**/*.spec.*"
  - "**/conftest.py"
  - "**/tests/**"
---

# Anti-corollary tests

**When:** Add or change a test.

Before keeping a test, name one code change it would catch; replace a case that catches none. Skip spelling cross products after proving canonicalization once; compare a few discriminating cases. Exercise the production path with a non-default expected result so a dead implementation cannot pass. Test policy compliance on governed surfaces; in an audit, name a mutation and record how many tests it fails.

**Enforcement:** none, the agent applies it.

**Full text:** [`docs/rule-guides/anti-corollary-tests.md`](../docs/rule-guides/anti-corollary-tests.md). Read it when choosing cases or auditing mutation evidence.
