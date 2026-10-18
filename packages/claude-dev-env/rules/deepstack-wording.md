---
paths:
  - "**/*.md"
  - "**/commands/**"
---

# DeepStack wording

**When:** Writing a deepened task, a worker prompt, or a line that names the three DeepStack lines.

Use these labels: `SCOPE (role):`, `EXAMPLES (illustration only):`, and `ZOOM-IN BLOCKER:`. Put `CDE_DEEPEN:v1` on line 1. Say "the user".

**Enforcement:** `hooks/session/deepen_first_prompt.py` is the gate. This rule cites that gate.

**Full text:** [guide](../docs/rule-guides/deepstack-wording.md). Read it when you write the three lines.
