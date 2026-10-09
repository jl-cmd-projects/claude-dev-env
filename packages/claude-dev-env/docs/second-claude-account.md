# Second Claude account

A second Claude subscription runs agents on the same machine as the main one. It
shares every skill, rule, plugin, setting and doc in the main Claude home, and it
keeps its own sign-in and history.

## Pieces

| File | What it does |
|---|---|
| `scripts/claude_account_profile.py` | Links each shared entry of `~/.claude` into the profile `~/.claude-profiles/ev`, moves stale copies into `.replaced/<time>/`, and writes the `claude-ev.cmd` launcher into `~/.local/bin` |
| `scripts/account_broker.py` | Reads the account roster and usage meters, chooses an account, and runs Claude with that account's home |
| `scripts/claude_account_worker.py` | Runs one headless Claude worker through the broker |
| `scripts/claude_account_worker_process.py` | Sends the brief to the broker and measures the run |
| `scripts/claude_account_worker_report.py` | Builds and writes the JSON report a worker leaves behind |
| `scripts/dev_env_scripts_constants/claude_account_worker_constants.py` | The worker's flag names, defaults, exit codes, and report keys |
| `scripts/dev_env_scripts_constants/claude_account_constants.py` | The profile name, the entries that stay per account, and the account thresholds |

The launcher sets `CLAUDE_CONFIG_DIR` to the profile and passes every argument to
`claude`, so `claude-ev -p "..."` runs like `claude -p "..."` on the second
account.

These entries stay per account and are never linked: `.credentials.json` and
`.claude.json` with their backups, `projects`, `sessions`, `todos`, `history.jsonl`,
and the other state folders named in the constants file.

## Sign in once

```
python packages/claude-dev-env/scripts/claude_account_profile.py
claude-ev auth login
```

The sign-in lives in `~/.claude-profiles/ev/.credentials.json` on that machine.
Claude refreshes it on each run.

## Which account a job uses

The broker ranks every Claude account that has room and picks the one with the
most room left. An account's room is the smaller of its 5-hour and weekly
percent left. A resumed session stays on its account while that account has
room.

| Account | Has room while |
|---|---|
| every account | under 99% of its week and under 95% of its 5-hour window |

When no account has room, the job waits until the next account reset, or for one
hour when no reset is known. An unreadable meter never picks its account, and
the wait reason names each account whose meter could not be read.

```
python packages/claude-dev-env/scripts/account_broker.py choose --product claude
```

The JSON output has a `decision` object and an `accounts` list. Each account's
`meters` holds its remaining percent and reset time for the 5-hour window and
the week. An unreadable meter appears as `null`, and the account's
`unread_reason` holds the failure text when the reader raised one. A wait decision has
`action: "wait"` and a `resets_at` timestamp. The broker exits with code 3 on
wait. The worker writes the same reset time to its report.
