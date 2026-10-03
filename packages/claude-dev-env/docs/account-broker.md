# Account broker

`account_broker.py` reads the Claude and Codex account rosters, checks each account's session and weekly usage, and chooses an account with room. It does not select a model or sleep. A Codex decision names the `normal` or `luna` tier for the caller.

Claude's main home is `~/.claude`. Its `claude-chain.json` file contains a `chain` list; each entry's `credentials_path` field identifies the credentials file whose parent is that account's home folder. The optional `extra-profiles.json` file in the main home lists additional profile names. Codex uses its configured account roster. When no Codex roster is configured, the broker chooses the default Codex home.

## Commands

```text
python scripts/account_broker.py accounts --product claude
python scripts/account_broker.py choose --product codex
python scripts/account_broker.py choose --product codex --spent account-name:1790000000
python scripts/account_broker.py check --product codex
python scripts/account_broker.py run --product claude --report report.json -- claude --output-format json -p "prompt"
```

`accounts` prints the roster without reading meters. `choose` prints `decision`, `accounts`, and `state_path`. Each decision contains `action`, `account`, `home`, `reason`, `tier`, and `resets_at`. A wait decision has no account or home and includes the soonest reset in UTC. A failed meter read excludes the account for that choice. `--spent` saves an exclusion until the supplied Unix reset, the account's soonest known meter reset, or one hour when neither is available. Meter reads younger than 60 seconds are reused.

`check` prints nothing and exits 3 while every account is below its floor. `run` sets only `CLAUDE_CONFIG_DIR` or `CODEX_HOME` for each attempt. It replays the same stdin bytes when a usage limit or start failure leads to another account. It writes the command's stdout to stdout and diagnostics to stderr. A resumed Claude session uses the account bound to its session when that account has room.

The broker stores cached meters, spent marks, and Claude session bindings in one JSON file under `~/.claude/account-broker`. State writes use a sibling temporary file and `os.replace`.

## Exit codes and report

| Code | Meaning |
| --- | --- |
| `0` | `choose` or `check` found an account, or the job exited successfully. |
| `3` | No account clears its floor. The decision includes `resets_at`. |
| `4` | A Claude job stopped with `advisor_blocked`. |
| Other command code | `run` returns the command's exit code after a served response. |

`run` writes a JSON report with `product`, `command`, `events`, and `final_decision`. A wait report has `final_decision.action` equal to `wait` and a UTC `final_decision.resets_at`.
