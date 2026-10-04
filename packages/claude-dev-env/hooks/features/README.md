# Hook feature map

Open this map before changing, debugging, or adding a hook. Pick the family that owns the behavior, then use its registration and proof command to check the change.

## Where hooks run

- Claude hook registrations live in [`hooks.json`](../hooks.json). The four `ALL_*HOSTED_HOOK_ENTRIES` rosters in [`hooks_constants/`](../hooks_constants/) name scripts run inside dispatchers. The Write and Edit dispatcher also calls `blocking/state_description_blocker.py` directly.
- Policy lint loads several modules under `hooks/blocking/` through [`adapter_detectors.py`](../../scripts/policy_lint/adapter_detectors.py) and [`adapter_pairing.py`](../../scripts/policy_lint/adapter_pairing.py). A module in that directory is not necessarily a Claude hook.
- Reinstall pruning comes from `FOLDED_HOOK_RELATIVE_PATHS`, `POST_FOLDED_HOOK_RELATIVE_PATHS`, and `RETIRED_HOOK_REGISTRATION_RELATIVE_PATHS` in [`bin/install.mjs`](../../bin/install.mjs).
- Git hook entry points and their tests live in [`hooks/git-hooks/`](../git-hooks/).

## Feature entry contract

Each family page starts with a title and an agent-facing behavior summary. Its four sections appear in order. `Checks` names each registered script once, `When it fires` gives the event, matcher, timeout, and hosted tool names, `Proving it` pairs an input with a repository-root command and expected observation, and `Gotchas` records traps near that family.

## Conventions

- Script paths in `Checks` start at `hooks/`. Commands in `Proving it` start at the repository root.
- The dispatcher is the registration point for each hosted script. Use its roster to check which tool names reach the script.
- A command that runs pytest uses the named adjacent test file. Read that test before changing the behavior it covers.
- `hooks/hooks.json` and the four hosted rosters decide membership. The map test checks that every registered script appears once.

## Families

- [Write and Edit blocking](./write-edit-blocking.md) covers the mutation dispatcher, edit advisors, and description gate.
- [Bash dispatchers](./bash-dispatchers.md) covers command rewriting and the post-call reminder.
- [Post-write validation](./post-write-validation.md) covers the after-write dispatcher and formatter.
- [Conduct gates](./conduct-gates.md) covers chat replies, edit markers, step notes, checked claims, and the pull request lifecycle skill.
- [Session context](./session-context.md) covers skill reminders and startup guidance.
- [Spawn routing](./spawn-routing.md) covers spawn readiness, pacing, and model selection.
- [Observability](./observability.md) covers instruction loads, edited files, and investigation resets.
- [Lifecycle cleanup](./lifecycle-cleanup.md) covers nested checkouts, worktree setup, and session cleanup.
