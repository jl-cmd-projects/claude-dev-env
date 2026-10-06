# Trimmed Sol prompt

Use this map for "which prompt is Codex using?" and "use the trimmed Sol prompt". [The guide](../../../../packages/claude-dev-env/docs/codex-accounts.md#trimmed-sol-prompt) states the design.

## Sub-features

- Prompt file. `packages/claude-dev-env/system-prompts/codex-sol.md` installs to `~/.claude/system-prompts/codex-sol.md`.
- Profile. `bin/codex-trimmed-sol.mjs` writes `CODEX_HOME/trimmed-sol.config.toml` with `model` and `model_instructions_file`. A file without the package header stays as the user wrote it. Uninstall removes the package file.
- Account homes. `trimmed-sol.config.toml` is in `ALL_SHARED_CODEX_HOME_NAMES`, so `sync` links it into each account home.

## How to get to it (user POV)

A full install writes the profile. A Codex run passes `--profile trimmed-sol` to use it. A run without the flag uses the model's default prompt.

## Driving it

Run the unit and sandbox install tests from the repository root:

```powershell
node --test packages/claude-dev-env/bin/codex-trimmed-sol.test.mjs
python -m pytest packages/claude-dev-env/scripts/test_codex_account_choice.py -q
```

Read the installed setting after an install:

```powershell
Get-Content "$HOME\.codex\trimmed-sol.config.toml"
```

`model_instructions_file` names the installed prompt file.

## Proof run

Run the same ordinary request twice through the broker, once on the default prompt and once on the trimmed prompt. Keep the request the same and change only the flag:

```bash
python ~/.claude/scripts/account_broker.py run --product codex --report default.json -- codex exec --model gpt-6.1-sol --json "<request>" < /dev/null > default.jsonl
python ~/.claude/scripts/account_broker.py run --product codex --report trimmed.json -- codex exec --profile trimmed-sol --json "<request>" < /dev/null > trimmed.jsonl
```

Pick requests that touch a rewritten line: reply length, a skill that matches the task, a bug fix and its test, a pull request body. Quote the reply lines that differ.

## Gotchas

- Codex refuses `--profile trimmed-sol` while `config.toml` also holds a `[profiles.trimmed-sol]` table or `profile = "trimmed-sol"`.
- The broker exits 3 with action `wait` when no account has room. That run is blocked, so report its reason and `resets_at`.
