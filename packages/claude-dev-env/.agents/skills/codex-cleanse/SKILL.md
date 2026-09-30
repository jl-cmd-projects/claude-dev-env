---
name: codex-cleanse
description: Preview or archive local Codex sessions after seven days without activity. Use for an on-demand session cleanup or a local scheduled archive run across a selected Codex home.
---

# Codex cleanse

Run `scripts/cleanse.mjs` with Node.js from this skill directory. Select the account with `--codex-home <absolute path>`. Without that flag, the command uses `CODEX_HOME`, then the current user's `.codex` directory. Use `--codex-path <absolute executable path>` when Codex is outside the supported native install locations.

Preview first:

```text
node scripts/cleanse.mjs --stdio --codex-home <absolute path>
```

Archive the eligible sessions after reviewing the preview:

```text
node scripts/cleanse.mjs --stdio --codex-home <absolute path> --apply
```

The default cutoff is seven days. `--inactive-days <number>` changes it. When the local Codex app's task listing is available, repeat `--exclude-thread-id <UUID>` for the current task and each active desktop task. Run the command on demand when the user requests archiving. The command starts a separate local app-server process and cannot see other clients' runtime status. It checks the stored activity time and rollout file modification time before each archive request.

The command reads the selected home's state database through `thread/list`, including all local source kinds. It re-reads each candidate, checks its rollout file modification time and unarchived descendants, and calls `thread/archive` for eligible leaves before parents. It confirms archived IDs through a final archived listing. It writes one JSON report to stdout and progress to stderr. A failed archive or readback exits with a nonzero status.

Run the archive task on the local machine with the app and selected account available. A cloud task cannot read this machine's Codex home. Codex session archiving leaves managed worktrees in place. The desktop setting at Settings > Worktrees > General > Automatically delete old worktrees controls separate worktree cleanup by retained count.
