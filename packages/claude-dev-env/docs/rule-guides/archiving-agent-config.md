# Archiving a rule, skill, agent, or command

Full text behind [`rules/archiving-agent-config.md`](../../rules/archiving-agent-config.md), which loads in sessions as the short form.

## Evidence of use

Enforcement in this package often has a different name from the file that describes it. The script, lint identifier, and running check show whether a capability remains in service. A rule can have no mentions of its slug and still have a checker under another name.

`CHANGELOG.md` records history. The `README.md` inventory table lists what ships. `bin/ever-shipped-skills.mjs` retains archived names on purpose. Mentions in these three files add no evidence of current use.

This package installs into other repositories. A path absent from this tree can resolve in the host repository where the rule or skill runs. The path's intended location determines whether it is stale.

## Archive layout

`rules-archived/` sits beside `rules/`, and `.agents/skills-archived/` sits beside `.agents/skills/`. The installer copies a content directory whole, so an archive inside a live directory would ship. `CONTENT_DIRECTORIES` in `bin/install.mjs` omits archive siblings, and skill installation enumerates `.agents/skills` alone.

The archive manifest records why each file left service, the `git mv` that restores it, and every companion edit a restore must undo. The sibling archive keeps the file available for a reverse move.

## Exempt files

The "Never archived" section of `rules-archived/ARCHIVE-MANIFEST.md` names files that stay in service. `rules/correction-lens.md` is listed there. Editing an exempt file to sharpen it remains ordinary work.

## Skill names and tests

The prune computes retired skill names as every name in `bin/ever-shipped-skills.mjs` minus the names installed now. The installer uses that set to move stale copies out of a host's agents home. `scripts/active_capability_references.py` uses the same registry to report leftover mentions of an archived name.

The node test command globs `.agents/skills/**/*.test.mjs`. Tests under a renamed archived skill directory leave that run without failing, so the test count shows whether coverage still runs.

## Sibling rules

| Rule | Role |
|---|---|
| [`retired-hook-prose.md`](../../rules/retired-hook-prose.md) | Hook prose names checks that still run |
| [`doc-inventory-integrity.md`](../../rules/doc-inventory-integrity.md) | Inventory tables reflect what ships |
