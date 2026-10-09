---
paths:
  - "**/test_*.py"
  - "**/*_test.py"
  - "**/*.test.*"
  - "**/*.spec.*"
  - "**/conftest.py"
  - "**/tests/**"
---

# Testing standards

**When:** Write or review behavior tests.

Read [`TEST_QUALITY.md`](../docs/TEST_QUALITY.md) and give mocks every field the component reads, with valid values. Assert results from production data and code paths. Use red, green, refactor for fixes and new behavior; add prototype tests before a pull request goes ready, and ship a reproducing test with each fix. A production fix titled `fix` needs a changed Python or Node test that fails on base and passes on head.

**Enforcement:** `useless_test_checks.py` and `code_rules_test_assertions.py` catch weak assertions; `Fix test proof` checks fix tests.

**Full text:** [guide](../docs/rule-guides/testing.md). Read it for mock fields, test order, and fix proof details.
