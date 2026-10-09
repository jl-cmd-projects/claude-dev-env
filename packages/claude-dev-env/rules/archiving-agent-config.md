---
paths:
  - "**/rules/**"
  - "**/rules-archived/**"
  - "**/.agents/skills/**"
  - "**/skills-archived/**"
  - "**/agents/**"
  - "**/commands/**"
  - "**/ever-shipped-skills.mjs"
---

# Archiving a rule, skill, agent, or command

**When:** Before archiving configuration.

Trace checks and callers; `CHANGELOG.md`, `README.md`, shipped-skills registry, and host paths prove neither use nor disuse. Read `rules-archived/ARCHIVE-MANIFEST.md`; skip and report exemptions, then continue. Move unused files with `git mv` into sibling archives; record the reason, restore command, and companion edits. Retain skill names in `bin/ever-shipped-skills.mjs` and check tests lost when a skill directory moves.

**Enforcement:** none.

**Full text:** [guide](../docs/rule-guides/archiving-agent-config.md). Read it before moving or restoring.
