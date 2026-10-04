---
paths:
  - "**/rules/*.md"
---

# Rules prose names only hooks that run

**When:** Describing a hook or retiring a gate.

Verify the module and its hook registration or dispatcher roster before claiming it runs; describe a retired hook in past tense or name the check that carries its work now. When retiring a gate, remove the forced agent calls, tokens, extra steps, thresholds, audit rubrics, and review prompts it required across every instruction lane. Add a retired hook path to the installer roster when deleting its module.

**Enforcement:** `retired-hook-prose` in `scripts/policy_lint/registry.py` checks instruction Markdown, including `rules/` and `docs/`; the detour sweep is manual.

**Full text:** [`docs/rule-guides/retired-hook-prose.md`](../docs/rule-guides/retired-hook-prose.md). Read it when tracing a hook's current path or removing its gate.
