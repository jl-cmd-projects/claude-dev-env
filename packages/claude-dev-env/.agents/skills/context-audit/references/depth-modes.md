# Triggers, depth modes, and caps

## Principle

Keep entry points thin and references thick. An entry file loads on a trigger the agent does not choose, so every line in it costs context on every run. A reference loads only when a link sends the agent there.

Content used on every invocation stays in the entry file. Moving it behind a link adds a file read to every run and saves nothing.

## Triggers

| Trigger | What loads the file |
|---|---|
| `session-start` | Root `CLAUDE.md`, `AGENTS.md`, `CLAUDE.local.md` and their `@` imports, rules without `paths`, skill descriptions in a project or installed skills folder, and saved SessionStart hook text. |
| `folder-enter` | Instruction files in a subfolder, and skill descriptions in a nested `.claude/skills` folder. |
| `path-match` | Rules whose frontmatter has `paths`. They load when the agent reads a matching file. |
| `skill-invoke` | A skill body. It loads when the skill runs. |
| `on-link` | Files under a skill folder other than `SKILL.md`, and markdown files reached through a relative link. Link depth counts hops from the first entry file. |
| `file-open` | A Python module docstring. The agent reads it when it opens the file. |

A skill with `disable-model-invocation: true` has no listing row. Skills under folders named `tests` or `fixtures`, or with `archive` in a folder name, are skipped.

## Depth modes

| Mode | Meaning |
|---|---|
| `empty` | One byte or less. |
| `carries` | Over the line cap, or over the cap times 120 bytes. |
| `points` | Within the cap, with relative links out. |
| `lean` | Within the cap, with no links out. |
| `reference` | On-link depth. No cap applies. |

## Caps

| Kind | Cap |
|---|---|
| Root instructions and their imports, saved hook text | 20 lines |
| Nested instructions and their imports | 12 lines |
| Rule | 20 lines |
| Skill body | 200 lines |
| Module docstring | 15 lines |
| Skill description | 500 characters. The listing truncates at 1,536. |

The caps live in `scripts/context_audit_constants/config/constants.py`.

## Row fields

Each line of the rows file is one JSON object.

| Field | Meaning |
|---|---|
| `path` | Path relative to the repository root, or the hook text file name. |
| `kind` | `instructions`, `import`, `rule`, `skill-description`, `skill-body`, `skill-reference`, `hook-text`, `linked-doc`, or `docstring`. |
| `loader` | What reads the file. |
| `trigger` | One trigger from the table above. |
| `bytes`, `lines` | Size of the text the agent receives. |
| `est_tokens` | Bytes divided by 4. An estimate. |
| `links_out` | Relative markdown links that resolve inside the repository. |
| `depth_mode` | One mode from the table above. |
| `cap` | The cap that applies, or null. |
| `note` | Extra context, such as link depth. |

## Splitting a long file

1. List the steps every run uses. Keep them in the entry file.
2. Move each detail that only some runs need into its own file under `references/`.
3. Link each moved file from the entry file with one line that says when to read it.
4. Rerun the audit and confirm the entry file is `points` or `lean`.
