# Account broker

`account_broker.py` reads the configured Claude or Codex accounts, reads each account's 5-hour and weekly usage, and chooses the account with the most room in its tighter window. Claude's main account runs only while its existing spend guard permits it. A Codex decision may name the `normal` or `luna` tier so the caller can choose a model. The broker does not choose a model or sleep.

## Commands

Run these commands from the package checkout.

```text
python scripts/account_broker.py choose --product claude
python scripts/account_broker.py check --product codex
python scripts/account_broker.py run --product claude --report report.json -- claude --output-format json -p "prompt"
```

`choose` prints a JSON object with `decision` and `accounts`. Each account has its name, home, main-account flag, and meters. Unread meters are `null`. `check` prints nothing and lets a caller poll for room. `run` sets `CLAUDE_CONFIG_DIR` or `CODEX_HOME` for each attempt. After a usage-limit response, it tries the next eligible account and writes the report. A resumed Claude session uses the account recorded for its session when that account remains available.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | `choose` or `check` found an account, or the job exited successfully. |
| `3` | No account clears its floor. The decision includes the soonest known reset. |
| Other command code | `run` returns the job's exit code after a non-limit response. |

## Report

`run` writes a JSON object with `product`, `command`, `events`, and `final_decision`. Each pick event holds a decision. Each attempt event holds an account and exit code. Each usage-limit event holds the account and its next known reset. The final decision holds `action`, `account`, `home`, `reset_at`, `reason`, and `tier`. A wait decision has no account or home.
