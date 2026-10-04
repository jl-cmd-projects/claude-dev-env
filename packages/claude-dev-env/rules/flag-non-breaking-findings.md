---
paths:
  - "**/hooks/**"
  - "**/policy_lint/**"
  - "**/repository_checks/**"
  - "**/.pre-commit-config.yaml"
  - "**/.githooks/**"
  - "**/.husky/**"
  - "**/.github/workflows/**"
---
# Flag Non-Breaking Findings

A gate fails on a breaking finding and records a non-breaking finding for later repair. Each check declares its category. A defect, secret, broken test, syntax error, or instruction that fails to load is breaking; a style or structural preference is recorded without blocking.

When this rule applies, read the full text guide before acting.

**Full text:** [`docs/rule-guides/flag-non-breaking-findings.md`](../docs/rule-guides/flag-non-breaking-findings.md)
