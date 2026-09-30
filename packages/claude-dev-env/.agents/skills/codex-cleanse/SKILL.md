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

The command lists indexed sessions through `thread/list` and discovers other session IDs from rollout filenames under the selected home's `sessions` directory.
It reads their metadata through `thread/read` without opening conversation content.
It re-reads each candidate, checks its activity time, rollout file modification time, exclusions, and unarchived descendants, then calls `thread/archive` for eligible leaves before parents.
It confirms archived IDs through a final archived listing or a native read of the archived path for sessions omitted from that listing.
It writes one JSON report to stdout and progress to stderr.
Zero-byte rollout files count as `emptyRollout` skips because the native API cannot read their metadata.
Discovery failures stop archive writes and exit with a nonzero status.
An archive candidate failure stops later archive requests. Earlier requests still receive readback.
Archive and readback failures remain in the report and produce a nonzero exit status.

After a successful apply run archives sessions, refresh the active task exclusions and run again. Stop when a successful run reports zero archives.

Run the archive task on the local machine with the app and selected account available. A cloud task cannot read this machine's Codex home. Codex session archiving leaves managed worktrees in place. The desktop setting at Settings > Worktrees > General > Automatically delete old worktrees controls separate worktree cleanup by retained count.
