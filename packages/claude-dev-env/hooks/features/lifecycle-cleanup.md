# Lifecycle cleanup

This family runs nested checkout hooks, refreshes a worktree base, and clears stale session files. Its cleanup paths let the agent start and end a session without leftover hook state.

## Checks

- `lifecycle/nested_project_hooks.py` runs hook registrations from checkouts nested one level below a session directory.
- `lifecycle/enter_worktree_origin_prefetch.py` fetches the default branch before a fresh worktree is created.
- `lifecycle/session_end_cleanup.py` removes old context cache files, temporary files, and transcript backups at session end.
- `session/plugin_data_dir_cleanup.py` removes empty plugin data directories at session start.
- `session/session_env_cleanup.py` clears the current Windows session environment directory and stale siblings at session start.
- `session/session_edit_tracker_cleanup.py` clears this session's edit tracker on a fresh start or session end.

## When it fires

- `lifecycle/nested_project_hooks.py` runs on `PreToolUse` matcher `*` at `120` seconds and `SessionStart` matcher empty at `1800` seconds in `hooks.json`.
- `lifecycle/enter_worktree_origin_prefetch.py` runs on `PreToolUse`, matcher `EnterWorktree`, timeout `25` seconds in `hooks.json`.
- `lifecycle/session_end_cleanup.py` runs on `SessionEnd`, matcher empty, timeout `3` seconds in `hooks.json`.
- `session/plugin_data_dir_cleanup.py` and `session/session_env_cleanup.py` run on `SessionStart`, matcher empty, timeout `10` seconds each in `hooks.json`.
- `session/session_edit_tracker_cleanup.py` runs on `SessionStart`, matcher empty, timeout `10` seconds and `SessionEnd`, matcher empty, timeout `3` seconds in `hooks.json`.

## Proving it

Preconditions:

- Run each command from the repository root with Python and pytest available. The tests and direct cache probe use disposable directories.

- **Nested checkout hooks.** Input is a session started above a child checkout with its own hooks. Run `python -m pytest packages/claude-dev-env/hooks/lifecycle/test_nested_project_hooks.py -q`. The adjacent test observes the child hook running in its checkout.
- **Worktree fetch.** Input is an `EnterWorktree` call without a path. Run `python -m pytest packages/claude-dev-env/hooks/lifecycle/test_enter_worktree_origin_prefetch.py -q`. The adjacent test observes a fetch attempt and a zero exit even when a remote is absent.
- **Session-end cache.** Input is an aged `claude-ctx-` cache file in a disposable directory. Run `python -c 'import os, runpy, tempfile; from pathlib import Path; directory=tempfile.TemporaryDirectory(); root=Path(directory.name); entry=root/"claude-ctx-old.json"; entry.write_text("{}"); os.utime(entry,(0,0)); module=runpy.run_path("packages/claude-dev-env/hooks/lifecycle/session_end_cleanup.py"); module["purge_old_entries"](str(root),7); assert not entry.exists(); directory.cleanup(); print("stale cache entry removed")'`. The command prints `stale cache entry removed`. This script has no adjacent behavior test.
- **Plugin data cleanup.** Input is an empty plugin data directory. Run `python -m pytest packages/claude-dev-env/hooks/session/test_plugin_data_dir_cleanup.py -q`. The adjacent test observes its removal and preserves directories with files.
- **Session environment cleanup.** Input is a current Windows session environment directory or an aged sibling. Run `python -m pytest packages/claude-dev-env/hooks/session/test_session_env_cleanup.py -q`. The adjacent test observes removal while recent siblings remain.
- **Edit tracker cleanup.** Input is a fresh SessionStart or SessionEnd payload. Run `python -m pytest packages/claude-dev-env/hooks/session/test_session_edit_tracker_cleanup.py -q`. The adjacent test observes removal for that session and preservation on resume.

## Gotchas

- The nested checkout runner forwards child denials and asks. It drops child allow decisions so a child cannot widen permission.
- Worktree prefetch applies to fresh creation and exits zero after a failed fetch.
- Session-end cleanup has no adjacent behavior test. Its direct probe calls `purge_old_entries` with an isolated directory.
- The session edit tracker survives a compact or resume. Cleanup targets the current session only.
