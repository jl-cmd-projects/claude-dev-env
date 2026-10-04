# Second Claude account

A second Claude subscription runs agents beside the main account. The profile sync shares the main Claude home with the second account's profile. The broker reads usage meters, applies the main account guard, and runs the job under the chosen account. [The second account guide](../../../../packages/claude-dev-env/docs/second-claude-account.md) states the design.

## Sub-features

- Profile sync. `scripts/claude_account_profile.py` links each shared entry of the main home into `~/.claude-profiles/ev`, moves a stale copy into `.replaced/<time>/`, and removes a link whose main entry is gone.
- Per-account state. Sign-in, `.claude.json`, history, and the state folders in `claude_account_constants.py` stay in each profile and are never linked.
- Launcher. The sync writes `claude-ev.cmd`, which sets `CLAUDE_CONFIG_DIR` to the profile and passes every argument to `claude`.
- Account broker. `scripts/account_broker.py` prints a decision and account readings for `choose`, or runs a command with `run`.
- Usage probe. `scripts/claude_chain_usage.py` reads one account's short and weekly meters for the broker.

## How to get to it (user POV)

A user runs the profile sync once, then signs the second account in with `claude-ev auth login`. The broker chooses an account and sets its home for each Claude job.

## Driving it with Python

Run the unit tests from the repository root:

```powershell
python -m pytest packages/claude-dev-env/scripts/test_claude_account_profile.py packages/claude-dev-env/scripts/test_account_broker.py packages/claude-dev-env/scripts/test_account_broker_guard.py packages/claude-dev-env/scripts/test_claude_chain_usage.py -q
```

Drive the sync against a disposable home. Pass all three paths, so the run writes nothing under the user home:

```powershell
python packages/claude-dev-env/scripts/claude_account_profile.py --main-home <tmp>/main --profile-home <tmp>/profiles/ev --launcher-directory <tmp>/bin
```

The first run lists each shared entry under `linked`. A second run prints empty `linked`, `moved_aside`, and `unlinked` lists. A plain folder in the profile under a shared name moves to `.replaced/<time>/` and reports under `moved_aside`. An entry removed from the main home reports under `unlinked`. A per-account name such as `.credentials.json` never appears in `linked`.

Check broker routing with the broker tests. They supply disposable account homes and meter readings:

```powershell
python -m pytest packages/claude-dev-env/scripts/test_account_broker.py -q
```

The tests assert the chosen account, the main account guard, usage-limit fall-through, and the wait exit code.

## Live meters

To inspect a configured account roster, run `python packages/claude-dev-env/scripts/account_broker.py choose --product claude`. Its JSON output carries `decision`, `accounts`, and `state_path`. A wait decision includes `resets_at` and exits with code 3. Keep the output out of this repository because it names local paths.

## Gotchas

- Keep credential files out of test fixtures. The broker tests use fake meter readings.
- An unread main meter never picks main.
- On Windows a shared directory links as a junction. On other systems it links as a symbolic link. A shared file links as a symbolic link, or as a hard link when the system refuses a symbolic link.
- The launcher is a Windows command file. On other systems the proof reads its text and does not run it.
