---
name: context-audit
description: Inventory every file an agent loads from a repository checkout, with size, trigger, and depth mode, then list what to clean up. Use when the user asks to audit the context in a repository, measure instruction or skill load, or find bloated CLAUDE.md, AGENTS.md, rules, or skills.
---

# Context audit

Use this skill when the user says "audit the context in <repository>" or asks what an agent loads from a checkout.

## Run

```
python "${CLAUDE_SKILL_DIR}/scripts/context_audit.py" <repository-root> --rows <scratch>/rows.jsonl
```

Add these options when they apply:

| Option | When |
|---|---|
| `--rules-dir <path>` | The repository ships a folder that installs as the user rules folder. |
| `--skills-dir <path>` | The repository ships a folder that installs as the user skills folder. |
| `--session-start-text <file>` | A SessionStart hook prints text. Save that text to a file first. Repeat for each hook. |

Paths for `--rules-dir` and `--skills-dir` are relative to the repository root. The script runs no hook command.

## Read the output

The report opens with the startup load in lines and estimated tokens, then a table by trigger. The cleanup list follows in three sections.

1. **Carries depth over cap.** An entry file holds depth that belongs in a reference. Move that depth into a linked file and leave a pointer.
2. **Empty instruction stubs.** An instruction file or rule with no content. Delete it unless a tool needs the file to exist.
3. **Long skills to split.** A skill body over 200 lines. Keep the steps every run uses in `SKILL.md` and move the rest into `references/`.

Content used on every invocation stays in the entry file. Moving it behind a link adds a read to every run.

Hand the user the cleanup list with paths, line counts, and caps. The rows file holds every row for follow-up questions.

[references/depth-modes.md](references/depth-modes.md) has the triggers, the depth modes, the caps table, and the row fields.

## Layout

| File | Purpose |
|---|---|
| `scripts/context_audit.py` | Command line entry point. Prints the report and writes the rows file. |
| `scripts/context_inventory.py` | Walks the checkout and records one row per loaded file. |
| `scripts/context_sources.py` | Reads files, parses frontmatter, follows links and imports, and measures rows. |
| `scripts/context_report.py` | Formats the summary, the trigger table, and the cleanup list. |
| `scripts/context_audit_constants/config/constants.py` | Caps, patterns, labels, and report templates. |
