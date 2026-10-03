---
paths:
  - "**/*.workflow.js"
---

# Workflow substitution slots

**When:** Write a `.workflow.js` agent-prompt template with values filled per call or iteration.

Mark each changing value with angle brackets, including loop indices in paths or output keys such as `cand_<i>`.

**Enforcement:** `workflow-substitution` in the staged policy lint. `contrast-framing` checks authored Markdown.

**Full text:** [`docs/rule-guides/workflow-substitution-slots.md`](../docs/rule-guides/workflow-substitution-slots.md). Read it when a loop builds a path or output key.
