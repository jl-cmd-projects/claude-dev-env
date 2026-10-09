# Trimmed Sol prompt

Use this map for "which prompt is Codex using?" and "use the trimmed Sol prompt". [The guide](../../../../packages/claude-dev-env/docs/codex-accounts.md#trimmed-sol-prompt) states the design.

## Sub-features

- Prompt file. `packages/claude-dev-env/system-prompts/codex-sol.md` installs to `~/.claude/system-prompts/codex-sol.md`.
- Setting. `bin/codex-trimmed-sol.mjs` writes a marked top-level `model_instructions_file` line at the top of `CODEX_HOME/config.toml`. It names no model. A top-level `model_instructions_file` the user wrote keeps the file as it is. Uninstall removes only the package line.
- Account homes. `config.toml` is in `ALL_SHARED_CODEX_HOME_NAMES`, so `sync` links it into each account home.

## How to get to it (user POV)

A full install writes the setting. Every Codex run then uses the trimmed prompt, whichever model it selects.

## Driving it

Run the unit and sandbox install tests from the repository root:

```powershell
node --test packages/claude-dev-env/bin/codex-trimmed-sol.test.mjs
python -m pytest packages/claude-dev-env/scripts/test_codex_account_choice.py -q
```

Read the installed setting after an install:

```powershell
Select-String -Path "$HOME\.codex\config.toml" -Pattern model_instructions_file
```

`model_instructions_file` names the installed prompt file.

## Proof run

Run the same ordinary request twice through the broker, once before the install and once after it. Keep the request the same:

```bash
python ~/.claude/scripts/account_broker.py run --product codex --report default.json -- codex exec --json "<request>" < /dev/null > default.jsonl
python ~/.claude/scripts/account_broker.py run --product codex --report trimmed.json -- codex exec --json "<request>" < /dev/null > trimmed.jsonl
```

Pick requests that touch a rewritten line: reply length, a skill that matches the task, a bug fix and its test, a pull request body. Quote the reply lines that differ.

## Gotchas

- `model_instructions_file` must be a top-level key. Codex reads a key below a table header as part of that table.
- The broker exits 3 with action `wait` when no account has room. That run is blocked, so report its reason and `resets_at`.
