# Codex accounts

The [account broker](account-broker.md) assigns agent work across the Codex accounts.
Each account signs in under its own Codex home, and every home
shares the same Codex setup: config, rules, skills, plugins, prompts and agents.
A job asks the broker which account to use.

## Pieces

| File | What it does |
|---|---|
| `scripts/account_broker.py` | `choose --product codex` names the account and tier a job runs on; `check --product codex` reports whether any account has room |
| `scripts/codex_account_choice.py` | `sync` links the shared setup into every account's home; `setup` and `install` write one launcher per account |
| `scripts/codex_account_meters.py` | Reads one account's rate-limit windows, plan and credits through `codex app-server` with `CODEX_HOME` set to that account's home |
| `scripts/codex_plan_rules.py` | Judges one account's meters: the paid-plan list, the free, unlisted and Pro plan rules, the floors, and the tier the account reaches |
| `scripts/codex_account_chooser.py` | Picks the Codex account and tier from the readings, Pro plan accounts first, up to the tier a caller requires |
| `scripts/dev_env_scripts_constants/codex_account_constants.py` | The fallback account names, the roster variable and file, the launcher template, the shared entry names, the 10% bar, the 1% Luna stop, the 20% short-window floor for Luna, the switch that lifts the weekly stop, the Pro, other paid and free plan names, and the credit keys |

## Names and order

The account list names the accounts. Codex accounts carry no priority, so a
choice ranks them by plan and room, and the list order breaks only an exact tie.
The list comes from the `CODEX_ACCOUNT_PROFILES` environment variable, a comma-separated list such as
`alpha,beta`. When that variable is unset or empty, the roster is the saved list
in `account-launchers.json` under the profiles root. When neither exists, the
roster is empty. The broker's `choose` and `check` then read the default Codex home
as the account `default`, and `install` has no accounts. `sync` falls back to `codex-1`, `codex-2`, `codex-3` and `codex-4` when no list names an account. `choose` and `check` fall back to them only when `CODEX_ACCOUNT_PROFILES` holds only separators, such as `,`, and no saved list names an account.

Each read of the variable's list saves it to `account-launchers.json` when the
file holds a different list. A service, runner, or other process started
without the variable then reads the same roster from the file. When the file
cannot be written, the read prints a warning and uses the variable's list.

The broker's `choose` and `check` commands and the setup commands use that list.
Each account's home is `~/.codex-profiles/<name>`, or
`<name>` under `CODEX_PROFILES_ROOT` when set. `~/.codex` holds the shared setup
and is never a roster account. With no roster, `choose` and `check` read it as the account `default` unless `CODEX_HOME` names another home. A name starts with an ASCII letter or digit, and the rest uses ASCII letters, digits, hyphens or underscores.
`main`, `wait` and the Windows device names are refused, in any letter case.

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

While `CODEX_ACCOUNT_PROFILES` is set, the variable's list stays the roster. The
next broker, sync, or install run saves it over the setup list, and setup prints
a warning when the two differ. Change or clear the variable to change the
roster. Two processes with different values of the variable each save their own
list, so a process without the variable reads whichever list was saved last.

## Which account a job uses

Room is the least percent left across an account's windows, such as the 5-hour window and the week.
A window that reports no length counts as weekly.
The broker reuses an account's reading for 60 seconds, so a reading can be up to 60 seconds old.

This table covers a choice made without `--home`. A home that a caller names with `--home` follows the `--home` paragraph after the table.
On a paid plan with readable meters, that home runs whatever its room, credits or floors. It takes the tier its meters allow, or `luna` when no tier allows it.
The rows that rank accounts by plan, room and credits do not apply to it. The rows for a free plan, an unlisted plan and a failed meter read still apply.

| Condition | Answer |
|---|---|
| A Pro plan account (`pro`, `prolite` and `promax`) with more than 10% left | `normal` on the Pro account with the most room, before any account on another plan |
| No such Pro account, and a Pro plan account with more than 0% left in each window | `luna` on the Pro account with the most room, before any account on another plan, even one with more than 10% left |
| No Pro plan account reaches `normal` or `luna`, and an account on another paid plan with more than 10% left | `normal` on the account with the most room |
| No Pro plan account reaches `normal` or `luna`, no other account over 10%, and an account on another paid plan with more than 1% of its week left and at least 20% left in any window shorter than a week | `luna` on the account with the most room |
| Within one plan group (the Pro plan accounts, or the accounts on another paid plan), one account reaches `normal` and another reaches only `luna` | the `normal` account, whatever the room of each |
| Two accounts in one plan group at the same tier with the same room | The account that comes first in the account list. Codex accounts carry no priority, so the list order breaks only an exact tie |
| An account on a free plan (`free`) | never chosen, whatever its room or credits; a `wait` reason names it |
| An account whose plan is missing, blank or not one of the paid plans, which are `business`, `edu`, `enterprise`, `plus`, `pro`, `prolite`, `promax` and `team` | never chosen, whatever its room or credits; a `wait` reason names it |
| An account with credits (`hasCredits` is `true` with a balance above zero, or `unlimited` is `true`) and 10% or less left | `normal`, even at or under 1% of its week left or under 20% of a short window; the rows above that give `luna` count only accounts without credits; a Pro plan account with credits comes before every account on another plan; among accounts of the same kind, the one with the most room, so plan usage comes before credits alone |
| An account on another paid plan that reports a window shorter than a week, such as the 5-hour window, with under 20% of that window left | never takes `luna` |
| No account can run: no Pro plan account with more than 0% left in each window, no account on another paid plan with over 10% left or with more than 1% of its week left and at least 20% left in any window shorter than a week, and no account with credits | `wait`, naming the next reset when known |
| A meter read finds no Codex executable, or fails with text that holds `HTTP Error 429` | The broker makes that 1 read and does not retry. A 429 text sets no rate-limit cooldown for a Codex account |
| A meter read fails with a `CodexMeterUnreadError`, `OSError`, `ValueError`, `RuntimeError` or `subprocess.SubprocessError` that the row above does not cover | The broker reads it again, up to 3 reads, waiting 1 second and then 2 seconds |
| A meter read raises any other exception type | The broker does not catch it, so the command ends with that exception after 1 read |
| A meter is unread after every read | The account has `meters: null` and the failure text in `unread_reason`; a `wait` reason names the account and that text. An unread account is not judged by plan |

A caller that needs the `normal` tier passes `--require-tier normal`. The broker then chooses a Pro plan account only when it reaches `normal`, and otherwise the account on another paid plan with the most room that does. A caller that passes no tier takes a Pro plan account first, even on `luna`, before an account on another plan with more room.

With no roster configured, `choose` and `check` read the default Codex home, `CODEX_HOME` or `~/.codex`, as the account `default` and apply the same rules. A `CODEX_HOME` that is empty or only whitespace counts as unset. A failed read gives `wait` and exit 3, and the reason names the failure.

`--home <path>` judges that Codex home alone. A home on a paid plan with readable meters runs, whatever its room, with or without credits, and whatever `CODEX_WEEKLY_FLOOR_DISABLED` says. It reports the tier its meters allow, or `luna` when no tier allows it. A free, missing, blank, unknown or unlisted plan, or a home whose meters are unread, still gives `wait`. `--require-tier normal` still applies, so a home that does not reach `normal` gives `wait`. `check --home` answers as `choose --home` does. A spent mark saved for the roster account that has this home, by `run` or by `choose --spent`, still gives `wait` until its reset. A mark is keyed by product, account name and home, and `--home` reads a home the roster does not list as an account named for its folder. So a mark saved for the no-roster default account, named `default`, does not hold `--home <that home>` unless the folder of that home is also named `default`, and a mark saved for an account outside the roster never holds a `--home` answer. After an account leaves the roster, a mark saved while it was in the roster still holds `--home <its home>` only when the account's name equals the name of its resolved home folder. A roster account `Alpha` whose home folder is `alpha`, or whose home folder is a junction to a folder with another name, no longer holds `--home <its home>` once it leaves the roster. The broker refuses `--home` for the Claude product and with `--spent`.

A spent mark for an account outside the roster holds every answer made without `--home`. `choose --spent <name>[:reset]` saves it for a name the roster does not list, and `choose`, `check` and `run` then give `wait` until its reset, even when a roster account has room. The reason reads `account <name> outside the roster is spent; next reset at <time>`. With several such marks, the soonest reset counts. When the roster already answers `wait`, the earlier of the two resets is the one the answer reports. A mark with no reset lasts one hour.

The name `default` is the exception beside a roster that lists no account named `default`. There, `default` is not an account, because the default home is read only when no roster is configured. `choose --spent default` then saves nothing and prints a warning on standard error, and a stored `default` mark does not make `choose`, `check` or `run` wait.

```
python packages/claude-dev-env/scripts/account_broker.py choose --product codex
{"decision": {"action": "run", "account": "codex-1", "home": "...\\codex-1",
 "resets_at": null, "reason": "codex-1 has 62% left", "tier": "normal"},
 "accounts": [{"name": "codex-1", "home": "...\\codex-1", "is_main": false,
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

Set `CODEX_WEEKLY_FLOOR_DISABLED` to lift the 1% weekly stop for an account on a paid plan other than a Pro plan. The values that turn it on are `1`, `on`, `true` and `yes`. While it is on, such an account without credits that has 1% or less of its week left can take `luna`, and `choose` and `check` do not wait for its weekly reset. The 20% short-window floor still applies to it. The switch changes nothing for a Pro plan account. Without credits, a Pro plan account takes `luna` with more than 0% left in each window and waits at 0% in either window, whether the switch is on or off. An account with credits already runs under both floors, so the switch matters only for an account on another paid plan without credits.

```
$env:CODEX_WEEKLY_FLOOR_DISABLED = "1"
```

## Shared callers

Three scripts under `_shared` and the review evaluation run `choose --product codex` by path. Each script under `_shared` finds the
broker at `scripts/account_broker.py` in the directory that holds `_shared`.
Once installed, that is `~/.claude/scripts/account_broker.py`. The evaluation looks for
`scripts/account_broker.py` in the package that holds `.agents`, and then for the same file name under that package's `.claude/scripts` folder.

| Caller | What it does with the answer |
|---|---|
| `_shared/pr-loop/scripts/check_convergence.py` | Requires a Codex clean stamp on HEAD only on `normal`. `luna`, `wait`, or a failed broker skips the Codex gate |
| `_shared/advisor/scripts/codex_astra_advisor.py` | Calls `run_astra_preflight` in `_shared/advisor/scripts/codex_astra_preflight.py`, which runs the broker and judges its answer. With `CODEX_HOME` unset or blank, the preflight accepts only `normal`, and the advisor runs Codex with `CODEX_HOME` set to `decision.home`. With a non-blank `CODEX_HOME` set, the preflight asks the broker to judge that home and accepts `normal` or `luna`, which the broker answers for a paid plan whatever its room, and the advisor binds on that home. A `wait` answer or a tier it does not accept returns a `declined` fallback with the broker's reason and starts no Codex process. A broker that times out, cannot start, exits with a code other than 0 or 3, prints malformed JSON, or answers `normal` or `luna` with no home or no meters returns a `broken` fallback and starts no Codex process |
| `_shared/pr-loop/scripts/run_codex_review.py` | Runs the review with `CODEX_HOME` set to `decision.home`. With `CODEX_HOME` unset or blank, it accepts only `normal`. With a non-blank `CODEX_HOME`, it asks the broker to judge that home and accepts `normal` or `luna`, and the review runs on `decision.home`, the trimmed absolute folder the broker judged. `wait`, a tier it does not accept, or a failed broker returns `codex_down`, so the gate fails closed. A failed broker is one that does not answer, exits with a code other than 0 or 3, prints an answer that is not JSON or holds no `decision` object, or answers with no home. A broker that does not answer covers a timeout (exit code 124), a missing interpreter binary (127), and any other `OSError` from the spawn, such as `PermissionError` (126). Any other `OSError` at spawn returns 126 for a Codex probe, the broker or the review process, and on Windows that includes a removed working directory (`NotADirectoryError`), which only the review process can hit because the probes and the broker run with no working directory. A missing `account_broker.py` makes Python exit 2, and the outcome carries 2. Exit 69 covers a malformed broker answer, a wait, a refused tier, and an answer that names no home. Output that is not UTF-8 is decoded with replacement characters and checked like any other output. The `agent_message` text is `no Codex account has room for a review (<the broker's reason>)` for `wait` and a refused tier. Any other failure gives the script's own text, such as `account broker exit 2`, `account broker answer is malformed`, `account broker answer names no Codex home` or `account broker did not answer: exit 124`. A spawn error gives `account broker did not answer: exit 126` |
| `.agents/skills/build-eval/evals/review/review_eval_support/account.py` | Runs each live `codex exec` with `CODEX_HOME` set to `decision.home`. With `CODEX_HOME` unset or blank, it accepts only `normal`. With a non-blank `CODEX_HOME`, it asks the broker to judge that home and accepts `normal` or `luna`, and the run uses `decision.home`, the trimmed absolute folder the broker judged. `wait`, a tier it does not accept, or a failed broker records `infra_error` with the failure `no_codex_account` and starts no model call |

`run_codex_review.py`, the evaluation and `codex_astra_advisor.py` keep the account a non-blank `CODEX_HOME` names, but ask the broker to judge that home first with `choose --product codex --home <path>`, which the advisor runs through `codex_astra_preflight.py`. The home runs whether or not the roster lists it, whatever its room, at the tier the broker answers, `normal` or `luna`. A free plan, a missing, blank, unknown or unlisted plan, a `wait`, an unreadable home, or a failed broker gives `codex_down`, `infra_error`, or for the Astra advisor a fallback reply, with no model call. The Astra fallback is `declined` with the broker's reason when the broker answered `wait` or a tier the advisor does not accept, and `broken` when the broker failed to answer or its answer is unusable. `run_codex_review.py`, the evaluation and `codex_astra_advisor.py` launch Codex on `decision.home`, the trimmed absolute folder the broker judged, so whitespace around the exported value never reaches Codex.

A Pro plan account without credits takes `luna` for a caller that names no tier when its room is more than 0% and at most 10%. Each caller above passes `--require-tier normal` when it chooses among accounts, so the broker gives it the best account that reaches `normal`, or `wait`. A caller that judges a `CODEX_HOME` already set passes `--home` and no tier, so the broker answers `normal` or `luna` for a paid home with readable meters.

## Trimmed Sol prompt

The installer writes one top-level line into `~/.codex/config.toml`, under a
`# claude-dev-env trimmed Sol prompt` marker. The line points
`model_instructions_file` at `~/.codex/codex-sol.md`, a copy of the package's
`system-prompts/codex-sol.md`. The copy sits beside `config.toml`, so pruning
the managed files under `~/.claude`, which an older package version does on
`--update`, cannot leave Codex pointing at a missing file. The file
is Codex's default `gpt-6.1-sol` prompt with the lines that conflict with the
package rules rewritten. The line names no model, so every Codex run uses the
file, whichever model it selects. `sync` links `config.toml` into every account
home, so every account gets the line.

When `CODEX_HOME/config.toml` is the same file as `~/.codex/config.toml`, the
copy goes in `~/.codex`. `sync` makes that file a symbolic link, or a hard link
when the account cannot create symbolic links. Installing from an account home
then names the shared copy in `~/.codex`, and deleting or uninstalling that
account home leaves the other homes working. A `config.toml` that links
anywhere else, such as a dotfiles folder, keeps the copy in `CODEX_HOME`.

A `model_instructions_file` the user wrote at the top level keeps the config as
it is. Uninstall removes only the package line and the copy. Uninstalling from
an account home that shares `~/.codex/config.toml` leaves both alone, because
`~/.codex` still uses them.

To see which prompt Codex uses, read the setting:

```
Select-String -Path "$HOME\.codex\config.toml" -Pattern model_instructions_file
```

To run Codex on the trimmed prompt through the broker, run it as usual. `run`
reads all of standard input before it starts Codex, so close it:

```
python ~/.claude/scripts/account_broker.py run --product codex --report <report.json> -- codex exec "<request>" < /dev/null
```
