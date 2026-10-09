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

# Flag non-breaking findings

**When:** Writing a local gate or changing a check's severity.

Give every check ID a breaking or smell severity row; style and structure findings are smells. Fail the gate and stop for a bug, secret, broken test, syntax error, or instruction file that cannot load. Record a smell in `.claude/followups/smells.jsonl`, proceed, and fix it later in one combined follow-up pull request per parent pull request, whose body names the parent as `Follow-up to #N`; ledger failure leaves the gate decision unchanged. Treat an unclassified check as breaking.

**Enforcement:** none.

**Full text:** [guide](../docs/rule-guides/flag-non-breaking-findings.md). Read it when adding a check.
