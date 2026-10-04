---
paths:
  - "**/scripts/**"
  - "**/hooks/**"
  - "**/bin/**"
  - "**/ci/**"
  - "**/tools/**"
  - "**/skills/*/scripts/**"
  - "**/package.json"
  - "**/pyproject.toml"
  - "**/requirements*.txt"
---

# Prefer existing tools

**When:** Before building a tool, check, script, or library.

Search local and shared code, then open-source options. Stop at first fit; build if neither fits. Choose an external option with an active security process, no open critical advisory, field reputation, broad use, and a release or commit within a year; add missing rules in its configuration without a wrapper. Report its name, link, license, and one use count; for custom code, name rejected candidates and reasons.

**Enforcement:** none, the agent applies it.

**Full text:** [`docs/rule-guides/prefer-existing-tools.md`](../docs/rule-guides/prefer-existing-tools.md). Read it when comparing candidates.
