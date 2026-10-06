# Write and Edit blocking

This family decides whether an agent's file mutation can run. It also warns about broad refactors and unsafe migration edits before the agent changes a file.

## Checks

- `blocking/pre_tool_use_dispatcher.py` combines hosted advisory output with its native description check and returns one permission decision.
- `advisory/refactor_guard.py` warns when an Edit or MultiEdit appears to rename code beyond the current change.
- `advisory/migration_safety_advisor.py` warns when an Edit or MultiEdit adds an unsafe Django migration operation.
- `blocking/state_description_blocker.py` rejects historical or comparative prose in supported comments, docstrings, and Markdown.
- `blocking/context_budget_blocker.py` rejects a write that grows a skill entry, `AGENTS.md`, `CLAUDE.md`, or rule file past its context budget.

## When it fires

- `blocking/pre_tool_use_dispatcher.py` runs on `PreToolUse`, matcher `Write|Edit|MultiEdit|apply_patch`, timeout `60` seconds in `hooks.json`.
- `advisory/refactor_guard.py` and `advisory/migration_safety_advisor.py` run inside that dispatcher on `PreToolUse`, matcher `Write|Edit|MultiEdit|apply_patch`, timeout `60` seconds. `ALL_HOSTED_HOOK_ENTRIES` selects `Edit` and `MultiEdit` for each.
- `blocking/state_description_blocker.py` runs through the dispatcher's native evaluator on `PreToolUse`, matcher `Write|Edit|MultiEdit|apply_patch`, timeout `60` seconds. Its evaluator checks `Write`, `Edit`, and `MultiEdit` payloads and skips `apply_patch`.
- `blocking/context_budget_blocker.py` runs inside that dispatcher as a blocking hosted entry on `PreToolUse`, matcher `Write|Edit|MultiEdit|apply_patch`, timeout `60` seconds. It reads `.claude/context-budget.json` from the edited file's own repository.

## Proving it

Preconditions:

- Run each command from the repository root with Python and pytest available. The tests use disposable paths where they need files.

- **Dispatcher decision.** Input is a clean Write payload. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_pre_tool_use_dispatcher.py -q`. The adjacent test checks that the dispatcher allows clean writes and carries denials from its checks.
- **Refactor warning.** Input is a MultiEdit whose second edit renames a function. Run `python -m pytest packages/claude-dev-env/hooks/advisory/test_refactor_guard.py -q`. The adjacent test reports both function names in the warning.
- **Migration warning.** Input is an Edit containing `migrations.RemoveField`. Run `python -m pytest packages/claude-dev-env/hooks/advisory/test_migration_safety_advisor.py -q`. The adjacent test observes an allow decision with a migration warning.
- **Context budget gate.** Input is a Write of the orchestrator skill at commit `3f2c3ef`, then at `98f45b1`. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_context_budget_blocker.py -q`. The adjacent test observes a denial naming "Oversee delegated work" for the first and an allow for the second.
- **Description gate.** Input is a Write containing historical prose in a Python comment. Run `python -m pytest packages/claude-dev-env/hooks/blocking/test_state_description_blocker.py -q`. The adjacent test observes a denial reason.

## Gotchas

- `ALL_HOSTED_HOOK_ENTRIES` lists the two nonblocking advisors and the blocking context budget gate. The dispatcher calls the description evaluator through its native hook table.
- The context budget gate denies only what an edit adds. A repository with no policy file uses built-in kinds and treats the file's current text as its baseline entry, so a file under its line limit may grow to the limit and a file over it may only shrink. The CI ratchet runs in `scripts/policy_lint/adapter_context_budget.py`, never in the hook. See the [context budget reference](../../.agents/skills/build-eval/reference/context-budget.md).
- The dispatcher runs hosted entries in roster order. A hosted advisory crash stays silent; a native blocking check can deny the write.
- `scripts/policy_lint/adapter_detectors.py` also loads `blocking/state_description_blocker.py`. Check that adapter when changing its evaluator.
- `bin/install.mjs` names folded and retired script paths so reinstall can remove stale registrations.
