# Codex accounts

The account broker reads the rate-limit windows of the roster's Codex accounts, each signed in under its own Codex home, and names the account and tier a job runs on. [The guide](../../../../packages/claude-dev-env/docs/codex-accounts.md) states the design.

## Sub-features

- Roster. `CODEX_ACCOUNT_PROFILES`, comma-separated, else `account-launchers.json` under the profiles root, names the accounts in try order. The broker's `choose` and `check` commands and `sync` use it. With neither, the roster is empty: `choose` and `check` read the default Codex home as the account `default`, apply the same plan rule, and give `wait` on a failed read, and `install` has no accounts. `sync` falls back to `codex-1` through `codex-4` when no list names an account. `choose` and `check` fall back to them only when `CODEX_ACCOUNT_PROFILES` holds only separators, such as `,`, and no saved list names an account.
- Home sync. `scripts/codex_account_choice.py sync` links the shared entries of `~/.codex`, `agents` among them, into each roster account's home.
- Named launchers. `setup` asks for names, saves the roster, and writes `codex-<name>.cmd` with `call codex %*`. `install` reruns it without asking. A name left out at setup has its launcher renamed with a `.replaced-<time>` suffix, and its home stays.
- Per-account state. Every entry outside `ALL_SHARED_CODEX_HOME_NAMES` stays in each home and is never linked.
- Meter read. `scripts/codex_account_meters.py` starts `codex app-server` with `CODEX_HOME` set, sends the handshake and `account/rateLimits/read`, and keeps standard input open until the reply lands.
- Broker. `choose --product codex` prints `decision` with `action`, `account`, `home`, `resets_at`, `reason`, and `tier`, plus `accounts` with each account's meters. A Pro plan account that can run comes before every account on another plan, in either tier. Within a plan group, the normal tier selects the account with the most room. A wait answer exits 3 and still prints JSON.
- Luna stop. `check --product codex` exits 3 while every account is below its floor and 0 when an account has room.
- Luna short-window floor. An account on a paid plan other than a Pro plan, without credits, that reports a window shorter than a week, such as the 5-hour window, takes `luna` only with at least 20% of that window left. A Pro plan account at session 5% and week 80% takes `luna`, and a paid plan account with credits at 0% and 0% takes `normal`. A paid plan account other than a Pro plan at session 5% and week 80% waits in the roster, and `choose --home <path>` runs that one named home on `luna` below the 20% floor unless `--require-tier normal` is also passed.
- Free plan, unlisted plan and credits. Only an account whose `plan_type` is on the paid list (`ALL_PAID_PLAN_TYPES`) is chosen. An account whose `plan_type` is `free`, missing, blank, `unknown` or any other name, such as `free_works`, is never chosen, whatever its room, credits or the weekly-floor switch, and a `wait` reason names it. An account with unread meters is not judged by plan. An account with credits (`hasCredits` is `true` with a balance above zero, or `unlimited` is `true`) takes `normal` under both floors, and a Pro plan account comes first.
- Model-run callers. `_shared/pr-loop/scripts/run_codex_review.py` and the review evaluation under `.agents/skills/build-eval/evals/review` run `codex exec` with `CODEX_HOME` set to `decision.home`. With `CODEX_HOME` unset or blank, they accept only `normal`, and `luna`, `wait`, or a failed broker gives `codex_down` or `infra_error` with no model call. A non-blank `CODEX_HOME` goes to the broker trimmed, as `choose --product codex --home <path>`, which runs a paid plan whatever its room at `normal` or `luna`, and the run launches on the home the broker answers, the trimmed absolute folder it judged. A free, unknown or unlisted plan, a `wait`, an unreadable home, or a failed broker gives `codex_down` or `infra_error` with no model call. `_shared/advisor/scripts/codex_astra_advisor.py` judges a non-blank `CODEX_HOME` the same way, runs on `decision.home` at `normal` or `luna` whether or not the roster lists it, and returns a fallback reply with no Codex process when the broker refuses it: `declined` when the broker answers `wait` or a tier it does not accept, `broken` when the broker fails to answer or its answer is unusable. These callers and the convergence gate and the Astra preflight with no `CODEX_HOME` pass `--require-tier normal`, so a Pro plan account on `luna` gives way to the best account that reaches `normal`.

## How to get to it (user POV)

A user runs `setup` once, or `sync` with `CODEX_ACCOUNT_PROFILES` set, then signs each account in with `CODEX_HOME` set to its home and `codex login`. A job calls `account_broker.py choose --product codex` before it starts Codex, and runs under the `decision.home` it prints.

## Driving it with Python

Run the unit tests from the repository root:

```powershell
python -m pytest packages/claude-dev-env/scripts/test_codex_account_choice.py packages/claude-dev-env/scripts/test_account_broker.py packages/claude-dev-env/scripts/test_account_broker_guard.py packages/claude-dev-env/_shared/pr-loop/scripts/test_codex_review_account.py packages/claude-dev-env/_shared/pr-loop/scripts/test_run_codex_review.py packages/claude-dev-env/.agents/skills/build-eval/evals/review/test_run.py -q
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
