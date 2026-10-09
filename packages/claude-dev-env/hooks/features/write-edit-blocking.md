# Write and Edit blocking

This family decides whether an agent's file mutation can run. It also warns about unsafe migration edits before the agent changes a file.

## Checks

- `blocking/pre_tool_use_dispatcher.py` combines hosted advisory output with its native description check and returns one permission decision.
- `advisory/migration_safety_advisor.py` warns when an Edit or MultiEdit adds an unsafe Django migration operation.
- `blocking/state_description_blocker.py` rejects historical or comparative prose in supported comments, docstrings, and Markdown.

## When it fires

- `blocking/pre_tool_use_dispatcher.py` runs on `PreToolUse`, matcher `Write|Edit|MultiEdit|apply_patch`, timeout `60` seconds in `hooks.json`.
- `advisory/migration_safety_advisor.py` runs inside that dispatcher on `PreToolUse`, matcher `Write|Edit|MultiEdit|apply_patch`, timeout `60` seconds. `ALL_HOSTED_HOOK_ENTRIES` selects `Edit` and `MultiEdit` for it.
- `blocking/state_description_blocker.py` runs through the dispatcher's native evaluator on `PreToolUse`, matcher `Write|Edit|MultiEdit|apply_patch`, timeout `60` seconds. Its evaluator checks `Write`, `Edit`, and `MultiEdit` payloads and skips `apply_patch`.

## Proving it

Preconditions:

- Run each command from the repository root with Python and pytest available. The tests use disposable paths where they need files.

- **Dispatcher decision.** Input is a clean Write payload. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_pre_tool_use_dispatcher.py -q`. The adjacent test checks that the dispatcher allows clean writes and carries denials from its checks.
- **Migration warning.** Input is an Edit containing `migrations.RemoveField`. Run `python -m pytest packages/claude-dev-env/hooks/advisory/test_migration_safety_advisor.py -q`. The adjacent test observes an allow decision with a migration warning.
- **Description gate.** Input is a Write containing historical prose in a Python comment. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_state_description_blocker.py -q`. The adjacent test observes a denial reason.

## Gotchas

- `ALL_HOSTED_HOOK_ENTRIES` lists only the nonblocking migration advisor. The dispatcher calls the description evaluator through its native hook table.
- The dispatcher runs hosted entries in roster order. A hosted advisory crash stays silent; a native blocking check can deny the write.
- `scripts/policy_lint/adapter_detectors.py` also loads `blocking/state_description_blocker.py`. Check that adapter when changing its evaluator.
- `bin/install.mjs` names folded and retired script paths so reinstall can remove stale registrations.
