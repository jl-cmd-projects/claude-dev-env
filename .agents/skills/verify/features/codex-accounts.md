# Codex accounts

The account broker reads the rate-limit windows of the roster's Codex accounts, each signed in under its own Codex home, and names the account and tier a job runs on. [The guide](../../../../packages/claude-dev-env/docs/codex-accounts.md) states the design.

## Sub-features

- Roster. `CODEX_ACCOUNT_PROFILES`, comma-separated, else `account-launchers.json` under the profiles root, names the accounts in try order. With neither, the accounts are `codex-1` through `codex-4`. The broker's `choose` and `check` commands and `sync` use it.
- Home sync. `scripts/codex_account_choice.py sync` links the shared entries of `~/.codex`, `agents` among them, into each roster account's home.
- Named launchers. `setup` asks for names, saves the roster, and writes `codex-<name>.cmd` with `call codex %*`. `install` reruns it without asking. A name left out at setup has its launcher renamed with a `.replaced-<time>` suffix, and its home stays.
- Per-account state. Every entry outside `ALL_SHARED_CODEX_HOME_NAMES` stays in each home and is never linked.
- Meter read. `scripts/codex_account_meters.py` starts `codex app-server` with `CODEX_HOME` set, sends the handshake and `account/rateLimits/read`, and keeps standard input open until the reply lands.
- Broker. `choose --product codex` prints `decision` with `action`, `account`, `home`, `reset_at`, `reason`, and `tier`, plus `accounts` with each account's meters. The normal tier selects the account with the most room. A wait answer exits 3 and still prints JSON.
- Luna stop. `check --product codex` exits 3 while every account is below its floor and 0 when an account has room.
- Luna 5-hour floor. An account that reports a 5-hour window takes `luna` only with at least 20% of that window left.

## How to get to it (user POV)

A user runs `setup` once, or `sync` with `CODEX_ACCOUNT_PROFILES` set, then signs each account in with `CODEX_HOME` set to its home and `codex login`. A job calls `account_broker.py choose --product codex` before it starts Codex, and runs under the `decision.home` it prints.

## Driving it with Python

Run the unit tests from the repository root:

```powershell
python -m pytest packages/claude-dev-env/scripts/test_codex_account_choice.py packages/claude-dev-env/scripts/test_account_broker.py packages/claude-dev-env/scripts/test_account_broker_guard.py -q
```

On Windows the run includes `TestNpmShimLauncher`, which runs the Claude and Codex launchers through `cmd` against an npm-shaped shim and reads back `CLAUDE_CONFIG_DIR` or `CODEX_HOME`.

Drive the broker with a configured roster:

```powershell
python packages/claude-dev-env/scripts/account_broker.py choose --product codex
```

When every account sits below its floor, it exits 3 and prints `"decision": {"tier": "wait", ...}`. The `accounts` entries hold the available meter readings.

Drive the sync against a disposable home:

```powershell
python packages/claude-dev-env/scripts/codex_account_choice.py --profiles-root <tmp>/profiles sync --main-home <tmp>/main
```

Each account lists its shared entries under `linked`. A second run prints empty lists.

Drive the launchers against a disposable home that holds a few shared entries:

```powershell
$env:CODEX_ACCOUNT_PROFILES = "alpha,beta"
python packages/claude-dev-env/scripts/codex_account_choice.py --profiles-root <tmp>/profiles install --main-home <tmp>/main --launcher-directory <tmp>/bin
```

It prints `linked` and `launcher` for `alpha` and `beta`, and writes `codex-alpha.cmd` and `codex-beta.cmd`. A second run prints empty lists. Pipe names into `setup` with the variable unset, one per line, and it prints the saved names, then an `installed` report and a `retired` map naming each dropped launcher.

## Live meters

A live `choose` needs signed-in accounts. Run it from a pinned commit of this repository. Each readable account shows `session_percent_left` and `weekly_percent_left` in `meters`. Keep the command output out of this repository, since it names local paths.

## Gotchas

- Never read, print, or copy an `auth.json` file.
- The server exits without answering once its standard input closes, so the reader holds input open until the reply arrives or 30 seconds pass.
- An unread meter never takes a job. A `wait` with every account unread names no reset.
