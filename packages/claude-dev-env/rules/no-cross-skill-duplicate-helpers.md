---
paths: "**/skills/*/scripts/**/*.py"
---

# Cross-skill duplicate helpers

**When:** Write a top-level Python helper in a skill `scripts/` directory.

Within one skill, extract a shared module and import it at both call sites. Across skill folders, copy a small self-contained helper when independent installation needs it, then confirm the advisory names the source. For a large or behavior-bearing body, ask the user to choose an intentional copy with drift risk or a dependency that survives independent install.

**Enforcement:** `code_rules_duplicate_body.py` blocks sibling-module copies and emits cross-skill advisories through `code_rules_enforcer.py`; the agent judges copy size.

**Full text:** [guide](../docs/rule-guides/no-cross-skill-duplicate-helpers.md). Read it when judging copy size or dependency ownership.
