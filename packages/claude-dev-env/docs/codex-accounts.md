# Codex accounts

The account broker assigns agent work across the Codex accounts.
Each account signs in under its own Codex home, and every home
shares the same Codex setup: config, rules, skills, plugins, prompts and agents.
A job asks the broker which account to use.

## Pieces

| File | What it does |
|---|---|
| `scripts/account_broker.py` | `choose --product codex` names the account and tier a job runs on; `check --product codex` reports whether any account has room |
| `scripts/codex_account_choice.py` | `sync` links the shared setup into every account's home; `setup` and `install` write one launcher per account |
| `scripts/codex_account_meters.py` | Reads one account's rate-limit windows through `codex app-server` with `CODEX_HOME` set to that account's home |
| `scripts/dev_env_scripts_constants/codex_account_constants.py` | The fallback account names, the roster variable and file, the launcher template, the shared entry names, the 10% bar, the 1% Luna stop, and the 20% 5-hour floor for Luna |

## Names and order

The account roster names the accounts and their order. It comes from the
`CODEX_ACCOUNT_PROFILES` environment variable, a comma-separated list such as
`alpha,beta`. When that variable is unset or empty, the roster is the saved list
in `account-launchers.json` under the profiles root. When neither exists, the
accounts are `codex-1`, `codex-2`, `codex-3` and `codex-4`.

The broker's `choose` and `check` commands and the setup commands use that list.
Each account's home is `~/.codex-profiles/<name>`, or
`<name>` under `CODEX_PROFILES_ROOT` when set. `~/.codex` holds the shared setup
and is never an account. A name uses letters, digits, hyphens or underscores.
`main`, `wait` and the Windows device names are refused.

## Sign in once

```
python packages/claude-dev-env/scripts/codex_account_choice.py sync
```

Then, for each account, sign in with that account's home:

```
$env:CODEX_HOME = "$HOME\.codex-profiles\codex-1"; codex login
```

The sign-in lives in that folder's `auth.json`. Only the entries in
`ALL_SHARED_CODEX_HOME_NAMES` link to `~/.codex`. They are `AGENTS.md`, `agents`,
`config.toml`, `hooks`, `hooks.json`, `plugins`, `prompts`, `rules` and `skills`.
Sign-in, sessions, history, logs and state files stay per account.

## Named launchers

Each roster account gets a launcher, `codex-<name>.cmd`, in `~/.local/bin`. It
sets `CODEX_HOME` to that account's home and runs Codex with every argument, so
`codex-alpha exec "fix the test"` runs on the `alpha` account.

Run the setup once:

```
python packages/claude-dev-env/scripts/codex_account_choice.py setup
```

It prints the saved names, then asks for one name per line. A blank line or the
end of input finishes. An invalid name prints the reason and asks again. A
repeated name counts once. The setup saves the list to
`~/.codex-profiles/account-launchers.json`, links each account's home to
`~/.codex`, and writes each launcher.

Rerun the installer after the shared setup or this package changes:

```
python packages/claude-dev-env/scripts/codex_account_choice.py install
```

It reads the roster, links every account's home, and rewrites any launcher that
differs. A second run changes nothing. With no roster it prints `{}`.
`CODEX_ACCOUNT_PROFILES` overrides the saved file here too. Both commands take
`--main-home` and `--launcher-directory`.

The launcher runs `call codex %*`. `codex` is npm's `codex.cmd`, and its last
line ends the batch scope. Without `call`, that line also drops the launcher's
`CODEX_HOME`, and Codex runs on the main home.

The names typed in one setup run become the whole roster. A saved name
left out has its launcher renamed to `codex-<name>.cmd.replaced-<time>`. Its
folder under the profiles root stays, with its `auth.json`, so typing the name
again restores it. A blank first line empties the roster and moves every launcher
aside.

## Which account a job uses

Room is the smaller of an account's two windows: the 5-hour window and the week.

| Condition | Answer |
|---|---|
| One or more accounts with more than 10% left | `normal` on the account with the most room |
| No account over 10%, one or more over 1% | `luna` on the account with the most room |
| An account that reports a 5-hour window, with under 20% of that window left | never takes `luna` |
| No account over 1% | `wait`, naming the next reset when known |
| A meter is unread | The account has `meters: null` in `accounts` |

```
python packages/claude-dev-env/scripts/account_broker.py choose --product codex
{"decision": {"action": "run", "account": "codex-1", "home": "...\\codex-1",
 "reset_at": null, "reason": "codex-1 has 62% left", "tier": "normal"},
 "accounts": [{"account": "codex-1", "home": "...\\codex-1", "main": false,
 "meters": {"session_percent_left": 62.0, "session_resets_at": null,
 "weekly_percent_left": 70.0, "weekly_resets_at": null}}]}
```

A job runs Codex with `CODEX_HOME` set to `decision.home`. On `luna`, the job runs
Luna and polls `check` between steps:

```
python packages/claude-dev-env/scripts/account_broker.py check --product codex
```

`check` exits 3 while every account is below its floor, and 0 when an account
has room. The job stops on 3. `choose` also exits 3 for `wait` and still prints
the JSON answer.

## Shared callers

Two scripts under `_shared` run `choose --product codex` by path. Each finds the
broker at `scripts/account_broker.py` in the directory that holds `_shared`.
Once installed, that is `~/.claude/scripts/account_broker.py`.

| Caller | What it does with the answer |
|---|---|
| `_shared/pr-loop/scripts/check_convergence.py` | Requires a Codex clean stamp on HEAD only on `normal`. `luna`, `wait`, or a failed broker skips the Codex gate |
| `_shared/advisor/scripts/codex_astra_advisor.py` | Binds Astra only on `normal`, and runs Codex with `CODEX_HOME` set to `decision.home` |
